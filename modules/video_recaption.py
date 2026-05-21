"""
video_recaption.py — /changecaption command
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flow:
  1. User sends /changecaption in group
  2. Bot says: send up to 45 videos now
  3. User sends videos — one by one OR multiple at once (all accepted)
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
from caption_builder import build_video_caption, get_title_from_file_or_caption
from vars import AUTH_USERS

MAX_VIDEOS = 45
TIMEOUT    = 300    # 5 min wait for next message
BURST_WAIT = 2.5    # seconds to wait for more files in same burst

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

        await m.delete()

        editable = await client.send_message(
            chat_id,
            "**🎥 Video Caption Change Mode**\n\n"
            f"Send up to **{MAX_VIDEOS} videos** now — you can forward many at once!\n\n"
            "<blockquote>• I will download & delete each video, then count.\n"
            f"• Send **/Done** anytime to re-upload with new captions.\n"
            "• Send /cancel to abort.</blockquote>"
        )

        collected: list = []   # { path, title, ext, is_doc }
        count = 0
        tmp_dir = tempfile.mkdtemp(prefix="cinvid_")

        try:
            while count < MAX_VIDEOS:
                # ── Wait for next message ─────────────────────────────────────
                try:
                    incoming: Message = await bot.listen(chat_id, timeout=TIMEOUT)
                except asyncio.TimeoutError:
                    await editable.edit(
                        f"⏰ **Timeout!** No response for 5 minutes.\n"
                        f"Collected {count} video(s). Session ended.\n"
                        "Use /changecaption to start again."
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
                            "❌ No videos collected.\nUse /changecaption to start again."
                        )
                        _cleanup(tmp_dir, collected)
                        return
                    break

                # ── Check if it's a video/video-doc ──────────────────────────
                if not _is_video(incoming):
                    continue

                # ── Burst collection: gather simultaneous uploads ─────────────
                # Build a small list starting with this message
                burst = [incoming]
                await asyncio.sleep(BURST_WAIT)

                # Drain any messages that arrived during the sleep
                # We use a helper coroutine that peeks with a short timeout
                while count + len(burst) < MAX_VIDEOS:
                    try:
                        extra: Message = await bot.listen(chat_id, timeout=1)
                    except asyncio.TimeoutError:
                        break  # no more in burst
                    # If it's /Done or /cancel, put it back via a re-listen trick
                    # We can't "unget" from pyromod, so handle it now
                    if extra.text and extra.text.strip().lower() in ["/done", "/cancel", "done"]:
                        # Process the burst we have, then handle this command next loop
                        # We do this by breaking and storing command for next iteration
                        burst.append(extra)  # will be caught as non-video, handled below
                        break
                    burst.append(extra)

                # ── Process each message in burst ─────────────────────────────
                stop_after = False
                for msg in burst:
                    if count >= MAX_VIDEOS:
                        break

                    # If this is a command message (got mixed in from burst drain)
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

                    if not _is_video(msg):
                        continue

                    iv   = bool(msg.video)
                    fname        = (msg.video.file_name if iv else msg.document.file_name) or "video.mp4"
                    caption_text = msg.caption or ""

                    ext = "mp4"
                    if "." in fname:
                        raw_ext = fname.rsplit(".", 1)[-1].lower()
                        if raw_ext in ["mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "3gp"]:
                            ext = raw_ext

                    title = get_title_from_file_or_caption(fname, caption_text)

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
                            f"⚠️ Download failed for video {count+1}: {str(dl_err)[:150]}"
                        )
                        try: await msg.delete()
                        except Exception: pass
                        continue

                    # ── Delete from chat AFTER download ───────────────────────
                    try:
                        await msg.delete()
                    except Exception:
                        pass

                    is_doc = not bool(msg.video)
                    collected.append({"path": fpath, "title": title, "ext": ext, "is_doc": is_doc})
                    count += 1

                    if count >= MAX_VIDEOS:
                        await editable.edit(
                            f"✅ **{count}/{MAX_VIDEOS} videos received!**\n\n"
                            "Max limit reached. Preparing to re-upload..."
                        )
                    else:
                        await editable.edit(
                            f"📥 **{count}/{MAX_VIDEOS} videos received.**\n\n"
                            "Keep sending or send **/Done** when finished."
                        )

                if stop_after or count >= MAX_VIDEOS:
                    break

        except Exception as e:
            await editable.edit(f"❌ Error during collection: {str(e)[:300]}")
            _cleanup(tmp_dir, collected)
            return

        if not collected:
            await editable.edit("❌ No videos collected.")
            _cleanup(tmp_dir, collected)
            return

        # ── Re-upload from disk ───────────────────────────────────────────────
        await editable.edit(
            f"⏳ **Re-uploading {len(collected)} video(s) with new captions...**\n"
            "Please wait."
        )

        success = 0
        for idx, item in enumerate(collected, start=1):
            caption = build_video_caption(idx, item["title"], item["ext"])
            try:
                if item["is_doc"]:
                    await client.send_document(
                        chat_id  = chat_id,
                        document = item["path"],
                        caption  = caption
                    )
                else:
                    await client.send_video(
                        chat_id = chat_id,
                        video   = item["path"],
                        caption = caption
                    )
                success += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                await client.send_message(
                    chat_id, f"⚠️ Failed to send video {idx}: {str(e)[:200]}"
                )

        await editable.edit(
            f"✅ **Done! I shared all {success} video(s) with new Captions.**\n\n"
            "Now use me again — tap on /changecaption 🎯"
        )
        _cleanup(tmp_dir, collected)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_video(m: Message) -> bool:
    if m.video:
        return True
    if m.document and m.document.mime_type and m.document.mime_type.startswith("video/"):
        return True
    return False


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
