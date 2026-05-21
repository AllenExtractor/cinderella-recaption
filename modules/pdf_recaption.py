"""
pdf_recaption.py — /changepcaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flow:
  1. User sends /changepcaption in group
  2. Bot says: send up to 45 PDFs now
  3. User sends PDFs — one by one OR many at once (all accepted instantly)
     Bot concurrently downloads all to disk, deletes from chat, counts
  4. User sends /Done → Bot re-uploads all from disk with new cc1 captions
  5. Done message + invite to use again

SPEED FIXES:
  - BURST_WAIT removed — no delay before draining burst
  - All files in a burst downloaded CONCURRENTLY (asyncio.gather)
  - All deletes run concurrently
  - Re-uploads also concurrent (controlled with semaphore)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import os
import tempfile

from pyrogram import Client, filters
from pyrogram.types import Message

import globals
import user_store
from caption_builder import build_pdf_caption, get_title_from_file_or_caption
from vars import AUTH_USERS

MAX_PDFS      = 45
TIMEOUT       = 300   # 5 min idle wait
BURST_DRAIN   = 1.0   # 300ms window to drain simultaneous messages
MAX_DL_CONCUR = 4     # max concurrent downloads

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

def register_pdf_recaption_handlers(bot: Client):

    @bot.on_message(filters.command("changepcaption") & filters.group)
    async def changepcaption_cmd(client: Client, m: Message):
        chat_id = m.chat.id
        user_id = m.from_user.id if m.from_user else 0

        if user_id not in AUTH_USERS:
            await m.reply_text(
                f"<blockquote>**🙅 You are not authorized to use this bot.**\n"
                f"Contact the owner to get access.\n"
                f"Your User ID: `{user_id}`</blockquote>"
            )
            return

        # Check bot is admin
        try:
            bot_member = await client.get_chat_member(chat_id, (await client.get_me()).id)
            if bot_member.status.name not in ("ADMINISTRATOR", "OWNER"):
                await m.reply_text("⚠️ **Please make me an Admin with full rights first!**")
                return
        except Exception:
            pass

        await m.delete()

        editable = await client.send_message(
            chat_id,
            "**📄 PDF Caption Change Mode**\n\n"
            f"Send up to **{MAX_PDFS} PDF files** now — forward many at once!\n\n"
            "<blockquote>• I will instantly accept all PDFs, download & delete.\n"
            f"• Send **/Done** anytime to re-upload with new captions.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        collected: list = []   # { path, title }
        count = 0
        tmp_dir = tempfile.mkdtemp(prefix="cinpdf_")
        dl_sem  = asyncio.Semaphore(MAX_DL_CONCUR)

        async def download_one(msg: Message, idx: int):
            """Download a single PDF to disk, return item dict or None."""
            fname = msg.document.file_name or "document.pdf"
            cap   = msg.caption or ""
            title = get_title_from_file_or_caption(fname, cap)
            safe  = "".join(
                c if c.isalnum() or c in "._-" else "_"
                for c in f"{idx:03d}_{fname}"
            )
            fpath = os.path.join(tmp_dir, safe)

            async with dl_sem:
                try:
                    await client.download_media(msg, file_name=fpath)
                except Exception as dl_err:
                    await client.send_message(
                        chat_id,
                        f"⚠️ Download failed for PDF {idx}: {str(dl_err)[:150]}"
                    )
                    try: await msg.delete()
                    except Exception: pass
                    return None

            # Delete from chat right after download
            try:
                await msg.delete()
            except Exception:
                pass

            return {"path": fpath, "title": title}

        try:
            while count < MAX_PDFS:
                # ── Wait for first message of next batch ──────────────────────
                try:
                    incoming: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                except asyncio.TimeoutError:
                    await editable.edit(
                        f"⏰ **Timeout!** No response for 5 minutes.\n"
                        f"Collected {count} PDF(s). Session ended.\n"
                        "Use /changepcaption to start again."
                    )
                    _cleanup(tmp_dir, collected)
                    return

                # ── /cancel ───────────────────────────────────────────────────
                if incoming.text and incoming.text.strip().lower() == "/cancel":
                    try: await incoming.delete()
                    except Exception: pass
                    await editable.edit("❌ **Cancelled.**")
                    _cleanup(tmp_dir, collected)
                    return

                # ── /Done ─────────────────────────────────────────────────────
                if incoming.text and incoming.text.strip().lower() in ["/done", "done"]:
                    try: await incoming.delete()
                    except Exception: pass
                    if count == 0:
                        await editable.edit(
                            "❌ No PDFs collected.\nUse /changepcaption to start again."
                        )
                        _cleanup(tmp_dir, collected)
                        return
                    break

                # ── Not a PDF — skip ──────────────────────────────────────────
                if not _is_pdf(incoming):
                    continue

                # ── Drain burst: quickly collect all simultaneous messages ─────
                burst = [incoming]
                while count + len(burst) < MAX_PDFS:
                    try:
                        extra: Message = await bot.listen(chat_id, timeout=BURST_DRAIN)
                    except asyncio.TimeoutError:
                        break  # no more arriving — burst complete
                    if extra.text and extra.text.strip().lower() in ["/done", "/cancel", "done"]:
                        burst.append(extra)
                        break
                    burst.append(extra)

                # ── Separate commands from files ──────────────────────────────
                cmd_msg   = None
                file_msgs = []
                for msg in burst:
                    if msg.text:
                        txt = msg.text.strip().lower()
                        if txt in ["/done", "done", "/cancel"]:
                            cmd_msg = msg
                    elif _is_pdf(msg):
                        file_msgs.append(msg)

                # ── Concurrent download of all PDFs in burst ──────────────────
                if file_msgs:
                    slots_left = MAX_PDFS - count
                    to_dl      = file_msgs[:slots_left]

                    start_idx = count + 1
                    tasks     = [
                        download_one(msg, start_idx + i)
                        for i, msg in enumerate(to_dl)
                    ]
                    results = await asyncio.gather(*tasks)

                    for item in results:
                        if item:
                            collected.append(item)
                            count += 1

                    if count >= MAX_PDFS:
                        await editable.edit(
                            f"✅ **{count}/{MAX_PDFS} PDFs received!**\n\n"
                            "Max limit reached. Preparing to re-upload..."
                        )
                    else:
                        await editable.edit(
                            f"📥 **{count}/{MAX_PDFS} PDFs received.**\n\n"
                            "Keep sending or send **/Done** when finished."
                        )

                # ── Handle command found in burst ─────────────────────────────
                if cmd_msg:
                    txt = cmd_msg.text.strip().lower()
                    try: await cmd_msg.delete()
                    except Exception: pass
                    if txt in ["/done", "done"]:
                        if count == 0:
                            await editable.edit(
                                "❌ No PDFs collected.\nUse /changepcaption to start again."
                            )
                            _cleanup(tmp_dir, collected)
                            return
                        break
                    elif txt == "/cancel":
                        await editable.edit("❌ **Cancelled.**")
                        _cleanup(tmp_dir, collected)
                        return

                if count >= MAX_PDFS:
                    try:
                        done_msg: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                        try: await done_msg.delete()
                        except Exception: pass
                    except asyncio.TimeoutError:
                        pass
                    break

        except Exception as e:
            await editable.edit(f"❌ Error during collection: {str(e)[:300]}")
            _cleanup(tmp_dir, collected)
            return

        if not collected:
            await editable.edit("❌ No PDFs collected.")
            _cleanup(tmp_dir, collected)
            return

        # ── Re-upload from disk (concurrent, max 3 at a time) ────────────────
        await editable.edit(
            f"⏳ **Re-uploading {len(collected)} PDF(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        up_sem  = asyncio.Semaphore(3)

        async def upload_one(idx: int, item: dict):
            nonlocal success
            caption = build_pdf_caption(idx, item["title"])
            async with up_sem:
                try:
                    await client.send_document(
                        chat_id  = chat_id,
                        document = item["path"],
                        caption  = caption
                    )
                    success += 1
                except Exception as e:
                    await client.send_message(
                        chat_id, f"⚠️ Failed to send PDF {idx}: {str(e)[:200]}"
                    )

        upload_tasks = [
            upload_one(idx, item)
            for idx, item in enumerate(collected, start=1)
        ]
        await asyncio.gather(*upload_tasks)

        await editable.edit(
            f"✅ **Done! I shared all {success} PDF(s) with new Captions.**\n\n"
            "Now use me again — tap on /changepcaption 📄"
        )
        _cleanup(tmp_dir, collected)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_pdf(m: Message) -> bool:
    if not m.document:
        return False
    fname = m.document.file_name or ""
    mime  = m.document.mime_type or ""
    return fname.lower().endswith(".pdf") or "pdf" in mime.lower()


def _cleanup(tmp_dir: str, collected: list):
    for item in collected:
        try:
            if os.path.exists(item["path"]):
                os.remove(item["path"])
        except Exception:
            pass
    try:
        os.rmdir(tmp_dir)
    except Exception:
        pass

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,
