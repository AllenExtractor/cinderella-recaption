"""
video_recaption.py — /changecaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flow:
  1. User sends /changecaption in group
  2. Bot says: send up to 45 videos now
  3. User sends videos one by one (bot saves, deletes, counts: X/45)
  4. When user reaches 45 OR sends /Done:
     Bot resends all videos in sequence with cc1 caption
  5. Done message + invite to use again
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

import globals
import user_store
from caption_builder import build_video_caption, get_title_from_file_or_caption
from vars import AUTH_USERS

MAX_VIDEOS = 45
TIMEOUT    = 300  # 5 minutes

# ── Per-chat session storage ─────────────────────────────────────────────────
# { chat_id: { "active": bool, "videos": [ {"msg": Message, "title": str, "ext": str} ] } }
_video_sessions: dict = {}

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

def register_video_recaption_handlers(bot: Client):

    @bot.on_message(filters.command("changecaption") & filters.group)
    async def changecaption_cmd(client: Client, m: Message):
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
        _video_sessions[chat_id] = {"active": True, "videos": []}
        await m.delete()

        editable = await client.send_message(
            chat_id,
            "**🎥 Video Caption Change Mode**\n\n"
            f"Send up to **{MAX_VIDEOS} videos** now one by one.\n\n"
            "<blockquote>• I will save each video and show count.\n"
            f"• After all videos, send **/Done** to re-upload with new captions.\n"
            f"• Or send **/Done** anytime before {MAX_VIDEOS} to stop early.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        received = []
        count    = 0

        try:
            while count < MAX_VIDEOS:
                try:
                    incoming: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                except asyncio.TimeoutError:
                    await editable.edit(
                        f"⏰ **Timeout!** No response for 5 minutes.\n"
                        f"Collected {count} video(s). Session ended.\n"
                        "Use /changecaption to start again."
                    )
                    _video_sessions.pop(chat_id, None)
                    return

                # Cancel check
                if incoming.text and incoming.text.strip().lower() == "/cancel":
                    await incoming.delete()
                    await editable.edit("❌ **Cancelled.**")
                    _video_sessions.pop(chat_id, None)
                    return

                # /Done check
                if incoming.text and incoming.text.strip().lower() in ["/done", "/Done"]:
                    await incoming.delete()
                    if count == 0:
                        await editable.edit("❌ No videos collected. Use /changecaption to start again.")
                        _video_sessions.pop(chat_id, None)
                        return
                    break  # proceed to re-upload

                # Accept video or document (video file)
                is_video = bool(incoming.video)
                is_doc   = bool(
                    incoming.document and incoming.document.mime_type and
                    incoming.document.mime_type.startswith("video/")
                )

                if not (is_video or is_doc):
                    # Not a video — ignore but keep listening
                    continue

                # Extract title and extension
                if is_video:
                    fname    = incoming.video.file_name or "video.mp4"
                    caption_text = incoming.caption or ""
                else:
                    fname    = incoming.document.file_name or "video.mp4"
                    caption_text = incoming.caption or ""

                import os
                ext = "mp4"
                if "." in fname:
                    raw_ext = fname.rsplit(".", 1)[-1].lower()
                    if raw_ext in ["mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "3gp"]:
                        ext = raw_ext

                title = get_title_from_file_or_caption(fname, caption_text)

                # Store the message object + metadata
                received.append({"msg": incoming, "title": title, "ext": ext})
                count += 1

                # Delete user's video message (await delete)
                try:
                    await incoming.delete()
                except Exception:
                    pass

                if count >= MAX_VIDEOS:
                    await editable.edit(
                        f"✅ **{count}/{MAX_VIDEOS} videos received!**\n\n"
                        "You've reached the maximum limit.\n"
                        "Send **/Done** now to re-upload with new captions."
                    )
                else:
                    await editable.edit(
                        f"📥 **{count}/{MAX_VIDEOS} videos received.**\n\n"
                        f"Keep sending or send **/Done** when finished."
                    )

                if count >= MAX_VIDEOS:
                    # Wait for /Done
                    try:
                        done_msg: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                        if done_msg.text and done_msg.text.strip().lower() in ["/done", "/Done"]:
                            await done_msg.delete()
                        else:
                            await done_msg.delete()
                    except asyncio.TimeoutError:
                        pass
                    break

        except Exception as e:
            await editable.edit(f"❌ Error: {str(e)[:300]}")
            _video_sessions.pop(chat_id, None)
            return

        # ── Re-upload all videos with new cc1 captions ───────────────────────
        await editable.edit(
            f"⏳ **Re-uploading {count} video(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        for idx, item in enumerate(received, start=1):
            orig_msg: Message = item["msg"]
            title             = item["title"]
            ext               = item["ext"]
            caption           = build_video_caption(idx, title, ext)

            try:
                await client.copy_message(
                    chat_id       = chat_id,
                    from_chat_id  = orig_msg.chat.id if orig_msg.chat else chat_id,
                    message_id    = orig_msg.id,
                    caption       = caption
                )
                success += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                await client.send_message(chat_id, f"⚠️ Failed to send video {idx}: {str(e)[:200]}")

        await editable.edit(
            f"✅ **Done! I shared all {success} video(s) with new Captions.**\n\n"
            "Now use me again — tap on /changecaption 🎯"
        )
        _video_sessions.pop(chat_id, None)

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,
