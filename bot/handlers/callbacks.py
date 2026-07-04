"""
Inline button callback router for NexusBot.
All user-facing button interactions are handled here.
"""
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.models.database import Session, User, Question, Analytics, get_config
from bot.utils.keyboards import (
    question_keyboard, reconsider_keyboard, stats_keyboard
)
from bot.utils.helpers import (
    format_streak_message, format_xp_level, calculate_xp_for_event
)
from bot.handlers.content import deliver_content, send_apk_to_user

logger = logging.getLogger(__name__)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all inline button callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "show_question":
        await _show_question(update, context)
    elif data == "answer_yes":
        await _handle_yes(update, context)
    elif data == "answer_no":
        await _handle_no(update, context)
    elif data == "download_apk":
        await send_apk_to_user(update, context)
    elif data == "get_referral":
        await _show_referral(update, context)
    elif data == "my_stats":
        await _show_stats(update, context)
    elif data == "show_content":
        await deliver_content(update, context)
    else:
        logger.warning(f"Unknown callback data: {data}")


async def _show_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the active onboarding question."""
    query = update.callback_query
    chat_id = update.effective_chat.id

    # Safely delete the welcome message (text or GIF) to clear the screen and loading state
    try:
        await query.message.delete()
    except Exception:
        pass

    session = Session()
    try:
        question = (
            session.query(Question)
            .filter_by(is_active=True)
            .order_by(Question.order_index.asc())
            .first()
        )

        if not question:
            # No question set — go straight to content
            await deliver_content(update, context)
            return

        # Animated typing effect simulation
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        question_msg = (
            f"🤔 *Quick question for you:*\n\n"
            f"_{question.question_text}_"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=question_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=question_keyboard(question.yes_label, question.no_label),
        )

    except Exception as e:
        logger.error(f"Error in _show_question: {e}", exc_info=True)
    finally:
        session.close()


async def _handle_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle YES answer — deliver content."""
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        await query.message.delete()
    except Exception:
        pass

    session = Session()
    try:
        user = session.get(User, user_id)
        if user:
            user.question_answered = True
            user.answer_yes = True
            user.last_active = datetime.utcnow()
        session.add(Analytics(user_id=user_id, event="answer_yes"))
        session.commit()
    except Exception as e:
        logger.error(f"DB error in _handle_yes: {e}")
    finally:
        session.close()

    # Show exciting transition message
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🎊 *YES! Let's go!*\n\n"
            "⚡ Loading your exclusive content...\n"
            "🔓 Unlocking the vault..."
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

    # Deliver all content
    await deliver_content(update, context)


async def _handle_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle NO answer — friendly response with option to reconsider."""
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        await query.message.delete()
    except Exception:
        pass

    session = Session()
    try:
        user = session.get(User, user_id)
        if user:
            user.question_answered = True
            user.answer_yes = False
            user.last_active = datetime.utcnow()
        session.add(Analytics(user_id=user_id, event="answer_no"))
        session.commit()
    except Exception as e:
        logger.error(f"DB error in _handle_no: {e}")
    finally:
        session.close()

    no_response = get_config(
        "no_response_text",
        "😢 No worries! Whenever you change your mind,\njust tap below and we'll be here. 🌟"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=no_response,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reconsider_keyboard(),
    )


async def _show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user's unique referral link."""
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    session = Session()
    try:
        user = session.get(User, user_id)
        if not user or not user.referral_code:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Start the bot first with /start")
            return

        bot_username = context.bot.username
        referral_link = f"https://t.me/{bot_username}?start={user.referral_code}"

        xp_per_referral = calculate_xp_for_event("referral_joined")
        msg = (
            f"🔗 *Your Referral Link*\n\n"
            f"`{referral_link}`\n\n"
            f"📊 *Your Stats:*\n"
            f"👥 Friends Invited: *{user.referral_count}*\n"
            f"💎 XP Earned from Referrals: *{user.referral_count * xp_per_referral}*\n\n"
            f"🎁 Each friend who joins earns you *+{xp_per_referral} XP*!\n"
            f"🏆 Climb the leaderboard and unlock exclusive rewards!"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
        )

    except Exception as e:
        logger.error(f"Error in _show_referral: {e}", exc_info=True)
    finally:
        session.close()


async def _show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user stats: XP, level, streak, referrals."""
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    session = Session()
    try:
        user = session.get(User, user_id)
        if not user:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Use /start first!")
            return

        level_info = format_xp_level(user.xp_points)
        streak_msg = format_streak_message(user.streak_count)

        msg = (
            f"📊 *Your Stats, {user.get_display_name()}!*\n"
            f"{'─' * 25}\n"
            f"🏅 Level: *{level_info['name']}*\n"
            f"⚡ XP: *{user.xp_points}*\n"
        )
        if level_info['next_at']:
            remaining = level_info['next_at'] - user.xp_points
            msg += f"📈 Next Level: *{level_info['next_name']}* (need {remaining} more XP)\n"

        msg += (
            f"\n{streak_msg}\n"
            f"🔥 Current Streak: *{user.streak_count} days*\n"
            f"👥 Referrals: *{user.referral_count}*\n"
            f"\n💡 _Earn XP by downloading, referring friends & daily visits!_"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=stats_keyboard(),
        )

    except Exception as e:
        logger.error(f"Error in _show_stats: {e}", exc_info=True)
    finally:
        session.close()
