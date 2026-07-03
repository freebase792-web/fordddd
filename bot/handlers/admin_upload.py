"""
Admin Telegram Handler — For the bot owner only.
The admin can send files directly to the bot and they are automatically
saved as content or as the active APK. No file_id copy-pasting needed.

HOW TO USE:
  - Set ADMIN_TELEGRAM_ID in your .env to your Telegram numeric user ID.
  - Send any file directly to your bot in Telegram chat.
  - The bot responds with a confirmation and saves it automatically.
  - For APK: send the .apk file — it replaces the active APK instantly.
  - For other media: send the file — the bot asks what type to save as.

Get your Telegram ID: message @userinfobot → it shows your numeric ID.
"""

import logging
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.models.database import Session, Content, BotConfig, set_config, get_config

logger = logging.getLogger(__name__)

# Admin Telegram User ID — only this user can send files to the bot
ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))


def is_admin(user_id: int) -> bool:
    """Check if the sender is the designated admin."""
    return ADMIN_TELEGRAM_ID != 0 and user_id == ADMIN_TELEGRAM_ID


async def admin_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles any file/media sent directly to the bot by the admin.
    Auto-detects type and saves to database immediately.
    """
    user = update.effective_user
    if not is_admin(user.id):
        return  # Silently ignore non-admin file sends

    message = update.message
    chat_id = update.effective_chat.id

    # Detect what was sent
    file_id = None
    content_type = None
    file_name = None
    detected_label = ""

    if message.document:
        doc = message.document
        file_id = doc.file_id
        file_name = doc.file_name or "file"
        # Auto-detect APK by mime type or filename extension
        if (doc.mime_type == "application/vnd.android.package-archive"
                or (file_name and file_name.lower().endswith(".apk"))):
            content_type = "apk"
            detected_label = "📱 APK File"
        else:
            content_type = "document"
            detected_label = f"📁 Document ({file_name})"

    elif message.video:
        file_id = message.video.file_id
        content_type = "video"
        file_name = message.video.file_name or "video.mp4"
        detected_label = "🎬 Video"

    elif message.photo:
        # Use highest resolution photo
        file_id = message.photo[-1].file_id
        content_type = "image"
        file_name = "photo.jpg"
        detected_label = "🖼️ Image"

    elif message.voice:
        file_id = message.voice.file_id
        content_type = "voice"
        file_name = "voice.ogg"
        detected_label = "🎵 Voice Note"

    elif message.audio:
        file_id = message.audio.file_id
        content_type = "audio"
        file_name = message.audio.file_name or "audio.mp3"
        detected_label = "🎤 Audio"

    elif message.animation:
        file_id = message.animation.file_id
        content_type = "image"
        file_name = "animation.gif"
        detected_label = "🎞️ GIF / Animation"

    if not file_id:
        return  # Unknown type, ignore

    # Store file_id in context for the callback to use
    context.user_data["pending_file_id"] = file_id
    context.user_data["pending_file_name"] = file_name
    context.user_data["pending_content_type"] = content_type
    context.user_data["pending_caption"] = message.caption or ""

    # --- APK: Auto-save immediately, no prompt needed ---
    if content_type == "apk":
        await _save_apk(update, context, file_id, file_name, message.caption or "")
        return

    # --- Welcome GIF: If it's a GIF/animation, offer to set as welcome ---
    if content_type == "image" and detected_label.startswith("🎞️"):
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🌟 Set as Welcome GIF", callback_data="admin_set_welcome_gif"),
                InlineKeyboardButton("📦 Save as Content", callback_data="admin_save_content"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
        ])
        await message.reply_text(
            f"✅ *{detected_label} received!*\n\n"
            f"`{file_id}`\n\n"
            f"What should I do with this?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
        return

    # --- All other media: Ask what to do ---
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Add to User Content", callback_data="admin_save_content"),
            InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel"),
        ]
    ])

    await message.reply_text(
        f"✅ *{detected_label} received!*\n\n"
        f"📋 File ID saved:\n`{file_id}`\n\n"
        f"Tap below to add this to your bot's content.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def _save_apk(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    file_name: str,
    caption: str,
):
    """Auto-save a new APK, archiving the old one."""
    message = update.message
    chat_id = update.effective_chat.id

    # Ask for version number
    context.user_data["awaiting_apk_version"] = True
    context.user_data["pending_file_id"] = file_id
    context.user_data["pending_file_name"] = file_name
    context.user_data["pending_caption"] = caption

    await message.reply_text(
        f"📱 *APK received!* `{file_name}`\n\n"
        f"Reply with the version number (e.g. `1.2`) and optionally a changelog:\n\n"
        f"Format:\n`1.2\nWhat's new in this version...`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles text messages from admin — used to receive version info after APK upload.
    """
    user = update.effective_user
    if not is_admin(user.id):
        return

    message = update.message
    text = message.text.strip()

    # Handle APK version input
    if context.user_data.get("awaiting_apk_version"):
        context.user_data.pop("awaiting_apk_version")
        lines = text.split("\n", 1)
        version = lines[0].strip()
        changelog = lines[1].strip() if len(lines) > 1 else ""

        file_id = context.user_data.pop("pending_file_id", None)
        file_name = context.user_data.pop("pending_file_name", "App.apk")
        caption = context.user_data.pop("pending_caption", "")

        if not file_id:
            await message.reply_text("⚠️ No APK pending. Please send the APK file first.")
            return

        # Archive old APK and save new one
        session = Session()
        try:
            # Archive existing active APKs
            session.query(Content).filter_by(
                content_type="apk", is_active=True
            ).update({"is_active": False})

            # Save new APK as active
            new_apk = Content(
                content_type="apk",
                file_id=file_id,
                file_name=file_name,
                version=version,
                changelog=changelog,
                caption=caption or None,
                is_active=True,
            )
            session.add(new_apk)
            session.commit()

            await message.reply_text(
                f"🎉 *APK Updated Successfully!*\n\n"
                f"📱 File: `{file_name}`\n"
                f"📌 Version: *{version}*\n"
                f"📋 Changelog: {changelog or 'None'}\n\n"
                f"✅ Old APK archived. New APK is now live!\n"
                f"📢 Don't forget to send a Broadcast to notify your users!",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving APK: {e}", exc_info=True)
            await message.reply_text(f"❌ Error saving APK: {e}")
        finally:
            session.close()
        return

    # Admin info command
    if text in ("/admin_info", "/info"):
        await _show_admin_info(update, context)
        return


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin-specific inline button callbacks."""
    user = update.effective_user
    if not is_admin(user.id):
        return

    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_save_content":
        file_id = context.user_data.pop("pending_file_id", None)
        file_name = context.user_data.pop("pending_file_name", "file")
        content_type = context.user_data.pop("pending_content_type", "document")
        caption = context.user_data.pop("pending_caption", "")

        if not file_id:
            await query.edit_message_text("⚠️ No file pending.")
            return

        session = Session()
        try:
            # Get the highest current order index
            from sqlalchemy import func
            max_order = session.query(func.max(Content.order_index)).scalar() or 0
            item = Content(
                content_type=content_type,
                file_id=file_id,
                file_name=file_name,
                caption=caption or None,
                is_active=True,
                order_index=max_order + 1,
            )
            session.add(item)
            session.commit()
            await query.edit_message_text(
                f"✅ *Content saved!*\n\n"
                f"Type: `{content_type}`\n"
                f"File: `{file_name}`\n"
                f"Order: `{max_order + 1}`\n\n"
                f"It will now appear in the user content flow.\n"
                f"Manage it at: /admin/content",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            session.rollback()
            await query.edit_message_text(f"❌ Error: {e}")
        finally:
            session.close()

    elif data == "admin_set_welcome_gif":
        file_id = context.user_data.pop("pending_file_id", None)
        context.user_data.pop("pending_file_name", None)
        context.user_data.pop("pending_content_type", None)
        context.user_data.pop("pending_caption", None)
        if file_id:
            set_config("welcome_gif_id", file_id)
            await query.edit_message_text(
                f"🌟 *Welcome GIF/Animation set!*\n\n"
                f"New users will now see this animation when they start the bot.\n"
                f"File ID: `{file_id}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await query.edit_message_text("⚠️ No file pending.")

    elif data == "admin_cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Cancelled.")


async def _show_admin_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin quick-help info."""
    session = Session()
    try:
        from bot.models.database import User, Broadcast
        total_users = session.query(User).count()
        active_apk = session.query(Content).filter_by(
            is_active=True, content_type="apk"
        ).order_by(Content.id.desc()).first()

        msg = (
            "⚡ *NexusBot Admin Info*\n"
            "──────────────────────\n"
            f"👥 Total Users: *{total_users}*\n"
            f"📱 Active APK: *{active_apk.file_name} v{active_apk.version}*\n"
            if active_apk else f"📱 Active APK: *None uploaded*\n"
        )
        msg += (
            "\n📤 *Send me any file to save it:*\n"
            "• APK → auto-replaces active APK\n"
            "• Video/Image/Voice → added to content\n"
            "• GIF/Animation → set as welcome animation\n"
            "\n🌐 Manage everything at your Admin Panel."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
    finally:
        session.close()
