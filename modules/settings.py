"""
settings.py — Global Settings for Cinderella PVC Bot
Commands (group only, AUTH_USERS only):
  /setbatch   — Set global batch name
  /setcredit  — Set global credit name
  /viewsettings — Show current settings
"""

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

import globals
from vars import AUTH_USERS, CREDIT

TIMEOUT = 300

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

def register_settings_handlers(bot: Client):

    @bot.on_message(filters.command("setbatch") & filters.group)
    async def setbatch_cmd(client: Client, m: Message):
        user_id = m.from_user.id if m.from_user else 0
        if user_id not in AUTH_USERS:
            await m.reply_text(f"<blockquote>🙅 Not authorized. Your ID: `{user_id}`</blockquote>")
            return

        await m.delete()
        editable = await client.send_message(
            m.chat.id,
            "**⚙️ Set Batch Name**\n\n"
            "Send the **Batch Name** you want to use for all videos and PDFs.\n"
            "<blockquote>This will be saved globally and applied to all re-captioned files.\n"
            "Send /cancel to abort.</blockquote>"
        )

        try:
            reply: Message = await bot.listen(m.chat.id, timeout=TIMEOUT)
        except asyncio.TimeoutError:
            await editable.edit("⏰ Timeout. Use /setbatch to try again.")
            return

        if reply.text and reply.text.strip().lower() == "/cancel":
            await reply.delete()
            await editable.edit("❌ Cancelled.")
            return

        new_batch = reply.text.strip() if reply.text else ""
        await reply.delete()

        if not new_batch:
            await editable.edit("❌ Empty input. Use /setbatch to try again.")
            return

        globals.set_setting("batch_name", new_batch)
        await editable.edit(
            f"✅ **Batch Name updated!**\n\n"
            f"<blockquote>📚 New Batch Name:\n`{new_batch}`</blockquote>"
        )

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

    @bot.on_message(filters.command("setcredit") & filters.group)
    async def setcredit_cmd(client: Client, m: Message):
        user_id = m.from_user.id if m.from_user else 0
        if user_id not in AUTH_USERS:
            await m.reply_text(f"<blockquote>🙅 Not authorized. Your ID: `{user_id}`</blockquote>")
            return

        await m.delete()
        editable = await client.send_message(
            m.chat.id,
            "**⚙️ Set Credit Name**\n\n"
            "Send the **Credit Name** to appear in all captions.\n"
            "<blockquote>Tip: Use `Text|https://url` format for a hyperlink credit.\n"
            "Send /cancel to abort.</blockquote>"
        )

        try:
            reply: Message = await bot.listen(m.chat.id, timeout=TIMEOUT)
        except asyncio.TimeoutError:
            await editable.edit("⏰ Timeout. Use /setcredit to try again.")
            return

        if reply.text and reply.text.strip().lower() == "/cancel":
            await reply.delete()
            await editable.edit("❌ Cancelled.")
            return

        new_credit = reply.text.strip() if reply.text else ""
        await reply.delete()

        if not new_credit:
            await editable.edit("❌ Empty input. Use /setcredit to try again.")
            return

        globals.set_setting("credit_name", new_credit)
        await editable.edit(
            f"✅ **Credit Name updated!**\n\n"
            f"<blockquote>📥 New Credit:\n`{new_credit}`</blockquote>"
        )

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

    @bot.on_message(filters.command("viewsettings") & filters.group)
    async def viewsettings_cmd(client: Client, m: Message):
        user_id = m.from_user.id if m.from_user else 0
        if user_id not in AUTH_USERS:
            await m.reply_text(f"<blockquote>🙅 Not authorized. Your ID: `{user_id}`</blockquote>")
            return

        b_name = globals.get_setting("batch_name",  "Premium Batch")
        cr     = globals.get_setting("credit_name", CREDIT)

        text = (
            "**⚙️ Current Global Settings**\n\n"
            f"<blockquote>📚 **Batch Name:**\n`{b_name}`\n\n"
            f"📥 **Credit Name:**\n`{cr}`</blockquote>\n\n"
            "Use /setbatch or /setcredit to update."
        )
        await m.reply_text(text)

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,
