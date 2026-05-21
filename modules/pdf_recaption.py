"""
pdf_recaption.py — /changepcaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flow:
  1. User sends /changepcaption in group
  2. Bot says: send up to 45 PDFs now
  3. User sends PDFs one by one (bot saves, deletes, counts: X/45)
  4. When user reaches 45 OR sends /Done:
     Bot resends all PDFs in sequence with cc1 caption
  5. Done message + invite to use again
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

import globals
import user_store
from caption_builder import build_pdf_caption, get_title_from_file_or_caption
from vars import AUTH_USERS

MAX_PDFS = 45
TIMEOUT  = 300  # 5 minutes

# ── Per-chat session storage ─────────────────────────────────────────────────
_pdf_sessions: dict = {}

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

        # Start new session
        _pdf_sessions[chat_id] = {"active": True, "pdfs": []}
        await m.delete()

        editable = await client.send_message(
            chat_id,
            "**📄 PDF Caption Change Mode**\n\n"
            f"Send up to **{MAX_PDFS} PDF files** now one by one.\n\n"
            "<blockquote>• I will save each PDF and show count.\n"
            f"• After all PDFs, send **/Done** to re-upload with new captions.\n"
            f"• Or send **/Done** anytime before {MAX_PDFS} to stop early.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        received = []
        count    = 0

        try:
            while count < MAX_PDFS:
                try:
                    incoming: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                except asyncio.TimeoutError:
                    await editable.edit(
                        f"⏰ **Timeout!** No response for 5 minutes.\n"
                        f"Collected {count} PDF(s). Session ended.\n"
                        "Use /changepcaption to start again."
                    )
                    _pdf_sessions.pop(chat_id, None)
                    return

                # Cancel check
                if incoming.text and incoming.text.strip().lower() == "/cancel":
                    await incoming.delete()
                    await editable.edit("❌ **Cancelled.**")
                    _pdf_sessions.pop(chat_id, None)
                    return

                # /Done check
                if incoming.text and incoming.text.strip().lower() in ["/done", "/Done"]:
                    await incoming.delete()
                    if count == 0:
                        await editable.edit("❌ No PDFs collected. Use /changepcaption to start again.")
                        _pdf_sessions.pop(chat_id, None)
                        return
                    break  # proceed to re-upload

                # Accept PDF documents only
                is_pdf = bool(
                    incoming.document and incoming.document.file_name and
                    incoming.document.file_name.lower().endswith(".pdf")
                )
                # Also accept documents with pdf mime type
                if not is_pdf and incoming.document and incoming.document.mime_type:
                    is_pdf = "pdf" in incoming.document.mime_type.lower()

                if not is_pdf:
                    # Not a PDF — ignore, keep listening
                    continue

                fname        = incoming.document.file_name or "document.pdf"
                caption_text = incoming.caption or ""
                title        = get_title_from_file_or_caption(fname, caption_text)

                # Store the message + metadata
                received.append({"msg": incoming, "title": title})
                count += 1

                # Delete user's PDF message (await delete)
                try:
                    await incoming.delete()
                except Exception:
                    pass

                if count >= MAX_PDFS:
                    await editable.edit(
                        f"✅ **{count}/{MAX_PDFS} PDFs received!**\n\n"
                        "You've reached the maximum limit.\n"
                        "Send **/Done** now to re-upload with new captions."
                    )
                else:
                    await editable.edit(
                        f"📥 **{count}/{MAX_PDFS} PDFs received.**\n\n"
                        f"Keep sending or send **/Done** when finished."
                    )

                if count >= MAX_PDFS:
                    # Wait for /Done
                    try:
                        done_msg: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                        if done_msg.text:
                            await done_msg.delete()
                    except asyncio.TimeoutError:
                        pass
                    break

        except Exception as e:
            await editable.edit(f"❌ Error: {str(e)[:300]}")
            _pdf_sessions.pop(chat_id, None)
            return

        # ── Re-upload all PDFs with new cc1 captions ─────────────────────────
        await editable.edit(
            f"⏳ **Re-uploading {count} PDF(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        for idx, item in enumerate(received, start=1):
            orig_msg: Message = item["msg"]
            title             = item["title"]
            caption           = build_pdf_caption(idx, title)

            try:
                await client.copy_message(
                    chat_id      = chat_id,
                    from_chat_id = orig_msg.chat.id if orig_msg.chat else chat_id,
                    message_id   = orig_msg.id,
                    caption      = caption
                )
                success += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                await client.send_message(chat_id, f"⚠️ Failed to send PDF {idx}: {str(e)[:200]}")

        await editable.edit(
            f"✅ **Done! I shared all {success} PDF(s) with new Captions.**\n\n"
            "Now use me again — tap on /changepcaption 📄"
        )
        _pdf_sessions.pop(chat_id, None)

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,
