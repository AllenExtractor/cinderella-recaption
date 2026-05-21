"""
main.py — Cinderella PVC Bot (PDF Video Caption Bot)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Commands (GROUP only):
  /start         — Welcome message with image, feature list & buttons
  /changecaption — Recaption up to 5000 videos with cc1 style
  /changepcaption— Recaption up to 5000 PDFs with cc1 style
  /setbatch      — Set global batch name (global settings)
  /setcredit     — Set global credit name (global settings)
  /viewsettings  — View current global settings

Commands (PRIVATE, OWNER only):
  /broadcast     — Broadcast to all users/groups
  /broadusers    — View all registered users/groups

NOTE: Bot works ONLY in group chats (except broadcast commands).
Bot must be admin with full rights in the group.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import random
import asyncio
import threading

from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from pyromod import listen

import globals
import user_store
from vars import API_ID, API_HASH, BOT_TOKEN, OWNER, CREDIT, AUTH_USERS, TOTAL_USERS
from video_recaption import register_video_recaption_handlers
from pdf_recaption   import register_pdf_recaption_handlers
from settings        import register_settings_handlers
from broadcast       import register_broadcast_handlers

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

# ── Random image list ────────────────────────────────────────────────────────
image_list = [
    "https://graph.org/file/417cc7326cab9036c0152-f6a281db2a6975dfa9.jpg",
    "https://graph.org/file/033121ad32291bcaddd01-d91ae4a1f7ca9378fc.jpg",
    "https://graph.org/file/45f48779e0aa39709d1e8-4c024567d60f6ec5c2.jpg",
    "https://graph.org/file/6ccdd92af77784c9d367e-a4ba6f10456656bbbd.jpg",
    "https://graph.org/file/b23084c3e9124e14e18ec-d385f8f9c8b1635a2e.jpg",
    "https://graph.org/file/29c4511ee7a4653d22fe1-67906a2a8392895644.jpg",
    "https://graph.org/file/b45300f1cd068ad8f1895-fa23a3a1ad25789597.jpg",
]

# ── Initialize bot ────────────────────────────────────────────────────────────
bot = Client(
    "cinderella_pvc_bot",
    api_id    = API_ID,
    api_hash  = API_HASH,
    bot_token = BOT_TOKEN
)

# ── Start keyboard (with feature list & buttons) ─────────────────────────────
def get_start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Change Video Caption", switch_inline_query_current_chat="/changecaption")],
        [InlineKeyboardButton("📄 Change PDF Caption",   switch_inline_query_current_chat="/changepcaption")],
        [InlineKeyboardButton("⚙️ Set Batch Name",        switch_inline_query_current_chat="/setbatch"),
         InlineKeyboardButton("💳 Set Credit",            switch_inline_query_current_chat="/setcredit")],
        [InlineKeyboardButton("📊 View Settings",         switch_inline_query_current_chat="/viewsettings")],
        [InlineKeyboardButton("📢 Help & Info",           callback_data="help_info")],
        [InlineKeyboardButton("🔍 Developer", url="https://t.me/CinderellaContactBot"),
         InlineKeyboardButton("👑 Owner",     url="https://t.me/MR_Toxic_1")],
    ])

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

@bot.on_message(filters.command("start"))
async def start_cmd(client: Client, m: Message):
    user_id = m.from_user.id if m.from_user else 0

    # Register user
    user_store.register_user(user_id)
    if user_id not in TOTAL_USERS:
        TOTAL_USERS.append(user_id)

    # If in group — register group too
    if m.chat.id != user_id:
        user_store.register_group(m.chat.id)

    is_auth = user_id in AUTH_USERS
    first   = m.from_user.first_name if m.from_user else "Friend"

    if is_auth:
        caption = (
            f"**Hello Dear 👑 {first}!**\n\n"
            f"➠ I am **Cinderella PVC Bot** (PDF-Video-Caption Bot)\n\n"
            f"**✨ What I can do:**\n"
            f"• 🎥 `/changecaption` — Re-caption up to **5000 videos** at once\n"
            f"• 📄 `/changepcaption` — Re-caption up to **5000 PDFs** at once\n"
            f"• ⚙️ `/setbatch` — Set global **Batch Name**\n"
            f"• 💳 `/setcredit` — Set global **Credit Name**\n"
            f"• 📊 `/viewsettings` — View current settings\n\n"
            f"<blockquote>⚠️ All commands work in **Group Chat only**.\n"
            f"Bot must be **Admin** with full rights in the group.</blockquote>\n\n"
            f"➠ Made By : [{CREDIT}](tg://openmessage?user_id={OWNER}) 🦁"
        )
    else:
        caption = (
            f"**Hello 🫣 {first}!**\n\n"
            f"➠ I am **Cinderella PVC Bot** (PDF Video Caption Bot)\n\n"
            f"I can **re-caption videos and PDFs** with a beautiful cc1-style caption!\n\n"
            f"**Features:**\n"
            f"• 🎥 Bulk Video Caption Change (up to 5000 videos)\n"
            f"• 📄 Bulk PDF Caption Change (up to 5000 PDFs)\n"
            f"• ⚙️ Global Settings: Batch Name & Credit Name\n\n"
            f"<blockquote>You are currently **not authorized**.\n"
            f"Contact the owner to get access.\n"
            f"Your User ID: `{user_id}`</blockquote>\n\n"
            f"💬 Contact: [{CREDIT}](tg://openmessage?user_id={OWNER}) 🔓"
        )

    await client.send_photo(
        chat_id      = m.chat.id,
        photo        = random.choice(image_list),
        caption      = caption,
        reply_markup = get_start_keyboard()
    )

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

@bot.on_callback_query(filters.regex("help_info"))
async def help_info_cb(client, callback_query):
    text = (
        "**📖 Cinderella PVC Bot — Help**\n\n"
        "**Group Commands (Auth Users):**\n"
        "• `/changecaption` — Bulk recaption videos (max 5000)\n"
        "• `/changepcaption` — Bulk recaption PDFs (max 5000)\n"
        "• `/setbatch` — Set global batch name\n"
        "• `/setcredit` — Set global credit name\n"
        "• `/viewsettings` — View current settings\n\n"
        "**Private Commands (Owner only):**\n"
        "• `/broadcast` — Broadcast a message\n"
        "• `/broadusers` — View all users/groups\n\n"
        "<blockquote>⚠️ Bot must be **Admin** in group with full rights.\n"
        "All group commands work in group chat only.</blockquote>"
    )
    await callback_query.message.edit_caption(
        caption      = text,
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
        ])
    )
    await callback_query.answer()

@bot.on_callback_query(filters.regex("back_home"))
async def back_home_cb(client, callback_query):
    first = callback_query.from_user.first_name if callback_query.from_user else "Friend"
    caption = (
        f"**Hello 👑 {first}!**\n\n"
        f"➠ I am **Cinderella PVC Bot** (PDF Video Caption Bot)\n\n"
        f"Use the buttons below to get started!\n\n"
        f"➠ Made By : [{CREDIT}](tg://openmessage?user_id={OWNER}) 🦁"
    )
    try:
        await callback_query.message.edit_media(
            InputMediaPhoto(
                media   = random.choice(image_list),
                caption = caption
            ),
            reply_markup=get_start_keyboard()
        )
    except Exception:
        await callback_query.message.edit_caption(
            caption      = caption,
            reply_markup = get_start_keyboard()
        )
    await callback_query.answer()

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,
# ── Register all handlers ────────────────────────────────────────────────────
register_video_recaption_handlers(bot)
register_pdf_recaption_handlers(bot)
register_settings_handlers(bot)
register_broadcast_handlers(bot)

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,
# ── Flask web server (for Render.com free web service) ───────────────────────
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return """
<!DOCTYPE html>
<html>
<body style="background:#0d0d0d;color:#fff;font-family:monospace;text-align:center;padding:60px">
  <pre style="color:#e040fb;font-size:14px">
 ██████╗██╗███╗   ██╗██████╗ ███████╗██████╗ ███████╗██╗     ██╗      █████╗ 
██╔════╝██║████╗  ██║██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██║     ██╔══██╗
██║     ██║██╔██╗ ██║██║  ██║█████╗  ██████╔╝█████╗  ██║     ██║     ███████║
██║     ██║██║╚██╗██║██║  ██║██╔══╝  ██╔══██╗██╔══╝  ██║     ██║     ██╔══██║
╚██████╗██║██║ ╚████║██████╔╝███████╗██║  ██║███████╗███████╗███████╗██║  ██║
 ╚═════╝╚═╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝
  </pre>
  <h2 style="color:#e040fb">Cinderella PVC Bot — Running ✅</h2>
  <p style="color:#aaa">PDF · Video · Caption Bot</p>
  <p style="color:#666">Powered by Team★Toxic</p>
</body>
</html>
"""

@flask_app.route("/health")
def health():
    return {"status": "ok", "bot": "Cinderella PVC Bot"}, 200

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

def run_flask():
    # Only run Flask internally if NOT launched by gunicorn
    # (Dockerfile CMD runs gunicorn for Flask + python3 main.py for bot separately)
    # When gunicorn is used, PORT is already bound — skip Flask thread to avoid conflict
    port = int(os.environ.get("PORT", 8000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

if __name__ == "__main__":
    # Dockerfile runs gunicorn for Flask on $PORT separately.
    # main.py is started as the bot worker — do NOT start Flask here to avoid port conflict.
    # Only start Flask thread if running standalone (no gunicorn in env).
    import sys
    running_under_gunicorn = "gunicorn" in sys.modules or os.environ.get("SERVER_SOFTWARE", "").startswith("gunicorn")

    if not running_under_gunicorn:
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print(f"[PVC Bot] Flask web server started on port {os.environ.get('PORT', 8000)}")
    else:
        print("[PVC Bot] Gunicorn detected — skipping internal Flask server to avoid port conflict.")

    # Run Pyrogram bot (blocking)
    print("[PVC Bot] Starting Cinderella PVC Bot...")
    bot.run()
