"""
pdf_recaption.py — /changepcaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY APPROACH — NO DOWNLOAD AT ALL:
  Telegram already stores the file on its servers.
  We just save the file_id (a string), delete the message,
  then resend using that file_id — takes ~0 seconds to "save".

Flow:
  1. /changepcaption → session starts
  2. User sends PDFs (one or many at once — all caught via burst drain)
  3. Bot saves file_id instantly, deletes message, counts
  4. /Done → Bot resends all PDFs via file_id with new cc1 captions
  5. Done ✅

SPEED:
  - BURST_DRAIN = 0.003s  — near-instant burst collection
  - No download → "save" is instant (just store file_id string)
  - Resend via file_id = Telegram-server-to-Telegram-server, very fast
  - Concurrent resend with semaphore
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

import globals
import user_store
from caption_builder import build_pdf_caption, get_title_from_file_or_caption
from vars import AUTH_USERS

MAX_PDFS    = 45
TIMEOUT     = 300    # 5 min idle wait
BURST_DRAIN = 0.003  # 3ms — near-instant burst drain

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
            "<blockquote>• PDFs are accepted instantly (no download needed).\n"
            f"• Send **/Done** anytime to re-send with new captions.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        # collected: list of dicts { file_id, title }
        collected: list = []
        count = 0

        try:
            while count < MAX_PDFS:
                # ── Wait for first message ────────────────────────────────────
                try:
                    incoming: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                except asyncio.TimeoutError:
                    await editable.edit(
                        f"⏰ **Timeout!** No response for 5 minutes.\n"
                        f"Collected {count} PDF(s). Session ended.\n"
                        "Use /changepcaption to start again."
                    )
                    return

                # /cancel
                if incoming.text and incoming.text.strip().lower() == "/cancel":
                    try: await incoming.delete()
                    except Exception: pass
                    await editable.edit("❌ **Cancelled.**")
                    return

                # /Done
                if incoming.text and incoming.text.strip().lower() in ["/done", "done"]:
                    try: await incoming.delete()
                    except Exception: pass
                    if count == 0:
                        await editable.edit(
                            "❌ No PDFs collected.\nUse /changepcaption to start again."
                        )
                        return
                    break

                # Not a PDF — skip
                if not _is_pdf(incoming):
                    continue

                # ── Burst drain ───────────────────────────────────────────────
                burst = [incoming]
                while count + len(burst) < MAX_PDFS:
                    try:
                        extra: Message = await bot.listen(chat_id, timeout=BURST_DRAIN)
                    except asyncio.TimeoutError:
                        break
                    if extra.text and extra.text.strip().lower() in ["/done", "/cancel", "done"]:
                        burst.append(extra)
                        break
                    burst.append(extra)

                # ── Separate commands from PDF messages ───────────────────────
                cmd_msg   = None
                file_msgs = []
                for msg in burst:
                    if msg.text:
                        txt = msg.text.strip().lower()
                        if txt in ["/done", "done", "/cancel"]:
                            cmd_msg = msg
                    elif _is_pdf(msg):
                        file_msgs.append(msg)

                # ── Save file_id (INSTANT — no download) ─────────────────────
                for msg in file_msgs:
                    if count >= MAX_PDFS:
                        break

                    file_id  = msg.document.file_id
                    fname    = msg.document.file_name or "document.pdf"
                    title    = get_title_from_file_or_caption(fname, msg.caption or "")

                    # Delete original from chat
                    try:
                        await msg.delete()
                    except Exception:
                        pass

                    collected.append({
                        "file_id":  file_id,
                        "title":    title,
                    })
                    count += 1

                if count >= MAX_PDFS:
                    await editable.edit(
                        f"✅ **{count}/{MAX_PDFS} PDFs received!**\n\n"
                        "Max limit reached. Preparing to re-send..."
                    )
                elif file_msgs:
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
                            return
                        break
                    elif txt == "/cancel":
                        await editable.edit("❌ **Cancelled.**")
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
            return

        if not collected:
            await editable.edit("❌ No PDFs collected.")
            return

        # ── Re-send via file_id (concurrent, max 3 at a time) ────────────────
        await editable.edit(
            f"⏳ **Re-sending {len(collected)} PDF(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        up_sem  = asyncio.Semaphore(3)

        async def send_one(idx: int, item: dict):
            nonlocal success
            caption = build_pdf_caption(idx, item["title"])
            async with up_sem:
                try:
                    await client.send_document(
                        chat_id  = chat_id,
                        document = item["file_id"],
                        caption  = caption
                    )
                    success += 1
                except Exception as e:
                    await client.send_message(
                        chat_id,
                        f"⚠️ Failed to send PDF {idx}: {str(e)[:200]}"
                    )

        await asyncio.gather(*[send_one(i, item) for i, item in enumerate(collected, 1)])

        await editable.edit(
            f"✅ **Done! I shared all {success} PDF(s) with new Captions.**\n\n"
            "Now use me again — tap on /changepcaption 📄"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_pdf(m: Message) -> bool:
    if not m.document:
        return False
    fname = m.document.file_name or ""
    mime  = m.document.mime_type or ""
    return fname.lower().endswith(".pdf") or "pdf" in mime.lower()

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,
