"""
Reusable Telegram keyboard/button builders for NexusBot.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def start_keyboard() -> InlineKeyboardMarkup:
    """Welcome screen 'Let's Go' button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Let's Go!", callback_data="show_question")]
    ])


def question_keyboard(yes_label: str = "✅ Yes, I'm in!", no_label: str = "❌ Not now") -> InlineKeyboardMarkup:
    """Yes / No question buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(yes_label, callback_data="answer_yes"),
            InlineKeyboardButton(no_label, callback_data="answer_no"),
        ]
    ])


def reconsider_keyboard() -> InlineKeyboardMarkup:
    """Shown after NO answer — let them reconsider."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 Actually, I changed my mind!", callback_data="answer_yes")],
        [InlineKeyboardButton("🔗 Share with a friend", callback_data="get_referral")],
    ])


def content_keyboard(apk_version: str = None, apk_button_text: str = "⬇️ Download App") -> InlineKeyboardMarkup:
    """Content screen buttons shown after YES."""
    buttons = []
    if apk_version:
        buttons.append([InlineKeyboardButton(
            f"{apk_button_text} v{apk_version}", callback_data="download_apk"
        )])
    buttons.append([InlineKeyboardButton("🔗 Invite Friends & Earn XP", callback_data="get_referral")])
    buttons.append([InlineKeyboardButton("📊 My Stats", callback_data="my_stats")])
    return InlineKeyboardMarkup(buttons)


def apk_download_keyboard(apk_version: str, apk_button_text: str = "⬇️ Download App") -> InlineKeyboardMarkup:
    """Standalone APK download button (used in broadcasts)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{apk_button_text} v{apk_version}", callback_data="download_apk")]
    ])


def back_to_content_keyboard() -> InlineKeyboardMarkup:
    """Button to go back to content after downloading APK."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Back to Content", callback_data="show_content")],
        [InlineKeyboardButton("🔗 Invite Friends", callback_data="get_referral")],
    ])


def stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 See Content Again", callback_data="show_content")],
        [InlineKeyboardButton("🔗 Get Referral Link", callback_data="get_referral")],
    ])
