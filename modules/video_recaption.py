"""
video_recaption.py — /changecaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY APPROACH — NO DOWNLOAD AT ALL:
  Telegram already stores the file on its servers.
  We just save the file_id (a string), delete the message,
  then resend using that file_id — takes ~0 seconds to "save".

Flow:
  1. /changecaption → session starts
  2. User sends videos (one or many at once — all caught via burst drain)
  3. Bot saves file_id + metadata instantly, deletes message, counts
  4. /Done → Bot resends all videos via file_id with new cc1 captions
  5. Done ✅

SPEED:
  - BURST_DRAIN = 0.003s  — near-instant burst collection
  - No download → "save" is instant (just store file_id string)
  - Resend via file_id = Telegram-server-to-Telegram-server, very fast
  - Concurrent resend with semaphore

CAPTION ADDITION:
  - Video Duration extracted from msg.video.duration (seconds)
  - Formatted as H:MM:SS and added at TOP of caption
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

import globals
import user_store
from caption_builder import build_video_caption, get_title_from_file_or_caption
from vars import AUTH_USERS

MAX_VIDEOS  = 5000
TIMEOUT     = 300    # 5 min idle wait
BURST_DRAIN = 0.003  # 3ms — near-instant burst drain

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

def _fmt_duration(seconds: int) -> str:
    """Convert seconds → H:MM:SS format. E.g. 6397 → 1:46:37"""
    if not seconds or seconds <= 0:
        return "0:00:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"


def register_video_recaption_handlers(bot: Client):

    @bot.on_message(filters.command("changecaption") & filters.group)
    async def changecaption_cmd(client: Client, m: Message):
        chat_id = m.chat.id
        user_id = m.from_user.id if m.from_user else 0

        if user_id not in AUTH_USERS:
            await m.reply_text(
                f"<blockquote>**🙅 You are not authorized to use this bot🙆🏿‍♀️.**\n"
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
            "**🎥 Video Caption Change Mode**\n\n"
            f"Send up to **{MAX_VIDEOS} videos** now — forward many at once!\n\n"
            "<blockquote>• Videos are accepted instantly (no download needed).\n"
            f"• Send **/Done** anytime to re-send with new captions.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        # collected: list of dicts
        # { file_id, title, ext, is_doc, duration_str }
        collected: list = []
        count = 0

        try:
            while count < MAX_VIDEOS:
                # ── Wait for first message ────────────────────────────────────
                try:
                    incoming: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                except asyncio.TimeoutError:
                    await editable.edit(
                        f"⏰ **Timeout!** No response for 5 minutes.\n"
                        f"Collected {count} video(s). Session ended.\n"
                        "Use /changecaption to start again."
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
                            "❌ No videos collected.\nUse /changecaption to start again."
                        )
                        return
                    break

                # Not a video — skip
                if not _is_video(incoming):
                    continue

                # ── Burst drain: collect all simultaneous messages ─────────────
                burst = [incoming]
                while count + len(burst) < MAX_VIDEOS:
                    try:
                        extra: Message = await bot.listen(chat_id, timeout=BURST_DRAIN)
                    except asyncio.TimeoutError:
                        break
                    if extra.text and extra.text.strip().lower() in ["/done", "/cancel", "done"]:
                        burst.append(extra)
                        break
                    burst.append(extra)

                # ── Separate commands from video messages ─────────────────────
                cmd_msg   = None
                file_msgs = []
                for msg in burst:
                    if msg.text:
                        txt = msg.text.strip().lower()
                        if txt in ["/done", "done", "/cancel"]:
                            cmd_msg = msg
                    elif _is_video(msg):
                        file_msgs.append(msg)

                # ── Save file_id (INSTANT — no download) ─────────────────────
                for msg in file_msgs:
                    if count >= MAX_VIDEOS:
                        break

                    iv = bool(msg.video)

                    if iv:
                        file_id  = msg.video.file_id
                        fname    = msg.video.file_name or "video.mp4"
                        duration = msg.video.duration or 0
                    else:
                        file_id  = msg.document.file_id
                        fname    = msg.document.file_name or "video.mp4"
                        duration = getattr(msg.document, "duration", 0) or 0

                    ext = "mp4"
                    if "." in fname:
                        raw = fname.rsplit(".", 1)[-1].lower()
                        if raw in ["mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "3gp"]:
                            ext = raw

                    title        = get_title_from_file_or_caption(fname, msg.caption or "")
                    duration_str = _fmt_duration(int(duration))

                    # Delete original from chat
                    try:
                        await msg.delete()
                    except Exception:
                        pass

                    collected.append({
                        "file_id":      file_id,
                        "title":        title,
                        "ext":          ext,
                        "is_doc":       not iv,
                        "duration_str": duration_str,
                    })
                    count += 1

                if count >= MAX_VIDEOS:
                    await editable.edit(
                        f"✅ **{count}/{MAX_VIDEOS} videos received!**\n\n"
                        "Max limit reached. Preparing to re-send..."
                    )
                elif file_msgs:
                    await editable.edit(
                        f"📥 **{count}/{MAX_VIDEOS} videos received.**\n\n"
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
                                "❌ No videos collected.\nUse /changecaption to start again."
                            )
                            return
                        break
                    elif txt == "/cancel":
                        await editable.edit("❌ **Cancelled.**")
                        return

                if count >= MAX_VIDEOS:
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
            await editable.edit("❌ No videos collected.")
            return

        # ── Re-send via file_id (concurrent, max 3 at a time) ────────────────
        await editable.edit(
            f"⏳ **Re-sending {len(collected)} video(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        up_sem  = asyncio.Semaphore(3)

        async def send_one(idx: int, item: dict):
            nonlocal success
            caption = build_video_caption(
                idx,
                item["title"],
                item["ext"],
                item["duration_str"]
            )
            async with up_sem:
                try:
                    if item["is_doc"]:
                        await client.send_document(
                            chat_id  = chat_id,
                            document = item["file_id"],
                            caption  = caption
                        )
                    else:
                        await client.send_video(
                            chat_id = chat_id,
                            video   = item["file_id"],
                            caption = caption
                        )
                    success += 1
                except Exception as e:
                    await client.send_message(
                        chat_id,
                        f"⚠️ Failed to send video {idx}: {str(e)[:200]}"
                    )

        await asyncio.gather(*[send_one(i, item) for i, item in enumerate(collected, 1)])

        await editable.edit(
            f"✅ **Done! I shared all {success} video(s) with new Captions.**\n\n"
            "Now use me again — tap on /changecaption 🎯"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_video(m: Message) -> bool:
    if m.video:
        return True
    if m.document and m.document.mime_type and m.document.mime_type.startswith("video/"):
        return True
    return False

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,
