"""
Content delivery handler.
Sends all active content (video, image, voice, text, APK) to the user
after they answer YES. Fully driven by admin-configured content.
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.models.database import Session, User, Content, Analytics, get_config
from bot.utils.keyboards import content_keyboard, back_to_content_keyboard, user_reply_keyboard
from bot.utils.helpers import calculate_xp_for_event, format_xp_level, track_message

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

        # Check if demo content delivery is enabled
        demo_enabled = get_config("demo_enabled", "true").lower() == "true"

        # Deliver each piece in order if demo is ON
        for item in contents:
            if not demo_enabled and item.content_type != "apk":
                continue  # Skip general content/demo items if demo toggle is OFF
                
            try:
                if item.content_type == "text":
                    msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text=item.text_content or item.caption or "—",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    track_message(context, msg)

                elif item.content_type == "image":
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=item.file_id,
                        caption=item.caption or "",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    track_message(context, msg)

                elif item.content_type == "video":
                    msg = await context.bot.send_video(
                        chat_id=chat_id,
                        video=item.file_id,
                        caption=item.caption or "",
                        parse_mode=ParseMode.MARKDOWN,
                        supports_streaming=True,
                    )
                    track_message(context, msg)

                elif item.content_type == "voice":
                    msg = await context.bot.send_voice(
                        chat_id=chat_id,
                        voice=item.file_id,
                        caption=item.caption or "",
                    )
                    track_message(context, msg)

                elif item.content_type == "audio":
                    msg = await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=item.file_id,
                        caption=item.caption or "",
                    )
                    track_message(context, msg)

                elif item.content_type == "apk":
                    continue

                elif item.content_type == "apk_demo":
                    await send_apk_to_user(update, context)

                elif item.content_type == "link":
                    link_kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton(item.link_text or "🔗 Open Link", url=item.link_url or item.text_content)]
                    ])
                    msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text=item.caption or "🔗 *Click the button below:*",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=link_kb,
                    )
                    track_message(context, msg)
                    continue

                if item.link_url:
                    link_kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton(item.link_text or "🔗 Open Link", url=item.link_url)]
                    ])
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="🔗 *Related link:*",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=link_kb,
                    )

            except Exception as e:
                logger.error(f"Error sending content item {item.id}: {e}")
                continue

        apk_version = active_apk.version if active_apk else None
        apk_button_text = get_config("apk_button_text", "⬇️ Download App")
        demo_tpl = get_config(
            "demo_closing_text",
            "✨ *There you go, {name}!*\n\n"
            "You finally got what you wanted. 😉\n"
            "Don't just run away now! Use the bottom buttons to download the APK and invite your friends. secretly... 🤫"
        )
        closing_msg = demo_tpl.replace("{name}", user.get_display_name())

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=closing_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=user_reply_keyboard(),
        )
        track_message(context, msg)

        if active_apk and not user.downloaded_apk:
            total_downloads = session.query(Analytics).filter_by(event="apk_download").count()
            reminder_text = (
                f"📱 *Don't miss out!*\n\n"
                f"👥 *{total_downloads} users* have already downloaded the APK.\n"
                f"💎 Get *+{calculate_xp_for_event('download_apk') * 2} XP* bonus on your first download!\n\n"
                f"👇 Tap the button below to get it now."
            )
            reminder_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=reminder_text,
                parse_mode=ParseMode.MARKDOWN,
            )
            track_message(context, reminder_msg)

    except Exception as e:
        logger.error(f"Error in deliver_content: {e}", exc_info=True)
    finally:
        session.close()


async def send_apk_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the latest APK file to the user with social proof and install guide."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    session = Session()
    try:
        active_apk = (
            session.query(Content)
            .filter_by(is_active=True, content_type="apk")
            .order_by(Content.id.desc())
            .first()
        )

        if not active_apk:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ No APK available yet. Check back soon! 🔔",
            )
            track_message(context, msg)
            return
        user = session.get(User, user_id)

        total_downloads = session.query(Analytics).filter_by(event="apk_download").count()
        is_first_download = user and not user.downloaded_apk

        if user:
            if not user.downloaded_apk:
                user.downloaded_apk = True
                bonus_xp = calculate_xp_for_event("download_apk") * 2
                user.xp_points += bonus_xp
                if user.referrer_id:
                    referrer = session.get(User, user.referrer_id)
                    if referrer:
                        ref_bonus = calculate_xp_for_event("referral_joined")
                        referrer.xp_points += ref_bonus
                        try:
                            await context.bot.send_message(
                                chat_id=user.referrer_id,
                                text=(
                                    f"🎉 *Your referral just downloaded the APK!*\n"
                                    f"You earned *+{ref_bonus} XP* 💎"
                                ),
                                parse_mode=ParseMode.MARKDOWN,
                            )
                        except Exception:
                            pass
            user.last_active = datetime.utcnow()
        session.add(Analytics(user_id=user_id, event="apk_download",
                              metadata_={"version": active_apk.version}))
        session.commit()

        social_proof = f"👥 *{total_downloads + 1} users* have downloaded this APK"
        caption_parts = [
            f"📱 *{active_apk.file_name or 'App'}*",
            f"📌 Version: *{active_apk.version}*" if active_apk.version else "",
            f"\n📋 *What's new:*\n{active_apk.changelog}" if active_apk.changelog else "",
            f"\n{social_proof}",
            "\n⬇️ *Tap the file below to install!*"
        ]
        caption = "\n".join(p for p in caption_parts if p)

        app_icon_id = get_config("apk_icon_file_id", "")
        if app_icon_id:
            try:
                icon_msg = await context.bot.send_photo(
                    chat_id=chat_id, photo=app_icon_id,
                    caption="📦 *Preparing your download...*",
                    parse_mode=ParseMode.MARKDOWN
                )
                track_message(context, icon_msg)
            except Exception:
                pass

        xp_bonus_msg = ""
        if is_first_download and user:
            xp_bonus_msg = (
                f"\n\n🎁 *First download bonus!* +{calculate_xp_for_event('download_apk') * 2} XP 💎"
            )

        await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")

        doc_msg = await context.bot.send_document(
            chat_id=chat_id,
            document=active_apk.file_id,
            caption=caption + xp_bonus_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_to_content_keyboard(),
        )
        track_message(context, doc_msg)

        install_guide = get_config(
            "install_guide_text",
            "📲 *How to Install the APK:*\n\n"
            "1. Tap the file above to download\n"
            "2. Open the downloaded file\n"
            "3. Tap *Install* (allow from unknown sources if prompted)\n"
            "4. Open the app and enjoy! 🚀\n\n"
            "💡 *Need help?* Just tap /start anytime!"
        )
        guide_msg = await context.bot.send_message(
            chat_id=chat_id, text=install_guide,
            parse_mode=ParseMode.MARKDOWN,
        )
        track_message(context, guide_msg)

    except Exception as e:
        logger.error(f"Error in send_apk_to_user: {e}", exc_info=True)
        err_msg = await context.bot.send_message(chat_id=chat_id, text="❌ Couldn't send the APK. Please try again.")
        track_message(context, err_msg)
    finally:
        session.close()
