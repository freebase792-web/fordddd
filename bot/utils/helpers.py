"""
Utility helpers for NexusBot.
"""
import random
import string
from datetime import datetime, date


STREAK_EMOJIS = ["🔥", "🔥🔥", "🔥🔥🔥", "💎", "👑", "🏆", "⚡", "🌟"]
XP_EVENTS = {
    "start": 10,
    "answer_yes": 50,
    "answer_no": 5,
    "download_apk": 100,
    "referral_joined": 200,
    "daily_streak": 25,
}


def generate_referral_code(user_id: int) -> str:
    """Generate a unique referral code for a user."""
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"NX{user_id}{suffix}"


def get_streak_emoji(streak: int) -> str:
    """Get emoji based on streak count."""
    idx = min(streak - 1, len(STREAK_EMOJIS) - 1)
    return STREAK_EMOJIS[max(0, idx)]


def format_streak_message(streak: int) -> str:
    """Format a streak message for the user."""
    emoji = get_streak_emoji(streak)
    if streak == 1:
        return f"{emoji} Day 1 streak — you're just getting started!"
    elif streak < 7:
        return f"{emoji} {streak}-day streak — keep it going!"
    elif streak < 30:
        return f"{emoji} {streak}-day streak — you're on fire!"
    else:
        return f"{emoji} {streak}-day streak — LEGENDARY status! 👑"


def calculate_xp_for_event(event: str) -> int:
    return XP_EVENTS.get(event, 0)


def format_xp_level(xp: int) -> dict:
    """Return level info based on XP."""
    levels = [
        (0, "Newcomer 🌱"),
        (100, "Explorer 🗺️"),
        (300, "Adventurer ⚔️"),
        (600, "Champion 🏅"),
        (1000, "Legend 🌟"),
        (2000, "Mythic 💎"),
        (5000, "GOD MODE 👑"),
    ]
    current_level = levels[0]
    next_level = levels[1] if len(levels) > 1 else None
    for i, (xp_req, name) in enumerate(levels):
        if xp >= xp_req:
            current_level = (xp_req, name)
            next_level = levels[i + 1] if i + 1 < len(levels) else None
    return {
        "name": current_level[1],
        "xp": xp,
        "next_at": next_level[0] if next_level else None,
        "next_name": next_level[1] if next_level else "MAX LEVEL 🏆",
    }


def update_streak(user) -> bool:
    """Update user streak. Returns True if streak was incremented."""
    today = date.today()
    if user.streak_last_date is None:
        user.streak_count = 1
        user.streak_last_date = datetime.utcnow()
        return True
    last_date = user.streak_last_date.date() if isinstance(user.streak_last_date, datetime) else user.streak_last_date
    delta = (today - last_date).days
    if delta == 0:
        return False  # Already updated today
    elif delta == 1:
        user.streak_count += 1
        user.streak_last_date = datetime.utcnow()
        return True
    else:
        user.streak_count = 1  # Reset streak
        user.streak_last_date = datetime.utcnow()
        return True


def escape_md(text: str) -> str:
    """Escape Markdown V2 special characters."""
    special = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in special else c for c in text)
