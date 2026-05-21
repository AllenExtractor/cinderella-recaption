"""
pdf_recaption.py — /changepcaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flow:
  1. User sends /changepcaption in group
  2. Bot says: send up to 45 PDFs now
  3. User sends PDFs (one by one OR multiple at once — all accepted)
     Bot downloads each to disk, deletes from chat, counts: X/45
  4. When user reaches 45 OR sends /Done:
     Bot re-uploads all PDFs from disk with new cc1 captions
  5. Done message + invite to use again

FIXES:
  - Multiple simultaneous files: event-based listener with 2s batching window
  - Empty messages / copy_message fail: files downloaded to disk first,
    then deleted, then re-uploaded via send_document from disk
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
TIMEOUT    = 300   # 5 min idle wait
BATCH_WAIT = 2.5   # seconds to wait for more files after last received

# ── Per-chat session storage ──────────────────────────────────────────────────
_pdf_sessions: dict = {}

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

def register_pdf_recaption_handlers(bot: Client):

    # ── Passive event handler — feeds queue for any active session ────────────
    @bot.on_message(filters.group)
    async def _pdf_feed(client: Client, m: Message):
        chat_id = m.chat.id
        session = _pdf_sessions.get(chat_id)
        if session and session.get("active"):
            await session["queue"].put(m)

    # ── /changepcaption command ───────────────────────────────────────────────
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

        # Start new session with a queue
        q: asyncio.Queue = asyncio.Queue()
        _pdf_sessions[chat_id] = {"active": True, "queue": q}
        await m.delete()

        editable = await client.send_message(
            chat_id,
            "**📄 PDF Caption Change Mode**\n\n"
            f"Send up to **{MAX_PDFS} PDF files** now — you can send many at once!\n\n"
            "<blockquote>• I will download each PDF, delete from chat, and count.\n"
            f"• After all PDFs, send **/Done** to re-upload with new captions.\n"
            f"• Or send **/Done** anytime before {MAX_PDFS} to stop early.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        # ── collected: list of dicts { path, title } ─────────────────────────
        collected: list = []
        count = 0
        tmp_dir = tempfile.mkdtemp(prefix="cinderella_pdf_")

        try:
            while count < MAX_PDFS:
                # ── Wait for next item (with timeout) ────────────────────────
                try:
                    incoming: Message = await asyncio.wait_for(q.get(), timeout=TIMEOUT)
                except asyncio.TimeoutError:
                    await editable.edit(
                        f"⏰ **Timeout!** No response for 5 minutes.\n"
                        f"Collected {count} PDF(s). Session ended.\n"
                        "Use /changepcaption to start again."
                    )
                    _pdf_sessions.pop(chat_id, None)
                    _cleanup(tmp_dir, collected)
                    return

                # ── /cancel ───────────────────────────────────────────────────
                if incoming.text and incoming.text.strip().lower() == "/cancel":
                    try: await incoming.delete()
                    except Exception: pass
                    await editable.edit("❌ **Cancelled.**")
                    _pdf_sessions.pop(chat_id, None)
                    _cleanup(tmp_dir, collected)
                    return

                # ── /Done ─────────────────────────────────────────────────────
                if incoming.text and incoming.text.strip().lower() in ["/done", "done"]:
                    try: await incoming.delete()
                    except Exception: pass
                    if count == 0:
                        await editable.edit("❌ No PDFs collected. Use /changepcaption to start again.")
                        _pdf_sessions.pop(chat_id, None)
                        _cleanup(tmp_dir, collected)
                        return
                    break  # proceed to re-upload

                # ── Check if it's a PDF ───────────────────────────────────────
                if not _is_pdf(incoming):
                    continue  # ignore non-PDF messages

                # ── Drain queue: collect all files that arrived simultaneously ─
                batch = [incoming]
                await asyncio.sleep(BATCH_WAIT)   # wait for simultaneous uploads
                while not q.empty():
                    extra = q.get_nowait()
                    if extra.text and extra.text.strip().lower() in ["/done", "/cancel", "done"]:
                        await q.put(extra)
                        break
                    if _is_pdf(extra):
                        batch.append(extra)

                # ── Process each message in batch ─────────────────────────────
                for msg in batch:
                    if count >= MAX_PDFS:
                        break

                    if not _is_pdf(msg):
                        continue

                    fname        = msg.document.file_name or "document.pdf"
                    caption_text = msg.caption or ""
                    title        = get_title_from_file_or_caption(fname, caption_text)

                    # ── Download to disk FIRST ────────────────────────────────
                    safe_name = f"{count+1:03d}_{fname}"
                    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in safe_name)
                    file_path = os.path.join(tmp_dir, safe_name)

                    try:
                        await client.download_media(msg, file_name=file_path)
                    except Exception as dl_err:
                        await client.send_message(chat_id, f"⚠️ Download failed for PDF {count+1}: {str(dl_err)[:200]}")
                        try: await msg.delete()
                        except Exception: pass
                        continue

                    # ── Delete from chat AFTER download ───────────────────────
                    try:
                        await msg.delete()
                    except Exception:
                        pass

                    collected.append({
                        "path":  file_path,
                        "title": title
                    })
                    count += 1

                    if count >= MAX_PDFS:
                        await editable.edit(
                            f"✅ **{count}/{MAX_PDFS} PDFs received!**\n\n"
                            "You've reached the maximum limit.\n"
                            "Send **/Done** now to re-upload with new captions."
                        )
                    else:
                        await editable.edit(
                            f"📥 **{count}/{MAX_PDFS} PDFs received.**\n\n"
                            "Keep sending or send **/Done** when finished."
                        )

                # ── If reached MAX — wait for /Done then break ─────────────
                if count >= MAX_PDFS:
                    try:
                        done_msg: Message = await asyncio.wait_for(q.get(), timeout=TIMEOUT)
                        try: await done_msg.delete()
                        except Exception: pass
                    except asyncio.TimeoutError:
                        pass
                    break

        except Exception as e:
            await editable.edit(f"❌ Error: {str(e)[:300]}")
            _pdf_sessions.pop(chat_id, None)
            _cleanup(tmp_dir, collected)
            return

        _pdf_sessions.pop(chat_id, None)

        if not collected:
            await editable.edit("❌ No PDFs to re-upload.")
            _cleanup(tmp_dir, collected)
            return

        # ── Re-upload all PDFs from disk with new captions ───────────────────
        await editable.edit(
            f"⏳ **Re-uploading {len(collected)} PDF(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        for idx, item in enumerate(collected, start=1):
            fpath   = item["path"]
            title   = item["title"]
            caption = build_pdf_caption(idx, title)

            try:
                await client.send_document(
                    chat_id  = chat_id,
                    document = fpath,
                    caption  = caption
                )
                success += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                await client.send_message(chat_id, f"⚠️ Failed to send PDF {idx}: {str(e)[:200]}")

        await editable.edit(
            f"✅ **Done! I shared all {success} PDF(s) with new Captions.**\n\n"
            "Now use me again — tap on /changepcaption 📄"
        )
        _cleanup(tmp_dir, collected)


def _is_pdf(m: Message) -> bool:
    """Return True if the message contains a PDF document."""
    if not m.document:
        return False
    fname = m.document.file_name or ""
    mime  = m.document.mime_type or ""
    return fname.lower().endswith(".pdf") or "pdf" in mime.lower()


def _cleanup(tmp_dir: str, collected: list):
    """Remove downloaded temp files."""
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
