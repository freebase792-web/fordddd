"""
/start command handler — user onboarding and registration.
Handles referral codes, streak updates, and welcome flow.
"""
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.models.database import Session, User, Analytics, get_config
from bot.utils.keyboards import start_keyboard, user_reply_keyboard
from bot.utils.helpers import (
    generate_referral_code, update_streak, format_streak_message,
    calculate_xp_for_event
)

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — register user and show welcome."""
    user_tg = update.effective_user
    chat_id = update.effective_chat.id

    # Check maintenance mode
    if get_config("bot_enabled", "true").lower() != "true":
        maint_msg = get_config(
            "maintenance_message",
            "🔧 We're upgrading the experience. Back soon! 💫"
        )
        await update.message.reply_text(maint_msg)
        return

    session = Session()
    try:
        from bot.handlers.admin_upload import is_admin
        from bot.utils.keyboards import admin_panel_keyboard

        # --- ADMIN FLOW: Show Admin Panel directly ---
        if is_admin(user_tg.id):
            demo_on = get_config("demo_enabled", "true").lower() == "true"
            bot_active = get_config("bot_enabled", "true").lower() == "true"
            
            await update.message.reply_text(
                "⚡ *NexusBot Admin Panel* ⚡\n\n"
                "Manage your APKs, settings, content, and broadcasts directly from Telegram below:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=admin_panel_keyboard(demo_on, bot_active)
            )
            return

        # --- USER FLOW ---
        user = session.get(User, user_tg.id)
        is_new = user is None

        if is_new:
            # Parse referral code from deep link: /start REF_CODE
            referrer_id = None
            if context.args:
                ref_code = context.args[0]
                referrer = session.query(User).filter_by(referral_code=ref_code).first()
                if referrer and referrer.id != user_tg.id:
                    referrer_id = referrer.id
                    referrer.referral_count += 1
                    referrer.xp_points += calculate_xp_for_event("referral_joined")
                    session.flush()

            user = User(
                id=user_tg.id,
                username=user_tg.username,
                first_name=user_tg.first_name,
                last_name=user_tg.last_name,
                language_code=user_tg.language_code or "en",
                referrer_id=referrer_id,
                referral_code=generate_referral_code(user_tg.id),
                streak_count=1,
                streak_last_date=datetime.utcnow(),
                xp_points=calculate_xp_for_event("start"),
            )
            session.add(user)

            # Log analytics
            session.add(Analytics(user_id=user_tg.id, event="start", metadata_={"is_new": True}))
            session.flush()

            # ── Real-time log notification to Admin inside Telegram ──
            from bot.handlers.admin_upload import ADMIN_TELEGRAM_ID
            if ADMIN_TELEGRAM_ID:
                try:
                    name_str = f"{user_tg.first_name or ''} {user_tg.last_name or ''}".strip()
                    username_str = f"@{user_tg.username}" if user_tg.username else "—"
                    await context.bot.send_message(
                        chat_id=ADMIN_TELEGRAM_ID,
                        text=(
                            f"🆕 *New user*\n\n"
                            f"👤 Name: *{name_str or 'Unknown'}*\n"
                            f"🆔 ID: `{user_tg.id}`\n"
                            f"📛 Username: {username_str}"
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception as log_err:
                    logger.error(f"Failed to send join log to admin: {log_err}")

            if referrer_id:
                # Notify referrer about new join (non-blocking)
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"🎉 *Someone just joined using your link!*\n"
                            f"You earned *+{calculate_xp_for_event('referral_joined')} XP* 💎\n\n"
                            f"Keep sharing to climb the leaderboard! 🚀"
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass  # Referrer may have blocked bot

        else:
            # Returning user — update info and streak
            user.username = user_tg.username
            user.first_name = user_tg.first_name
            user.last_name = user_tg.last_name
            user.last_active = datetime.utcnow()
            streak_updated = update_streak(user)
            if streak_updated:
                user.xp_points += calculate_xp_for_event("daily_streak")

        session.commit()

        # Dock the persistent custom Reply Keyboard at the bottom of the Telegram chat immediately
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🤖 *Accessing premium portal...*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=user_reply_keyboard()
            )
        except Exception as kb_err:
            logger.error(f"Failed to dock custom reply keyboard: {kb_err}")

        # Route the user dynamically based on whether they've answered the onboarding question
        from bot.handlers.callbacks import _show_question
        from bot.handlers.content import deliver_content

        if user.question_answered:
            # Returning user who already answered Yes/No -> go straight to content
            await deliver_content(update, context)
        else:
            # New user -> go straight to the onboarding question
            await _show_question(update, context)

    except Exception as e:
        logger.error(f"Error in start_handler: {e}", exc_info=True)
        await update.message.reply_text("Something went wrong. Please try again with /start")
    finally:
        session.close()
