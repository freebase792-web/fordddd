"""
Content delivery handler.
Sends all active content (video, image, voice, text, APK) to the user
after they answer YES. Fully driven by admin-configured content.
"""
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.models.database import Session, User, Content, Analytics, get_config
from bot.utils.keyboards import content_keyboard, back_to_content_keyboard
from bot.utils.helpers import calculate_xp_for_event, format_xp_level

logger = logging.getLogger(__name__)


async def deliver_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Deliver all active content to the user after YES answer.
    Order: yes_intro → text → image(s) → video(s) → voice → APK button
    """
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    session = Session()
    try:
        user = session.get(User, user_id)
        if not user:
            return

        # Award XP for content view
        user.xp_points += calculate_xp_for_event("answer_yes")
        user.last_active = datetime.utcnow()

        # Log analytics
        session.add(Analytics(user_id=user_id, event="content_view"))
        session.commit()

        yes_intro = get_config("yes_intro_text", "🎊 *Amazing! You're in!*\n\nHere's your exclusive content 👇")
        await context.bot.send_message(
            chat_id=chat_id,
            text=yes_intro,
            parse_mode=ParseMode.MARKDOWN,
        )

        # Fetch all active content ordered by type priority and order_index
        contents = (
            session.query(Content)
            .filter_by(is_active=True)
            .order_by(Content.order_index.asc(), Content.id.asc())
            .all()
        )

        # Separate active APK for the button
        active_apk = next((c for c in contents if c.content_type == "apk"), None)

        # Deliver each piece in order
        for item in contents:
            try:
                if item.content_type == "text":
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=item.text_content or item.caption or "—",
                        parse_mode=ParseMode.MARKDOWN,
                    )

                elif item.content_type == "image":
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=item.file_id,
                        caption=item.caption or "",
                        parse_mode=ParseMode.MARKDOWN,
                    )

                elif item.content_type == "video":
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=item.file_id,
                        caption=item.caption or "",
                        parse_mode=ParseMode.MARKDOWN,
                        supports_streaming=True,
                    )

                elif item.content_type == "voice":
                    await context.bot.send_voice(
                        chat_id=chat_id,
                        voice=item.file_id,
                        caption=item.caption or "",
                    )

                elif item.content_type == "audio":
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=item.file_id,
                        caption=item.caption or "",
                    )

                elif item.content_type == "apk":
                    # APK is shown as a button below — skip direct send here
                    continue

            except Exception as e:
                logger.error(f"Error sending content item {item.id}: {e}")
                continue

        # Show action buttons (APK download + extras)
        apk_version = active_apk.version if active_apk else None
        apk_button_text = get_config("apk_button_text", "⬇️ Download App")
        level_info = format_xp_level(user.xp_points)

        closing_msg = (
            f"✨ *You're all set, {user.get_display_name()}!*\n\n"
            f"🏅 Level: *{level_info['name']}*\n"
            f"⚡ XP: *{user.xp_points}*\n"
        )
        if level_info['next_at']:
            closing_msg += f"📈 Next level at *{level_info['next_at']} XP* — *{level_info['next_name']}*\n"
        closing_msg += "\n👇 Use the buttons below:"

        await context.bot.send_message(
            chat_id=chat_id,
            text=closing_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=content_keyboard(apk_version, apk_button_text),
        )

    except Exception as e:
        logger.error(f"Error in deliver_content: {e}", exc_info=True)
    finally:
        session.close()


async def send_apk_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the latest APK file to the user."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    session = Session()
    try:
        # Always get the latest active APK
        active_apk = (
            session.query(Content)
            .filter_by(is_active=True, content_type="apk")
            .order_by(Content.id.desc())
            .first()
        )

        if not active_apk:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ No APK available yet. Check back soon! 🔔",
            )
            return

        # Log analytics
        user = session.get(User, user_id)
        if user:
            user.xp_points += calculate_xp_for_event("download_apk")
            user.last_active = datetime.utcnow()
        session.add(Analytics(user_id=user_id, event="apk_download",
                              metadata_={"version": active_apk.version}))
        session.commit()

        caption_parts = [f"📱 *{active_apk.file_name or 'App'}*"]
        if active_apk.version:
            caption_parts.append(f"📌 Version: *{active_apk.version}*")
        if active_apk.changelog:
            caption_parts.append(f"\n📋 *What's new:*\n{active_apk.changelog}")
        caption_parts.append("\n⬇️ Tap to install!")
        caption = "\n".join(caption_parts)

        await context.bot.send_document(
            chat_id=chat_id,
            document=active_apk.file_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_to_content_keyboard(),
        )

    except Exception as e:
        logger.error(f"Error in send_apk_to_user: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="❌ Couldn't send the APK. Please try again.")
    finally:
        session.close()
