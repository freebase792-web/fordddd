"""
Async broadcast engine for NexusBot.
Supports: text, voice note, image, video, APK/document, audio.
Respects Telegram rate limits (25 msg/sec).
Uses Redis queue for reliable delivery with retries.
"""
import asyncio
import logging
import time
from datetime import datetime
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError

from bot.models.database import Session, User, Broadcast, Analytics, Content, get_config

logger = logging.getLogger(__name__)

# Telegram safe broadcast rate
SEND_INTERVAL = 1 / 25  # 25 messages per second
MAX_RETRIES = 3


async def execute_broadcast(broadcast_id: int, bot_token: str):
    """
    Execute a broadcast job. Called by the worker process.
    Sends a message to all non-banned users.
    """
    bot = Bot(token=bot_token)
    session = Session()
    broadcast = None

    try:
        broadcast = session.get(Broadcast, broadcast_id)
        if not broadcast:
            logger.error(f"Broadcast {broadcast_id} not found")
            return

        broadcast.status = "sending"
        session.commit()

        # Get all active, non-banned users
        users = session.query(User).filter_by(is_banned=False).all()
        total = len(users)
        broadcast.total_users = total
        session.commit()

        sent = 0
        failed = 0

        # Build optional APK button
        reply_markup = None
        if broadcast.has_apk_button:
            active_apk = (
                session.query(Content)
                .filter_by(is_active=True, content_type="apk")
                .order_by(Content.id.desc())
                .first()
            )
            if active_apk:
                btn_text = f"{broadcast.apk_button_text} v{active_apk.version}" if active_apk.version else broadcast.apk_button_text
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton(btn_text, callback_data="download_apk")]
                ])

        for user in users:
            success = await _send_to_user(
                bot=bot,
                user_id=user.id,
                broadcast=broadcast,
                reply_markup=reply_markup,
                session=session,
            )
            if success:
                sent += 1
            else:
                failed += 1

            # Update progress every 50 users
            if (sent + failed) % 50 == 0:
                broadcast.sent_count = sent
                broadcast.failed_count = failed
                session.commit()

            # Rate limiting
            await asyncio.sleep(SEND_INTERVAL)

        # Final update
        broadcast.sent_count = sent
        broadcast.failed_count = failed
        broadcast.status = "done"
        broadcast.completed_at = datetime.utcnow()
        session.commit()

        logger.info(f"Broadcast {broadcast_id} complete: {sent}/{total} sent, {failed} failed")

    except Exception as e:
        logger.error(f"Broadcast {broadcast_id} failed: {e}", exc_info=True)
        if broadcast:
            broadcast.status = "failed"
            session.commit()
    finally:
        await bot.close()
        session.close()


async def _send_to_user(
    bot: Bot,
    user_id: int,
    broadcast: "Broadcast",
    reply_markup: InlineKeyboardMarkup | None,
    session,
    attempt: int = 1,
) -> bool:
    """Send a single broadcast message to one user. Retries up to MAX_RETRIES."""
    try:
        msg_type = broadcast.message_type
        file_id = broadcast.file_id
        caption = broadcast.caption or ""
        text = broadcast.content_text or ""

        if msg_type == "text":
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        elif msg_type == "image":
            await bot.send_photo(
                chat_id=user_id,
                photo=file_id,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        elif msg_type == "video":
            await bot.send_video(
                chat_id=user_id,
                video=file_id,
                caption=caption,
                parse_mode="Markdown",
                supports_streaming=True,
                reply_markup=reply_markup,
            )
        elif msg_type == "voice":
            # Voice note — native Telegram voice message
            await bot.send_voice(
                chat_id=user_id,
                voice=file_id,
                caption=caption,
                reply_markup=reply_markup,
            )
        elif msg_type == "audio":
            await bot.send_audio(
                chat_id=user_id,
                audio=file_id,
                caption=caption,
                reply_markup=reply_markup,
            )
        elif msg_type == "apk" or msg_type == "document":
            await bot.send_document(
                chat_id=user_id,
                document=file_id,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )

        return True

    except TelegramError as e:
        err_msg = str(e).lower()
        # User blocked bot or deleted account — don't retry
        if any(x in err_msg for x in ["blocked", "deactivated", "not found", "chat not found"]):
            return False
        # Retry on other errors
        if attempt < MAX_RETRIES:
            await asyncio.sleep(1)
            return await _send_to_user(bot, user_id, broadcast, reply_markup, session, attempt + 1)
        logger.warning(f"Failed to send to {user_id} after {MAX_RETRIES} attempts: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending to {user_id}: {e}")
        return False
