"""
NexusBot Database Models
Full SQLAlchemy ORM schema with all tables needed for the bot.
"""
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, BigInteger, Integer, String, Text,
    Boolean, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///nexusbot.db")

# Fix for Render's postgres:// vs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool if "postgresql" in DATABASE_URL else None,
    echo=False
)

Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)  # Telegram user_id
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    language_code = Column(String(10), default="en")
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    is_banned = Column(Boolean, default=False)
    referrer_id = Column(BigInteger, nullable=True)
    referral_code = Column(String(20), unique=True, nullable=True)
    referral_count = Column(Integer, default=0)
    streak_count = Column(Integer, default=0)
    streak_last_date = Column(DateTime, nullable=True)
    xp_points = Column(Integer, default=0)
    question_answered = Column(Boolean, default=False)
    answer_yes = Column(Boolean, nullable=True)

    def get_display_name(self):
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return f"User{self.id}"


class BotConfig(Base):
    __tablename__ = "bot_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_text = Column(Text, nullable=False)
    yes_label = Column(String(100), default="✅ Yes, I'm in!")
    no_label = Column(String(100), default="❌ Not now")
    yes_response = Column(Text, nullable=True)
    no_response = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Content(Base):
    __tablename__ = "content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_type = Column(String(50), nullable=False)  # video, text, apk, image, voice, audio
    file_id = Column(String(500), nullable=True)       # Telegram file_id
    file_name = Column(String(255), nullable=True)
    caption = Column(Text, nullable=True)
    text_content = Column(Text, nullable=True)         # for plain text content
    version = Column(String(50), nullable=True)        # for APK versioning
    changelog = Column(Text, nullable=True)            # for APK changelog
    is_active = Column(Boolean, default=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_type = Column(String(50), nullable=False)  # text, voice, image, video, apk, audio
    content_text = Column(Text, nullable=True)
    file_id = Column(String(500), nullable=True)
    caption = Column(Text, nullable=True)
    has_apk_button = Column(Boolean, default=False)    # include APK download button
    apk_button_text = Column(String(100), default="⬇️ Download App")
    status = Column(String(50), default="pending")     # pending, sending, done, failed
    total_users = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    created_by = Column(String(100), default="admin")


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    event = Column(String(100), nullable=False)        # start, yes, no, apk_download, video_view, etc.
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(engine)
    _seed_defaults()
    print("✅ Database initialized successfully.")


def _seed_defaults():
    """Seed default config values if not present."""
    session = Session()
    try:
        defaults = {
            "welcome_text": (
                "🎉 *Welcome to NexusBot!*\n\n"
                "You're about to unlock something incredible.\n"
                "Tap the button below to begin your journey! 🚀"
            ),
            "welcome_gif_id": "",           # Telegram file_id for welcome GIF/sticker
            "bot_enabled": "true",
            "maintenance_message": (
                "🔧 We're upgrading the experience.\n"
                "We'll be back shortly. Stay tuned! 💫"
            ),
            "no_response_text": (
                "😢 No worries! Whenever you change your mind,\n"
                "just tap /start and we'll be here waiting. 🌟"
            ),
            "yes_intro_text": (
                "🎊 *Amazing! You're in!*\n\n"
                "Here's your exclusive content package 👇"
            ),
            "apk_button_text": "⬇️ Download App",
        }
        for key, value in defaults.items():
            existing = session.get(BotConfig, key)
            if not existing:
                session.add(BotConfig(key=key, value=value))
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Seed warning: {e}")
    finally:
        session.close()


def get_config(key: str, default: str = "") -> str:
    """Get a bot config value."""
    session = Session()
    try:
        cfg = session.get(BotConfig, key)
        return cfg.value if cfg else default
    finally:
        session.close()


def set_config(key: str, value: str):
    """Set a bot config value."""
    session = Session()
    try:
        cfg = session.get(BotConfig, key)
        if cfg:
            cfg.value = value
            cfg.updated_at = datetime.utcnow()
        else:
            session.add(BotConfig(key=key, value=value))
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
