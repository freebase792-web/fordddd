"""
NexusBot — Main Entry Point
Combines the Telegram bot (webhook mode) with the Flask admin panel.
Runs on a single Render web service process.
"""
import os
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)

from bot.models.database import init_db
from bot.handlers.start import start_handler
from bot.handlers.callbacks import callback_router
from bot.handlers.admin_upload import (
    admin_file_handler, admin_text_handler,
    admin_callback_handler, ADMIN_TELEGRAM_ID
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 8000))

# Build the PTB application (shared across requests)
_ptb_app: Application = None


def register_handlers(app: Application) -> None:
    """Register all bot handlers on the given application instance."""
    # ── Admin-only handlers (run BEFORE user handlers) ──────────────
    # These only activate if sender is the designated admin user ID.
    if ADMIN_TELEGRAM_ID:
        admin_filter = filters.User(user_id=ADMIN_TELEGRAM_ID)

        # Admin sends a file (APK, video, image, voice, audio, GIF)
        app.add_handler(MessageHandler(
            admin_filter & (
                filters.Document.ALL | filters.VIDEO |
                filters.PHOTO | filters.VOICE |
                filters.AUDIO | filters.ANIMATION
            ),
            admin_file_handler,
        ), group=0)

        # Admin sends text (e.g. version number after APK upload)
        app.add_handler(MessageHandler(
            admin_filter & filters.TEXT & ~filters.COMMAND,
            admin_text_handler,
        ), group=0)

        # Admin inline button callbacks (e.g. "Save as Content")
        app.add_handler(CallbackQueryHandler(
            admin_callback_handler,
            pattern="^admin_",
        ), group=0)
        
        # Admin sends /admin command
        app.add_handler(CommandHandler("admin", start_handler), group=0)

    # ── Regular user handlers ────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_handler), group=1)
    app.add_handler(CallbackQueryHandler(callback_router), group=1)


def get_ptb_app() -> Application:
    global _ptb_app
    if _ptb_app is None:
        _ptb_app = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )
        register_handlers(_ptb_app)
    return _ptb_app



