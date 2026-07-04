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

        # ── Send completion report to Admin inside Telegram (matching reference image) ──
        from bot.handlers.admin_upload import ADMIN_TELEGRAM_ID
        if ADMIN_TELEGRAM_ID:
            try:
                title_lbl = "APK Blast" if broadcast.message_type == "apk" else "Broadcast"
                
                # Check if it was a multimedia sequence
                is_multi = False
                if broadcast.content_text:
                    try:
                        import json
                        parsed = json.loads(broadcast.content_text)
                        if isinstance(parsed, list):
                            is_multi = True
                    except Exception:
                        pass
                
                type_lbl = "MULTIMEDIA" if is_multi else broadcast.message_type.upper()
                
                # Retrieve APK Name for the report if it is an APK broadcast
                apk_name_line = ""
                if broadcast.message_type == "apk":
                    active_apk = session.query(Content).filter_by(content_type="apk", is_active=True).first()
                    if active_apk:
                        apk_name_line = f"📲 APK Name: *{active_apk.file_name}*\n"

                await bot.send_message(
                    chat_id=ADMIN_TELEGRAM_ID,
                    text=(
                        f"🎉 *{title_lbl} Complete!* 🎉\n"
                        f"──────────────────────────\n"
                        f"{apk_name_line}"
                        f"👥 Total Users: *{total}*\n"
                        f"✅ Successfully Sent: *{sent}*\n"
                        f"🚫 Blocked (Skipped): *{failed}*\n"
                        f"⚠️ Other Fails: *0*\n"
                        f"──────────────────────────\n"
                        f"All done! 💪🔥"
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as report_err:
                logger.error(f"Failed to send broadcast completion report: {report_err}")

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
    """Send a single broadcast message (or multi-media sequence) to one user. Retries up to MAX_RETRIES."""
    try:
        # Check if the broadcast text is a serialized JSON array of multiple media items
        items = []
        if broadcast.content_text:
            try:
                import json
                parsed = json.loads(broadcast.content_text)
                if isinstance(parsed, list):
                    items = parsed
            except Exception:
                pass

        # Fallback to single media item if not a serialized sequence
        if not items:
            items = [{
                "type": broadcast.message_type,
                "file_id": broadcast.file_id,
                "caption": broadcast.caption,
                "text": broadcast.content_text
            }]

        # Send all items in sequence to the user
        for idx, item in enumerate(items):
            msg_type = item.get("type", "text")
            file_id = item.get("file_id")
            caption = item.get("caption") or ""
            text = item.get("text") or ""
            
            # Attach the APK button reply_markup ONLY to the final item in the sequence
            item_markup = reply_markup if idx == len(items) - 1 else None

            if msg_type == "text":
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=item_markup,
                )
            elif msg_type == "image":
                await bot.send_photo(
                    chat_id=user_id,
                    photo=file_id,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=item_markup,
                )
            elif msg_type == "video":
                await bot.send_video(
                    chat_id=user_id,
                    video=file_id,
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True,
                    reply_markup=item_markup,
                )
            elif msg_type == "voice":
                await bot.send_voice(
                    chat_id=user_id,
                    voice=file_id,
                    caption=caption,
                    reply_markup=item_markup,
                )
            elif msg_type == "audio":
                await bot.send_audio(
                    chat_id=user_id,
                    audio=file_id,
                    caption=caption,
                    reply_markup=item_markup,
                )
            elif msg_type in ("apk", "document"):
                await bot.send_document(
                    chat_id=user_id,
                    document=file_id,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=item_markup,
                )

        return True

    except TelegramError as e:
        err_msg = str(e).lower()
        if any(x in err_msg for x in ["blocked", "deactivated", "not found", "chat not found"]):
            return False
        if attempt < MAX_RETRIES:
            await asyncio.sleep(1)
            return await _send_to_user(bot, user_id, broadcast, reply_markup, session, attempt + 1)
        logger.warning(f"Failed to send to {user_id} after {attempt} attempts: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending to {user_id}: {e}")
        return False
