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
from bot.utils.keyboards import start_keyboard
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

        name = user.first_name or user.username or "there"
        streak = user.streak_count

        # Build welcome text
        welcome_text = get_config(
            "welcome_text",
            "🎉 *Welcome to NexusBot!*\n\nYou're about to unlock something incredible.\nTap the button below to begin! 🚀"
        )

        if is_new:
            greeting = f"👋 Hey *{name}*, welcome aboard!\n\n"
        else:
            streak_msg = format_streak_message(streak)
            greeting = f"🔥 Welcome back, *{name}*!\n{streak_msg}\n\n"

        full_welcome = greeting + welcome_text

        # Send welcome GIF if configured
        welcome_gif_id = get_config("welcome_gif_id", "")
        if welcome_gif_id:
            try:
                await context.bot.send_animation(
                    chat_id=chat_id,
                    animation=welcome_gif_id,
                    caption=full_welcome,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=start_keyboard(),
                )
            except Exception:
                # Fallback to text if GIF fails
                await update.message.reply_text(
                    full_welcome,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=start_keyboard(),
                )
        else:
            await update.message.reply_text(
                full_welcome,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=start_keyboard(),
            )

    except Exception as e:
        logger.error(f"Error in start_handler: {e}", exc_info=True)
        await update.message.reply_text("Something went wrong. Please try again with /start")
    finally:
        session.close()
