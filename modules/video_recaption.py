"""
video_recaption.py — /changecaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flow:
  1. User sends /changecaption in group
  2. Bot says: send up to 45 videos now
  3. User sends videos (one by one OR multiple at once — all accepted)
     Bot downloads each to disk, deletes from chat, counts: X/45
  4. When user reaches 45 OR sends /Done:
     Bot re-uploads all videos from disk with new cc1 captions
  5. Done message + invite to use again

FIXES:
  - Multiple simultaneous files: event-based listener with 2s batching window
  - Empty messages / copy_message fail: files downloaded to disk first,
    then deleted, then re-uploaded via send_video/send_document from disk
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import os
import tempfile

from pyrogram import Client, filters
from pyrogram.types import Message

import globals
import user_store
from caption_builder import build_video_caption, get_title_from_file_or_caption
from vars import AUTH_USERS

MAX_VIDEOS = 45
TIMEOUT    = 300   # 5 min idle wait for new file / /Done
BATCH_WAIT = 2.5   # seconds to wait for more files after last received

# ── Per-chat session storage ──────────────────────────────────────────────────
# { chat_id: { "active": bool, "queue": asyncio.Queue } }
_video_sessions: dict = {}

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

def register_video_recaption_handlers(bot: Client):

    # ── Passive event handler — feeds queue for any active session ────────────
    @bot.on_message(filters.group)
    async def _video_feed(client: Client, m: Message):
        chat_id = m.chat.id
        session = _video_sessions.get(chat_id)
        if session and session.get("active"):
            await session["queue"].put(m)

    # ── /changecaption command ────────────────────────────────────────────────
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

        # Start new session with a queue
        q: asyncio.Queue = asyncio.Queue()
        _video_sessions[chat_id] = {"active": True, "queue": q}
        await m.delete()

        editable = await client.send_message(
            chat_id,
            "**🎥 Video Caption Change Mode**\n\n"
            f"Send up to **{MAX_VIDEOS} videos** now — you can send many at once!\n\n"
            "<blockquote>• I will download each video, delete from chat, and count.\n"
            f"• After all videos, send **/Done** to re-upload with new captions.\n"
            f"• Or send **/Done** anytime before {MAX_VIDEOS} to stop early.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        # ── collected: list of dicts { path, title, ext, is_doc } ────────────
        collected: list = []
        count = 0
        tmp_dir = tempfile.mkdtemp(prefix="cinderella_vid_")

        try:
            while count < MAX_VIDEOS:
                # ── Wait for next item (with timeout) ────────────────────────
                try:
                    incoming: Message = await asyncio.wait_for(q.get(), timeout=TIMEOUT)
                except asyncio.TimeoutError:
                    await editable.edit(
                        f"⏰ **Timeout!** No response for 5 minutes.\n"
                        f"Collected {count} video(s). Session ended.\n"
                        "Use /changecaption to start again."
                    )
                    _video_sessions.pop(chat_id, None)
                    _cleanup(tmp_dir, collected)
                    return

                # ── /cancel ───────────────────────────────────────────────────
                if incoming.text and incoming.text.strip().lower() == "/cancel":
                    try: await incoming.delete()
                    except Exception: pass
                    await editable.edit("❌ **Cancelled.**")
                    _video_sessions.pop(chat_id, None)
                    _cleanup(tmp_dir, collected)
                    return

                # ── /Done ─────────────────────────────────────────────────────
                if incoming.text and incoming.text.strip().lower() in ["/done", "done"]:
                    try: await incoming.delete()
                    except Exception: pass
                    if count == 0:
                        await editable.edit("❌ No videos collected. Use /changecaption to start again.")
                        _video_sessions.pop(chat_id, None)
                        _cleanup(tmp_dir, collected)
                        return
                    break  # proceed to re-upload

                # ── Detect video/doc ──────────────────────────────────────────
                is_video = bool(incoming.video)
                is_doc   = bool(
                    incoming.document and incoming.document.mime_type and
                    incoming.document.mime_type.startswith("video/")
                )

                if not (is_video or is_doc):
                    continue  # ignore non-video messages

                # ── Drain queue: collect all files that arrived simultaneously ─
                # Add this message to a local batch first
                batch = [incoming]
                await asyncio.sleep(BATCH_WAIT)   # wait for simultaneous uploads
                while not q.empty():
                    extra = q.get_nowait()
                    # If it's /Done or /cancel, put back and stop draining
                    if extra.text and extra.text.strip().lower() in ["/done", "/cancel", "done"]:
                        await q.put(extra)
                        break
                    ev = bool(extra.video)
                    ed = bool(
                        extra.document and extra.document.mime_type and
                        extra.document.mime_type.startswith("video/")
                    )
                    if ev or ed:
                        batch.append(extra)

                # ── Process each message in batch ─────────────────────────────
                for msg in batch:
                    if count >= MAX_VIDEOS:
                        break

                    iv = bool(msg.video)
                    id_ = bool(
                        msg.document and msg.document.mime_type and
                        msg.document.mime_type.startswith("video/")
                    )

                    if not (iv or id_):
                        continue

                    fname        = (msg.video.file_name if iv else msg.document.file_name) or "video.mp4"
                    caption_text = msg.caption or ""

                    ext = "mp4"
                    if "." in fname:
                        raw_ext = fname.rsplit(".", 1)[-1].lower()
                        if raw_ext in ["mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "3gp"]:
                            ext = raw_ext

                    title = get_title_from_file_or_caption(fname, caption_text)

                    # ── Download to disk FIRST ────────────────────────────────
                    safe_name = f"{count+1:03d}_{fname}"
                    # Sanitize filename
                    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in safe_name)
                    file_path = os.path.join(tmp_dir, safe_name)

                    try:
                        await client.download_media(msg, file_name=file_path)
                    except Exception as dl_err:
                        await client.send_message(chat_id, f"⚠️ Download failed for video {count+1}: {str(dl_err)[:200]}")
                        try: await msg.delete()
                        except Exception: pass
                        continue

                    # ── Delete from chat AFTER download ───────────────────────
                    try:
                        await msg.delete()
                    except Exception:
                        pass

                    collected.append({
                        "path":   file_path,
                        "title":  title,
                        "ext":    ext,
                        "is_doc": id_
                    })
                    count += 1

                    if count >= MAX_VIDEOS:
                        await editable.edit(
                            f"✅ **{count}/{MAX_VIDEOS} videos received!**\n\n"
                            "You've reached the maximum limit.\n"
                            "Send **/Done** now to re-upload with new captions."
                        )
                    else:
                        await editable.edit(
                            f"📥 **{count}/{MAX_VIDEOS} videos received.**\n\n"
                            "Keep sending or send **/Done** when finished."
                        )

                # ── If reached MAX — wait for /Done then break ─────────────
                if count >= MAX_VIDEOS:
                    try:
                        done_msg: Message = await asyncio.wait_for(q.get(), timeout=TIMEOUT)
                        try: await done_msg.delete()
                        except Exception: pass
                    except asyncio.TimeoutError:
                        pass
                    break

        except Exception as e:
            await editable.edit(f"❌ Error: {str(e)[:300]}")
            _video_sessions.pop(chat_id, None)
            _cleanup(tmp_dir, collected)
            return

        _video_sessions.pop(chat_id, None)

        if not collected:
            await editable.edit("❌ No videos to re-upload.")
            _cleanup(tmp_dir, collected)
            return

        # ── Re-upload all videos from disk with new captions ─────────────────
        await editable.edit(
            f"⏳ **Re-uploading {len(collected)} video(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        for idx, item in enumerate(collected, start=1):
            fpath  = item["path"]
            title  = item["title"]
            ext    = item["ext"]
            is_doc = item["is_doc"]
            caption = build_video_caption(idx, title, ext)

            try:
                if is_doc:
                    await client.send_document(
                        chat_id   = chat_id,
                        document  = fpath,
                        caption   = caption
                    )
                else:
                    await client.send_video(
                        chat_id = chat_id,
                        video   = fpath,
                        caption = caption
                    )
                success += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                await client.send_message(chat_id, f"⚠️ Failed to send video {idx}: {str(e)[:200]}")

        await editable.edit(
            f"✅ **Done! I shared all {success} video(s) with new Captions.**\n\n"
            "Now use me again — tap on /changecaption 🎯"
        )
        _cleanup(tmp_dir, collected)


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
