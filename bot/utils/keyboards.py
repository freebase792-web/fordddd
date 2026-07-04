"""
Reusable Telegram keyboard/button builders for NexusBot.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def user_reply_keyboard() -> ReplyKeyboardMarkup:
    """Return the persistent bottom Reply Keyboard matching the user's screenshot."""
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Download APK")],
        [KeyboardButton("🌸 See Demo")]
    ], resize_keyboard=True, persistent=True)


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


def content_keyboard(apk_version: str = None, apk_button_text: str = "Download APK") -> InlineKeyboardMarkup:
    """Content screen buttons matching user's reference image."""
    buttons = []
    # Button 1: Download APK
    btn_text = f"📱 {apk_button_text}"
    if apk_version:
        btn_text = f"📱 {apk_button_text} v{apk_version}"
    buttons.append([InlineKeyboardButton(btn_text, callback_data="download_apk")])
    
    # Button 2: See Demo
    buttons.append([InlineKeyboardButton("🌸 See Demo", callback_data="show_content")])
    
    # Button 3: Referrals
    buttons.append([InlineKeyboardButton("🔗 Share & Earn XP", callback_data="get_referral")])
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


def admin_panel_keyboard(demo_on: bool = True, bot_active: bool = True) -> InlineKeyboardMarkup:
    """Construct the Telegram-based Admin Panel controls matching the user's requested layout."""
    demo_status = "🟢 Demo Content: ON" if demo_on else "🔴 Demo Content: OFF"
    bot_status = "🟢 Bot: ACTIVE" if bot_active else "🟡 Bot: MAINTENANCE"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Broadcast Media 📢", callback_data="admin_prompt_broadcast_media")],
        [InlineKeyboardButton("📲 Quick Send APK To All 📲", callback_data="admin_broadcast_apk")],
        [
            InlineKeyboardButton(demo_status, callback_data="admin_toggle_demo"),
            InlineKeyboardButton(bot_status, callback_data="admin_toggle_maintenance")
        ],
        [
            InlineKeyboardButton("📱 Set APK 📱", callback_data="admin_prompt_set_apk"),
            InlineKeyboardButton("🗑️ Remove APK 🗑️", callback_data="admin_remove_apk")
        ],
        [
            InlineKeyboardButton("🖼️ Set App Icon 🖼️", callback_data="admin_prompt_app_icon"),
            InlineKeyboardButton("🌸 Set Demo Media 🌸", callback_data="admin_prompt_demo")
        ],
        [
            InlineKeyboardButton("📛 APK Display Name 📛", callback_data="admin_prompt_apk_name"),
            InlineKeyboardButton("💬 APK Caption 💬", callback_data="admin_prompt_apk_caption")
        ],
        [
            InlineKeyboardButton("📝 Welcome Message 📝", callback_data="admin_prompt_welcome"),
            InlineKeyboardButton("📊 Get Stats Report 📊", callback_data="admin_get_report")
        ],
        [
            InlineKeyboardButton("❓ Help Guide ❓", callback_data="admin_how_to_use"),
            InlineKeyboardButton("❌ Close Panel", callback_data="admin_cancel")
        ]
    ])

