"""
NexusBot Database Models — Firebase Realtime Database Engine
Replaces SQLite/SQLAlchemy to provide 100% cloud persistence across Render redeploys and restarts.
Supports SQLAlchemy binary filter expressions via a custom FieldDescriptor.
"""
import os
import json
import time
import logging
import urllib.request
from datetime import datetime

FIREBASE_URL = "https://th-adult-default-rtdb.firebaseio.com"
FIREBASE_SECRET = "SwPMWuSbhRicoEi3XiJycMDgu0bxLvyUeqLLNrM5"

logger = logging.getLogger(__name__)


def fb_request(method, path, data=None):
    """Make HTTP REST API request to Firebase RTDB."""
    url = f"{FIREBASE_URL}/{path.lstrip('/')}.json?auth={FIREBASE_SECRET}"
    try:
        req_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=req_data, method=method)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Firebase RTDB Error on {method} {path}: {e}")
        return None


def parse_date(date_str):
    """Convert ISO date string from Firebase to datetime object."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        return None


def format_date(dt):
    """Convert datetime object to ISO string for Firebase."""
    if not dt:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


class FieldDescriptor:
    """Emulates SQLAlchemy class attribute comparison descriptors for python classes."""
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return f"{self.name} == {other}"

    def __ne__(self, other):
        return f"{self.name} != {other}"

    def asc(self):
        return self

    def desc(self):
        return self

    def __str__(self):
        return self.name


class User:
    id = FieldDescriptor("id")
    username = FieldDescriptor("username")
    first_name = FieldDescriptor("first_name")
    last_name = FieldDescriptor("last_name")
    language_code = FieldDescriptor("language_code")
    joined_at = FieldDescriptor("joined_at")
    last_active = FieldDescriptor("last_active")
    is_banned = FieldDescriptor("is_banned")
    referrer_id = FieldDescriptor("referrer_id")
    referral_code = FieldDescriptor("referral_code")
    referral_count = FieldDescriptor("referral_count")
    streak_count = FieldDescriptor("streak_count")
    streak_last_date = FieldDescriptor("streak_last_date")
    xp_points = FieldDescriptor("xp_points")
    question_answered = FieldDescriptor("question_answered")
    answer_yes = FieldDescriptor("answer_yes")
    downloaded_apk = FieldDescriptor("downloaded_apk")

    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.username = kwargs.get("username")
        self.first_name = kwargs.get("first_name")
        self.last_name = kwargs.get("last_name")
        self.language_code = kwargs.get("language_code", "en")
        self.joined_at = parse_date(kwargs.get("joined_at")) or datetime.utcnow()
        self.last_active = parse_date(kwargs.get("last_active")) or datetime.utcnow()
        self.is_banned = kwargs.get("is_banned", False)
        self.referrer_id = kwargs.get("referrer_id")
        self.referral_code = kwargs.get("referral_code")
        self.referral_count = kwargs.get("referral_count", 0)
        self.streak_count = kwargs.get("streak_count", 0)
        self.streak_last_date = parse_date(kwargs.get("streak_last_date"))
        self.xp_points = kwargs.get("xp_points", 0)
        self.question_answered = kwargs.get("question_answered", False)
        self.answer_yes = kwargs.get("answer_yes")
        self.downloaded_apk = kwargs.get("downloaded_apk", False)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "language_code": self.language_code,
            "joined_at": format_date(self.joined_at),
            "last_active": format_date(self.last_active),
            "is_banned": self.is_banned,
            "referrer_id": self.referrer_id,
            "referral_code": self.referral_code,
            "referral_count": self.referral_count,
            "streak_count": self.streak_count,
            "streak_last_date": format_date(self.streak_last_date),
            "xp_points": self.xp_points,
            "question_answered": self.question_answered,
            "answer_yes": self.answer_yes,
            "downloaded_apk": self.downloaded_apk
        }

    def get_display_name(self):
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return "User"


class Content:
    id = FieldDescriptor("id")
    content_type = FieldDescriptor("content_type")
    file_id = FieldDescriptor("file_id")
    file_name = FieldDescriptor("file_name")
    version = FieldDescriptor("version")
    changelog = FieldDescriptor("changelog")
    caption = FieldDescriptor("caption")
    text_content = FieldDescriptor("text_content")
    is_active = FieldDescriptor("is_active")
    order_index = FieldDescriptor("order_index")
    created_at = FieldDescriptor("created_at")

    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.content_type = kwargs.get("content_type")
        self.file_id = kwargs.get("file_id")
        self.file_name = kwargs.get("file_name")
        self.version = kwargs.get("version")
        self.changelog = kwargs.get("changelog")
        self.caption = kwargs.get("caption")
        self.text_content = kwargs.get("text_content")
        self.is_active = kwargs.get("is_active", True)
        self.order_index = kwargs.get("order_index", 0)

    def to_dict(self):
        return {
            "id": self.id,
            "content_type": self.content_type,
            "file_id": self.file_id,
            "file_name": self.file_name,
            "version": self.version,
            "changelog": self.changelog,
            "caption": self.caption,
            "text_content": self.text_content,
            "is_active": self.is_active,
            "order_index": self.order_index
        }


class Question:
    id = FieldDescriptor("id")
    question_text = FieldDescriptor("question_text")
    yes_label = FieldDescriptor("yes_label")
    no_label = FieldDescriptor("no_label")
    yes_response = FieldDescriptor("yes_response")
    no_response = FieldDescriptor("no_response")
    is_active = FieldDescriptor("is_active")
    order_index = FieldDescriptor("order_index")

    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.question_text = kwargs.get("question_text")
        self.yes_label = kwargs.get("yes_label", "✅ Yes, I'm in!")
        self.no_label = kwargs.get("no_label", "❌ Not now")
        self.yes_response = kwargs.get("yes_response")
        self.no_response = kwargs.get("no_response")
        self.is_active = kwargs.get("is_active", True)
        self.order_index = kwargs.get("order_index", 1)

    def to_dict(self):
        return {
            "id": self.id,
            "question_text": self.question_text,
            "yes_label": self.yes_label,
            "no_label": self.no_label,
            "yes_response": self.yes_response,
            "no_response": self.no_response,
            "is_active": self.is_active,
            "order_index": self.order_index
        }


class Broadcast:
    id = FieldDescriptor("id")
    message_type = FieldDescriptor("message_type")
    file_id = FieldDescriptor("file_id")
    caption = FieldDescriptor("caption")
    content_text = FieldDescriptor("content_text")
    has_apk_button = FieldDescriptor("has_apk_button")
    apk_button_text = FieldDescriptor("apk_button_text")
    status = FieldDescriptor("status")
    sent_count = FieldDescriptor("sent_count")
    failed_count = FieldDescriptor("failed_count")
    created_at = FieldDescriptor("created_at")
    completed_at = FieldDescriptor("completed_at")

    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.message_type = kwargs.get("message_type")
        self.file_id = kwargs.get("file_id")
        self.caption = kwargs.get("caption")
        self.content_text = kwargs.get("content_text")
        self.has_apk_button = kwargs.get("has_apk_button", False)
        self.apk_button_text = kwargs.get("apk_button_text", "⬇️ Download App")
        self.status = kwargs.get("status", "pending")
        self.sent_count = kwargs.get("sent_count", 0)
        self.failed_count = kwargs.get("failed_count", 0)
        self.created_at = parse_date(kwargs.get("created_at")) or datetime.utcnow()
        self.completed_at = parse_date(kwargs.get("completed_at"))

    def to_dict(self):
        return {
            "id": self.id,
            "message_type": self.message_type,
            "file_id": self.file_id,
            "caption": self.caption,
            "content_text": self.content_text,
            "has_apk_button": self.has_apk_button,
            "apk_button_text": self.apk_button_text,
            "status": self.status,
            "sent_count": self.sent_count,
            "failed_count": self.failed_count,
            "created_at": format_date(self.created_at),
            "completed_at": format_date(self.completed_at)
        }


class SubAdmin:
    telegram_id = FieldDescriptor("telegram_id")
    name = FieldDescriptor("name")
    username = FieldDescriptor("username")
    role = FieldDescriptor("role")
    added_by = FieldDescriptor("added_by")
    added_at = FieldDescriptor("added_at")
    is_active = FieldDescriptor("is_active")

    def __init__(self, **kwargs):
        self.telegram_id = kwargs.get("telegram_id")
        self.name = kwargs.get("name")
        self.username = kwargs.get("username")
        self.role = kwargs.get("role", "admin")
        self.added_by = kwargs.get("added_by")
        self.added_at = parse_date(kwargs.get("added_at")) or datetime.utcnow()
        self.is_active = kwargs.get("is_active", True)

    def to_dict(self):
        return {
            "telegram_id": self.telegram_id,
            "name": self.name,
            "username": self.username,
            "role": self.role,
            "added_by": self.added_by,
            "added_at": format_date(self.added_at),
            "is_active": self.is_active,
        }


class Analytics:
    id = FieldDescriptor("id")
    user_id = FieldDescriptor("user_id")
    event = FieldDescriptor("event")
    timestamp = FieldDescriptor("timestamp")
    metadata_ = FieldDescriptor("metadata_")

    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.user_id = kwargs.get("user_id")
        self.event = kwargs.get("event")
        self.timestamp = parse_date(kwargs.get("timestamp")) or datetime.utcnow()
        self.metadata_ = kwargs.get("metadata_")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event": self.event,
            "timestamp": format_date(self.timestamp),
            "metadata_": self.metadata_
        }


class BotConfig:
    key = FieldDescriptor("key")
    value = FieldDescriptor("value")

    def __init__(self, **kwargs):
        self.key = kwargs.get("key")
        self.value = kwargs.get("value")

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value
        }


class FirebaseQuery:
    def __init__(self, model_class, session):
        self.model_class = model_class
        self.session = session
        self._filters = {}
        self._limit = None

    def filter_by(self, **kwargs):
        self._filters.update(kwargs)
        return self

    def filter(self, *criterion):
        for c in criterion:
            c_str = str(c)
            if "==" in c_str:
                parts = c_str.split("==")
                key = parts[0].strip()
                val_str = parts[1].strip()
                if val_str == "True":
                    val = True
                elif val_str == "False":
                    val = False
                elif val_str == "None":
                    val = None
                elif val_str.isdigit():
                    val = int(val_str)
                else:
                    val = val_str.strip("'\"")
                self._filters[key] = val
            elif "!=" in c_str:
                parts = c_str.split("!=")
                key = parts[0].strip()
                val_str = parts[1].strip()
                if key == "content_type" and val_str.strip("'\"") == "apk":
                    self._filters["_not_apk"] = True
                elif key == "id":
                    try:
                        self._filters["_not_id"] = int(val_str)
                    except ValueError:
                        self._filters["_not_id"] = val_str.strip("'\"")
                else:
                    try:
                        self._filters[f"_not_{key}"] = int(val_str)
                    except ValueError:
                        self._filters[f"_not_{key}"] = val_str.strip("'\"")
            elif "content_type !=" in c_str or "content_type <>" in c_str:
                self._filters["_not_apk"] = True
            elif "is_active = 1" in c_str or "is_active = true" in c_str or "is_active == True" in c_str:
                self._filters["is_active"] = True
        return self

    def order_by(self, *args):
        return self

    def limit(self, limit_val):
        self._limit = limit_val
        return self

    def _fetch_all(self):
        path = self.model_class.__name__.lower() + "s"
        data = fb_request("GET", path) or {}
        
        if isinstance(data, list):
            items_iterator = [(str(idx), val) for idx, val in enumerate(data) if val is not None]
        elif isinstance(data, dict):
            items_iterator = data.items()
        else:
            items_iterator = []

        results = []
        for k, v in items_iterator:
            if v:
                v["id"] = int(k) if k.isdigit() else k
                obj = self.model_class(**v)
                results.append(obj)
        
        filtered = []
        for item in results:
            match = True
            for fk, fv in self._filters.items():
                if fk == "_not_apk":
                    if getattr(item, "content_type", None) == "apk":
                        match = False
                elif fk == "_not_id":
                    if getattr(item, "id", None) == fv:
                        match = False
                elif fk.startswith("_not_"):
                    real_key = fk.replace("_not_", "", 1)
                    if getattr(item, real_key, None) == fv:
                        match = False
                elif getattr(item, fk, None) != fv:
                    match = False
            if match:
                filtered.append(item)
        
        if self.model_class == Content:
            filtered.sort(key=lambda x: getattr(x, "order_index", 999))
        elif self.model_class == Broadcast:
            filtered.sort(key=lambda x: getattr(x, "created_at", datetime.min), reverse=True)
            
        if self._limit:
            filtered = filtered[:self._limit]
        return filtered

    def all(self):
        return self._fetch_all()

    def first(self):
        res = self._fetch_all()
        return res[0] if res else None

    def count(self):
        return len(self._fetch_all())

    def update(self, values):
        items = self._fetch_all()
        for item in items:
            for k, v in values.items():
                setattr(item, k, v)
            self.session.add(item)
        return len(items)


class FirebaseSession:
    def __init__(self):
        self.dirty = []

    def get(self, model_class, ident):
        path = f"{model_class.__name__.lower()}s/{ident}"
        data = fb_request("GET", path)
        if data:
            data["id"] = int(ident) if str(ident).isdigit() else ident
            return model_class(**data)
        return None

    def query(self, model_class):
        return FirebaseQuery(model_class, self)

    def add(self, obj):
        if obj not in self.dirty:
            self.dirty.append(obj)

    def delete(self, obj):
        """Delete an object from Firebase immediately."""
        path_prefix = obj.__class__.__name__.lower() + "s"
        path = f"{path_prefix}/{obj.id}"
        fb_request("DELETE", path)

    def commit(self):
        for obj in self.dirty:
            path_prefix = obj.__class__.__name__.lower() + "s"
            if getattr(obj, "id", None) is None:
                obj.id = int(time.time() * 1000)
            
            path = f"{path_prefix}/{obj.id}"
            fb_request("PUT", path, obj.to_dict())
        self.dirty.clear()

    def flush(self):
        """Intermediate flush emulated by commit."""
        self.commit()

    def rollback(self):
        self.dirty.clear()

    def close(self):
        self.dirty.clear()


# Export Session interface to match sessionmaker(bind=engine)
def Session():
    return FirebaseSession()


def get_config(key: str, default: str = "") -> str:
    """Get config string from Firebase."""
    val = fb_request("GET", f"config/{key}")
    if val is None:
        return default
    return str(val)


def set_config(key: str, value: str):
    """Set config string in Firebase."""
    fb_request("PUT", f"config/{key}", str(value))


def init_db():
    """Seed initial defaults in Firebase RTDB if missing."""
    # 1. Seed configs only if they don't exist
    if not get_config("welcome_text"):
        set_config("welcome_text", "Welcome to the Premium Portal! 🚀")
    if not get_config("yes_intro_text"):
        set_config("yes_intro_text", "🎊 *Amazing! You're in!*\n\nHere's your exclusive content package 👇")
    if not get_config("no_response_text"):
        set_config("no_response_text", "😢 No worries! Whenever you change your mind,\njust tap /start and we'll be here. 🌟")
    if not get_config("demo_closing_text"):
        set_config("demo_closing_text", "✨ *There you go, {name}!*\n\nDon't just run away now! Use the bottom buttons to download the APK and invite your friends. secretly... 🤫")
    if not get_config("bot_enabled"):
        set_config("bot_enabled", "true")
    if not get_config("demo_enabled"):
        set_config("demo_enabled", "true")
    
    # 2. Seed onboarding question only if there are NO questions in the database
    session = Session()
    try:
        q_count = session.query(Question).count()
        if q_count == 0:
            q = Question(
                id=1,
                question_text="Are you ready to unlock premium APK downloads?",
                yes_label="✅ Yes, I'm in!",
                no_label="❌ Not now",
                is_active=True,
                order_index=1
            )
            session.add(q)
            session.commit()
            logger.info("✅ Firebase RTDB database initialized and seeded successfully.")
    except Exception as e:
        logger.error(f"Failed to seed question: {e}")
    finally:
        session.close()
