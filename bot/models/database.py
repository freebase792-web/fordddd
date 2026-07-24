"""
NexusBot Database Models — Firebase Realtime Database Engine
Replaces SQLite/SQLAlchemy to provide 100% cloud persistence across Render redeploys and restarts.
Supports SQLAlchemy binary filter expressions via a custom FieldDescriptor.
"""
import os
import json
import time
import logging
import threading
import urllib.request
from datetime import datetime

FIREBASE_URL = os.environ.get("FIREBASE_URL", "https://th-adult-default-rtdb.firebaseio.com")
FIREBASE_SECRET = os.environ.get("FIREBASE_SECRET", "SwPMWuSbhRicoEi3XiJycMDgu0bxLvyUeqLLNrM5")

logger = logging.getLogger(__name__)


def fb_request(method, path, data=None, timeout=10):
    """Make HTTP REST API request to Firebase RTDB."""
    if "?" in path:
        url = f"{FIREBASE_URL}/{path.lstrip('/')}&auth={FIREBASE_SECRET}"
    else:
        url = f"{FIREBASE_URL}/{path.lstrip('/')}.json?auth={FIREBASE_SECRET}"
    try:
        req_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=req_data, method=method)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            if not body:
                return None
            return json.loads(body)
    except json.JSONDecodeError:
        return None
    except Exception as e:
        logger.error(f"Firebase RTDB Error on {method} {path}: {e}")
        return None


_query_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 10


def _cache_key(model_class, filters, suffix=""):
    return f"{model_class.__name__}:{json.dumps(filters, default=str)}:{suffix}"


def get_cached(key):
    with _cache_lock:
        entry = _query_cache.get(key)
        if entry and time.time() - entry["ts"] < CACHE_TTL:
            return entry["val"]
    return None


def set_cache(key, val):
    with _cache_lock:
        _query_cache[key] = {"ts": time.time(), "val": val}


def clear_cache(model_class=None):
    global _query_cache
    with _cache_lock:
        if model_class:
            prefix = model_class.__name__ + ":"
            _query_cache = {k: v for k, v in _query_cache.items() if not k.startswith(prefix)}
        else:
            _query_cache = {}


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
    link_url = FieldDescriptor("link_url")
    link_text = FieldDescriptor("link_text")

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
        self.created_at = parse_date(kwargs.get("created_at")) or datetime.utcnow()
        self.link_url = kwargs.get("link_url")
        self.link_text = kwargs.get("link_text", "🔗 Open Link")

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
            "order_index": self.order_index,
            "created_at": format_date(self.created_at),
            "link_url": self.link_url,
            "link_text": self.link_text
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
    link_url = FieldDescriptor("link_url")
    link_text = FieldDescriptor("link_text")
    status = FieldDescriptor("status")
    sent_count = FieldDescriptor("sent_count")
    failed_count = FieldDescriptor("failed_count")
    total_users = FieldDescriptor("total_users")
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
        self.link_url = kwargs.get("link_url")
        self.link_text = kwargs.get("link_text", "🔗 Open Link")
        self.status = kwargs.get("status", "pending")
        self.sent_count = kwargs.get("sent_count", 0)
        self.failed_count = kwargs.get("failed_count", 0)
        self.total_users = kwargs.get("total_users", 0)
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
            "link_url": self.link_url,
            "link_text": self.link_text,
            "status": self.status,
            "sent_count": self.sent_count,
            "failed_count": self.failed_count,
            "total_users": self.total_users,
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
        self._offset = 0

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

    def offset(self, offset_val):
        self._offset = offset_val
        return self

    def _fetch_all(self):
        path = self.model_class.__name__.lower() + "s"

        # For User queries, fetch IDs first (shallow) then fetch only needed records
        if self.model_class == User and (self._limit or self._offset or not self._filters):
            ids_data = fb_request("GET", path + "?shallow=true", timeout=15) or {}
            if isinstance(ids_data, dict):
                all_ids = []
                for k, v in ids_data.items():
                    if v is not None:
                        try:
                            all_ids.append(int(k) if k.isdigit() else k)
                        except ValueError:
                            all_ids.append(k)
                all_ids.sort(reverse=True)
                window = all_ids
                if self._offset:
                    window = window[self._offset:]
                if self._limit:
                    window = window[:self._limit]
                results = []
                for uid in window:
                    user_path = f"users/{uid}"
                    user_data = fb_request("GET", user_path, timeout=10)
                    if user_data:
                        user_data["id"] = uid if isinstance(uid, int) else uid
                        obj = self.model_class(**user_data)
                        results.append(obj)
                filtered = []
                for item in results:
                    match = True
                    for fk, fv in self._filters.items():
                        if fk.startswith("_"):
                            continue
                        if getattr(item, fk, None) != fv:
                            match = False
                            break
                    if match:
                        filtered.append(item)
                return filtered

        data = fb_request("GET", path, timeout=15) or {}

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

        if self._offset:
            filtered = filtered[self._offset:]
        if self._limit:
            filtered = filtered[:self._limit]
        return filtered

    def _fetch_ids_only(self):
        """Fetch just the keys/IDs without full records (shallow)."""
        path = self.model_class.__name__.lower() + "s?shallow=true"
        data = fb_request("GET", path) or {}
        if not isinstance(data, dict):
            return []
        ids = []
        for k in data:
            try:
                ids.append(int(k) if k.isdigit() else k)
            except ValueError:
                pass
        return ids

    def all(self):
        return self._fetch_all()

    def first(self):
        res = self._fetch_all()
        return res[0] if res else None

    def count(self):
        ck = _cache_key(self.model_class, self._filters, "count")
        cached = get_cached(ck)
        if cached is not None:
            return cached
        if not self._filters:
            ids = self._fetch_ids_only()
            val = len(ids)
        else:
            val = len(self._fetch_all())
        set_cache(ck, val)
        return val

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
        path_prefix = obj.__class__.__name__.lower() + "s"
        path = f"{path_prefix}/{obj.id}"
        fb_request("DELETE", path)
        clear_cache(obj.__class__)

    def commit(self):
        changed_classes = set()
        for obj in self.dirty:
            path_prefix = obj.__class__.__name__.lower() + "s"
            if getattr(obj, "id", None) is None:
                obj.id = int(time.time() * 1000)
            path = f"{path_prefix}/{obj.id}"
            result = fb_request("PUT", path, obj.to_dict())
            if result is None:
                raise RuntimeError(f"Firebase write failed for {path}")
            changed_classes.add(obj.__class__)
        self.dirty.clear()
        for cls in changed_classes:
            clear_cache(cls)

    def flush(self):
        self.commit()

    def rollback(self):
        self.dirty.clear()

    def close(self):
        self.dirty.clear()

    def get_user_ids(self, only_active=True):
        """Get all user IDs from Firebase using shallow=true (no full records)."""
        import time
        for attempt in range(3):
            data = fb_request("GET", "users?shallow=true", timeout=15)
            if data and isinstance(data, dict):
                ids = []
                for k, v in data.items():
                    if v is not None:
                        try:
                            ids.append(int(k) if k.isdigit() else k)
                        except ValueError:
                            pass
                return ids
            if attempt < 2:
                time.sleep(1)
        return []

    def get_users_by_ids(self, ids):
        """Fetch multiple users by their IDs in batch (one request per user)."""
        users = []
        for uid in ids:
            u = self.get(User, uid)
            if u:
                users.append(u)
        return users


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
