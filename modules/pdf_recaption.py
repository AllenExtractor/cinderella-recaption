"""
pdf_recaption.py — /changepcaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flow:
  1. User sends /changepcaption in group
  2. Bot says: send up to 45 PDFs now
  3. User sends PDFs — one by one OR multiple at once (all accepted)
     Bot downloads each to disk, deletes from chat, counts: X/45
  4. User sends /Done → Bot re-uploads all from disk with new cc1 captions
  5. Done message + invite to use again

FIXES:
  - NO passive @bot.on_message handler (was breaking all other commands)
  - Uses pyromod listen() in a loop — collects bursts via short sleep window
  - Files downloaded to disk BEFORE delete — so resend never fails
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

MAX_PDFS   = 45
TIMEOUT    = 300    # 5 min wait
BURST_WAIT = 2.5    # seconds to gather simultaneous uploads

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
            f"Send up to **{MAX_PDFS} PDF files** now — you can forward many at once!\n\n"
            "<blockquote>• I will download & delete each PDF, then count.\n"
            f"• Send **/Done** anytime to re-upload with new captions.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        collected: list = []   # { path, title }
        count = 0
        tmp_dir = tempfile.mkdtemp(prefix="cinpdf_")

        try:
            while count < MAX_PDFS:
                # ── Wait for next message ─────────────────────────────────────
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

                # ── Check if it's a PDF ───────────────────────────────────────
                if not _is_pdf(incoming):
                    continue

                # ── Burst collection ──────────────────────────────────────────
                burst = [incoming]
                await asyncio.sleep(BURST_WAIT)

                while count + len(burst) < MAX_PDFS:
                    try:
                        extra: Message = await bot.listen(chat_id, timeout=1)
                    except asyncio.TimeoutError:
                        break
                    if extra.text and extra.text.strip().lower() in ["/done", "/cancel", "done"]:
                        burst.append(extra)
                        break
                    burst.append(extra)

                # ── Process each message in burst ─────────────────────────────
                stop_after = False
                for msg in burst:
                    if count >= MAX_PDFS:
                        break

                    if msg.text:
                        txt = msg.text.strip().lower()
                        if txt in ["/done", "done"]:
                            try: await msg.delete()
                            except Exception: pass
                            stop_after = True
                            break
                        elif txt == "/cancel":
                            try: await msg.delete()
                            except Exception: pass
                            await editable.edit("❌ **Cancelled.**")
                            _cleanup(tmp_dir, collected)
                            return
                        continue

                    if not _is_pdf(msg):
                        continue

                    fname        = msg.document.file_name or "document.pdf"
                    caption_text = msg.caption or ""
                    title        = get_title_from_file_or_caption(fname, caption_text)

                    # ── Download FIRST ────────────────────────────────────────
                    safe = "".join(
                        c if c.isalnum() or c in "._-" else "_"
                        for c in f"{count+1:03d}_{fname}"
                    )
                    fpath = os.path.join(tmp_dir, safe)

                    try:
                        await client.download_media(msg, file_name=fpath)
                    except Exception as dl_err:
                        await client.send_message(
                            chat_id,
                            f"⚠️ Download failed for PDF {count+1}: {str(dl_err)[:150]}"
                        )
                        try: await msg.delete()
                        except Exception: pass
                        continue

                    # ── Delete AFTER download ─────────────────────────────────
                    try:
                        await msg.delete()
                    except Exception:
                        pass

                    collected.append({"path": fpath, "title": title})
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

                if stop_after or count >= MAX_PDFS:
                    break

        except Exception as e:
            await editable.edit(f"❌ Error during collection: {str(e)[:300]}")
            _cleanup(tmp_dir, collected)
            return

        if not collected:
            await editable.edit("❌ No PDFs collected.")
            _cleanup(tmp_dir, collected)
            return

        # ── Re-upload from disk ───────────────────────────────────────────────
        await editable.edit(
            f"⏳ **Re-uploading {len(collected)} PDF(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        for idx, item in enumerate(collected, start=1):
            caption = build_pdf_caption(idx, item["title"])
            try:
                await client.send_document(
                    chat_id  = chat_id,
                    document = item["path"],
                    caption  = caption
                )
                success += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                await client.send_message(
                    chat_id, f"⚠️ Failed to send PDF {idx}: {str(e)[:200]}"
                )

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
