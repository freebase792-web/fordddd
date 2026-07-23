"""
Admin Telegram Handler — For the bot owner only.
Provides a complete, rich, interactive Admin Control Panel directly in Telegram.
Includes: Set APK, Send APK to All, set Welcome Text, set Demo, statistics reports, and real-time logs.
"""

import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from bot.models.database import Session, Content, BotConfig, set_config, get_config, User, Broadcast, Analytics, fb_request

logger = logging.getLogger(__name__)

# Admin Telegram User ID — only this user can access admin functions
ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))


def is_admin(user_id: int) -> bool:
    if ADMIN_TELEGRAM_ID != 0 and user_id == ADMIN_TELEGRAM_ID:
        return True
    data = fb_request("GET", f"sub_admins/{user_id}")
    return bool(data and data.get("is_active", False))


def get_admin_role(user_id: int) -> str:
    if ADMIN_TELEGRAM_ID != 0 and user_id == ADMIN_TELEGRAM_ID:
        return "super_admin"
    return "admin"


async def _make_sub_admin(message, target_id, target_name, target_username, adder_id):
    fb_request("PUT", f"sub_admins/{target_id}", {
        "telegram_id": target_id,
        "name": target_name or "Sub Admin",
        "username": target_username or "",
        "role": "admin",
        "added_by": adder_id,
        "added_at": datetime.utcnow().isoformat(),
        "is_active": True,
    })
    auth_username = target_username or f"user_{target_id}"
    fb_request("PUT", f"sub_admin_auth/{auth_username}", {
        "username": auth_username,
        "password": "subadmin123",
        "telegram_id": target_id,
        "role": "admin",
    })
    await message.reply_text(
        f"✅ *{target_name or 'User'} is now a Sub Admin!*\n\n"
        f"Default login: username `{auth_username}`, password `subadmin123`\n"
        f"Tell them to send /admin to access the panel.",
        parse_mode=ParseMode.MARKDOWN
    )


async def _safe_edit(query, text, **kwargs):
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            await query.answer()
        else:
            raise


async def _remove_sub_admin_render(query, user_id, chat_id):
    fb_request("PUT", f"sub_admins/{user_id}", {"is_active": False})
    await query.answer("Sub-admin removed.")
    sub_admin_data = fb_request("GET", "sub_admins") or {}
    msg_lines = ["👥 *Sub Admins:*\n"]
    keyboard_buttons = []
    if sub_admin_data and isinstance(sub_admin_data, dict):
        for tid, info in sub_admin_data.items():
            if info and info.get("is_active"):
                name = info.get("name", "Unknown")
                username = info.get("username", "")
                label = f"{name} (@{username})" if username else name
                msg_lines.append(f"• {label}")
                keyboard_buttons.append([
                    InlineKeyboardButton(f"❌ Remove {name}", callback_data=f"admin_remove_sub_admin_{tid}")
                ])
    else:
        msg_lines.append("_No sub-admins appointed._")
    keyboard_buttons.append([InlineKeyboardButton("➕ Add Sub Admin", callback_data="admin_prompt_add_sub_admin")])
    keyboard_buttons.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back_to_panel")])
    await _safe_edit(query, "\n".join(msg_lines), parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard_buttons))


async def admin_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles any file/media sent directly to the bot by the admin.
    """
    user = update.effective_user
    if not is_admin(user.id):
        return

    message = update.message
    chat_id = update.effective_chat.id

    # Check if super admin is adding a sub-admin (via forward or paste user ID)
    if context.user_data.get("awaiting_sub_admin_forward"):
        context.user_data.pop("awaiting_sub_admin_forward", None)
        fwd_from = message.forward_from if hasattr(message, 'forward_from') else None
        target_id = None
        target_name = None
        target_username = None

        if fwd_from:
            target_id = fwd_from.id
            target_name = fwd_from.first_name or "Sub Admin"
            target_username = fwd_from.username or ""
        elif message.text and message.text.strip().isdigit():
            target_id = int(message.text.strip())
            target_name = "Sub Admin (ID)"
            target_username = ""

        if not target_id:
            await message.reply_text(
                "❌ Forward a message from the user, or paste their Telegram User ID.\n\n"
                "📌 To get someone's ID: forward their message to @userinfobot"
            )
            return

        await _make_sub_admin(message, target_id, target_name, target_username, user.id)
        return

    file_id = None
    content_type = None
    file_name = None
    detected_label = ""

    if message.document:
        doc = message.document
        file_id = doc.file_id
        file_name = doc.file_name or "file"
        if doc.mime_type == "application/vnd.android.package-archive" or (file_name and file_name.lower().endswith(".apk")):
            content_type = "apk"
            detected_label = "📱 APK File"
        else:
            content_type = "document"
            detected_label = f"📁 Document ({file_name})"

    elif message.video:
        file_id = message.video.file_id
        content_type = "video"
        file_name = message.video.file_name or "video.mp4"
        detected_label = "🎬 Video"

    elif message.photo:
        file_id = message.photo[-1].file_id
        content_type = "image"
        file_name = "photo.jpg"
        detected_label = "🖼️ Image"

    elif message.voice:
        file_id = message.voice.file_id
        content_type = "voice"
        file_name = "voice.ogg"
        detected_label = "🎵 Voice Note"

    elif message.audio:
        file_id = message.audio.file_id
        content_type = "audio"
        file_name = message.audio.file_name or "audio.mp3"
        detected_label = "🎤 Audio"

    elif message.animation:
        file_id = message.animation.file_id
        content_type = "image"
        file_name = "animation.gif"
        detected_label = "🎞️ GIF / Animation"

    if not file_id:
        return

    # Check if we are waiting for an app icon image
    if context.user_data.get("awaiting_app_icon"):
        context.user_data.pop("awaiting_app_icon", None)
        set_config("apk_icon_file_id", file_id)
        await message.reply_text(
            f"✅ *App Icon Updated successfully!*\n\n"
            f"File ID: `{file_id}`\n"
            f"Users will now see this icon before downloading the APK.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if we are compiling a multi-media demo sequence
    demo_list = context.user_data.get("awaiting_demo_media_list")
    if demo_list is not None:
        demo_list.append({
            "content_type": content_type,
            "file_id": file_id,
            "caption": message.caption or "",
            "text_content": ""
        })
        context.user_data["awaiting_demo_media_list"] = demo_list

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Save Demo", callback_data="admin_confirm_demo_media_done")],
            [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
        ])

        await message.reply_text(
            f"🌸 *Added to Demo sequence!*\n\n"
            f"• Type: `{content_type}`\n"
            f"• Total Items: *{len(demo_list)}*\n\n"
            f"Send more text or media to add, or tap **Save Demo** to confirm.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        return

    # Check if we are compiling a multi-media broadcast list
    media_list = context.user_data.get("awaiting_broadcast_media_list")
    if media_list is not None:
        media_list.append({
            "type": content_type,
            "file_id": file_id,
            "caption": message.caption or ""
        })
        context.user_data["awaiting_broadcast_media_list"] = media_list

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done (Confirm)", callback_data="admin_confirm_bc_media_done")],
            [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
        ])

        await message.reply_text(
            f"📁 *Added to Broadcast list!*\n\n"
            f"• Type: `{content_type}`\n"
            f"• Total Items: *{len(media_list)}*\n\n"
            f"Send more text/files to add, or tap **Done** to proceed.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        return

    # Check if we are waiting for broadcast content
    if context.user_data.get("awaiting_broadcast_content"):
        context.user_data.pop("awaiting_broadcast_content", None)
        context.user_data["broadcast_file_id"] = file_id
        context.user_data["broadcast_type"] = content_type
        context.user_data["broadcast_caption"] = message.caption or ""
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Attach APK Button", callback_data="admin_confirm_bc_yes_apk"),
                InlineKeyboardButton("❌ No APK Button", callback_data="admin_confirm_bc_no_apk")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
        ])
        
        await message.reply_text(
            f"📢 *Broadcast {detected_label} Content Saved!*\n\n"
            f"Do you want to attach the APK download button below this broadcast?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        return

    # Check if we were specifically waiting for a demo file
    if context.user_data.get("awaiting_demo_file"):
        context.user_data.pop("awaiting_demo_file", None)
        session = Session()
        try:
            # Archive old demo content
            session.query(Content).filter(Content.content_type != "apk").update({"is_active": False})
            
            # Save new demo file
            new_demo = Content(
                content_type=content_type,
                file_id=file_id,
                file_name=file_name,
                caption=message.caption or "Check out the exclusive demo! 🌸",
                is_active=True,
                order_index=1,
            )
            session.add(new_demo)
            session.commit()
            
            # Set welcome GIF/animation if it is an animation
            if content_type == "image" and file_name.endswith(".gif"):
                set_config("welcome_gif_id", file_id)

            await message.reply_text(
                f"🌸 *Demo Content Updated successfully!*\n\n"
                f"Saved a *{content_type}* file as the active user demo view.",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            session.rollback()
            await message.reply_text(f"❌ Error setting demo: {e}")
        finally:
            session.close()
        return

    # Store file_id in context for callback
    context.user_data["pending_file_id"] = file_id
    context.user_data["pending_file_name"] = file_name
    context.user_data["pending_content_type"] = content_type
    context.user_data["pending_caption"] = message.caption or ""

    # If it is an APK, run the APK version prompt flow
    if content_type == "apk":
        await _save_apk_prompt(update, context, file_id, file_name, message.caption or "")
        return

    # For other items, show selection menu
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌸 Set as Demo content", callback_data="admin_set_as_demo"),
            InlineKeyboardButton("📦 Add to General Content", callback_data="admin_save_content"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
    ])

    await message.reply_text(
        f"✅ *{detected_label} received!*\n\n"
        f"Choose what to do with this file:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def _save_apk_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    file_name: str,
    caption: str,
):
    """Instantly save and activate the new APK with auto-incremented versioning."""
    message = update.message
    session = Session()
    try:
        # Fetch the last active APK to auto-increment version
        last_apk = session.query(Content).filter_by(content_type="apk").order_by(Content.id.desc()).first()
        
        # Determine new version
        new_version = "1.0"
        if last_apk and last_apk.version:
            try:
                new_version = str(round(float(last_apk.version) + 0.1, 1))
            except ValueError:
                new_version = "1.0"

        # Archive old active APKs
        session.query(Content).filter_by(content_type="apk", is_active=True).update({"is_active": False})

        # Save and activate new APK
        new_apk = Content(
            content_type="apk",
            file_id=file_id,
            file_name=file_name,
            version=new_version,
            changelog=caption or "Performance improvements and bug fixes.",
            is_active=True,
        )
        session.add(new_apk)
        session.commit()

        # Keyboard options for quick edits or broadcast
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ Edit Version/Changelog", callback_data=f"admin_edit_apk_meta_{new_apk.id}"),
                InlineKeyboardButton("📲 Send to All Users", callback_data="admin_broadcast_apk")
            ],
            [InlineKeyboardButton("✅ Done", callback_data="admin_cancel")]
        ])

        await message.reply_text(
            f"🎉 *APK Uploaded & Activated Instantly!*\n\n"
            f"📱 File: `{file_name}`\n"
            f"📌 Version: *v{new_version}* (Auto-incremented)\n"
            f"📋 Changelog: _{caption or 'Performance improvements.'}_\n\n"
            f"🚀 *New users will now automatically download this version!*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

    except Exception as e:
        session.rollback()
        logger.error(f"Error auto-saving APK: {e}", exc_info=True)
        await message.reply_text(f"❌ Error saving APK: {e}")
    finally:
        session.close()


async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles text inputs from the admin when configuring values.
    """
    user = update.effective_user
    if not is_admin(user.id):
        return

    message = update.message
    text = message.text.strip()

    # Passthrough for reply keyboard buttons — route to user handler
    known_buttons = [
        "📱 Download APK", "🌸 See Demo", "🎁 See Content Again",
        "🌟 Actually, I changed my mind!",
        "🔗 Share with a friend", "🔗 Get Referral Link",
    ]
    if text in known_buttons:
        from bot.handlers.callbacks import user_text_handler
        await user_text_handler(update, context)
        return

    session = Session()

    try:
        # Check if super admin is adding a sub-admin (via forward, paste ID, or @username)
        if context.user_data.get("awaiting_sub_admin_forward"):
            context.user_data.pop("awaiting_sub_admin_forward", None)
            fwd_from = message.forward_from if hasattr(message, 'forward_from') else None
            target_id = None
            target_name = None
            target_username = None

            if fwd_from:
                target_id = fwd_from.id
                target_name = fwd_from.first_name or "Sub Admin"
                target_username = fwd_from.username or ""
            elif text.isdigit():
                target_id = int(text)
                target_name = "Sub Admin (ID)"
                target_username = ""
            elif text.startswith("@"):
                username = text.lstrip("@")
                try:
                    chat = await context.bot.get_chat("@" + username)
                    target_id = chat.id
                    target_name = chat.first_name or username
                    target_username = username
                except Exception:
                    await message.reply_text(
                        "❌ Could not find a user with that username. "
                        "Make sure the username is correct and they have started this bot."
                    )
                    return
            else:
                await message.reply_text(
                    "❌ Please forward a message from the user, paste their numeric User ID, "
                    "or send their @username."
                )
                return

            await _make_sub_admin(message, target_id, target_name, target_username, user.id)
            return

        # Check if we are compiling a multi-media demo sequence
        demo_list = context.user_data.get("awaiting_demo_media_list")
        if demo_list is not None:
            demo_list.append({
                "content_type": "text",
                "file_id": None,
                "caption": "",
                "text_content": text
            })
            context.user_data["awaiting_demo_media_list"] = demo_list

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Save Demo", callback_data="admin_confirm_demo_media_done")],
                [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
            ])

            await message.reply_text(
                f"✍️ *Text added to Demo sequence!*\n\n"
                f"• Preview: _{text[:60]}..._\n"
                f"• Total Items: *{len(demo_list)}*\n\n"
                f"Send more text or media to add, or tap **Save Demo** to confirm.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            return

        # Check if we are compiling a multi-media broadcast list
        media_list = context.user_data.get("awaiting_broadcast_media_list")
        if media_list is not None:
            media_list.append({
                "type": "text",
                "text": text
            })
            context.user_data["awaiting_broadcast_media_list"] = media_list

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Done (Confirm)", callback_data="admin_confirm_bc_media_done")],
                [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
            ])

            await message.reply_text(
                f"✍️ *Text Item added to Broadcast list!*\n\n"
                f"• Preview: _{text[:60]}..._\n"
                f"• Total Items: *{len(media_list)}*\n\n"
                f"Send more text/files to add, or tap **Done** to proceed.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            return

        # Check if we are waiting for broadcast text content
        if context.user_data.get("awaiting_broadcast_content"):
            context.user_data.pop("awaiting_broadcast_content", None)
            context.user_data["broadcast_text"] = text
            context.user_data["broadcast_type"] = "text"
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Attach APK Button", callback_data="admin_confirm_bc_yes_apk"),
                    InlineKeyboardButton("❌ No APK Button", callback_data="admin_confirm_bc_no_apk")
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
            ])
            
            await message.reply_text(
                f"📢 *Broadcast Text Content Saved!*\n\n"
                f"Do you want to attach the APK download button below this message?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            return

        # 1. Handling APK version/changelog input (custom metadata update)
        if context.user_data.get("awaiting_apk_version"):
            context.user_data.pop("awaiting_apk_version")
            lines = text.split("\n", 1)
            version = lines[0].strip()
            changelog = lines[1].strip() if len(lines) > 1 else ""

            apk_edit_id = context.user_data.pop("awaiting_apk_edit_id", None)
            
            if apk_edit_id:
                # Upgraded path: edit metadata on the auto-saved APK
                apk_item = session.query(Content).filter_by(id=apk_edit_id).first()
                if apk_item:
                    apk_item.version = version
                    apk_item.changelog = changelog
                    session.commit()
                    await message.reply_text(
                        f"✅ *APK Metadata Updated!*\n\n"
                        f"📱 File: `{apk_item.file_name}`\n"
                        f"📌 Custom Version: *v{version}*\n"
                        f"📋 Changelog: _{changelog or 'None'}_",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await message.reply_text("❌ Error: Could not locate the uploaded APK record.")
            else:
                # Fallback path (old code)
                file_id = context.user_data.pop("pending_file_id", None)
                file_name = context.user_data.pop("pending_file_name", "App.apk")

                session.query(Content).filter_by(content_type="apk", is_active=True).update({"is_active": False})
                new_apk = Content(
                    content_type="apk",
                    file_id=file_id,
                    file_name=file_name,
                    version=version,
                    changelog=changelog,
                    is_active=True,
                )
                session.add(new_apk)
                session.commit()

                await message.reply_text(
                    f"🎉 *Active APK Configured successfully!*\n\n"
                    f"📛 Name: `{file_name}`\n"
                    f"📌 Version: *v{version}*\n"
                    f"📋 Changelog: _{changelog or 'None'}_",
                    parse_mode=ParseMode.MARKDOWN
                )
            return

        # 2. Handling APK name update
        if context.user_data.get("awaiting_apk_name"):
            context.user_data.pop("awaiting_apk_name")
            active_apk = session.query(Content).filter_by(content_type="apk", is_active=True).first()
            if active_apk:
                active_apk.file_name = text
                session.commit()
                await message.reply_text(f"✅ APK File Name set to: `{text}`")
            else:
                await message.reply_text("⚠️ No active APK found. Upload an APK file first!")
            return

        # 3. Handling APK caption update
        if context.user_data.get("awaiting_apk_caption"):
            context.user_data.pop("awaiting_apk_caption")
            active_apk = session.query(Content).filter_by(content_type="apk", is_active=True).first()
            if active_apk:
                active_apk.changelog = text
                session.commit()
                await message.reply_text(f"✅ APK Caption/Changelog set to:\n_{text}_", parse_mode=ParseMode.MARKDOWN)
            else:
                await message.reply_text("⚠️ No active APK found. Upload an APK file first!")
            return

        # 4. Handling welcome text update
        if context.user_data.get("awaiting_welcome_text"):
            context.user_data.pop("awaiting_welcome_text")
            set_config("welcome_text", text)
            await message.reply_text(f"✅ Welcome message updated successfully to:\n\n{text}", parse_mode=ParseMode.MARKDOWN)
            return

        # 5. Handling onboarding question update
        if context.user_data.get("awaiting_onboarding_question"):
            context.user_data.pop("awaiting_onboarding_question")
            from bot.models.database import Question
            q_item = session.query(Question).filter_by(is_active=True).first()
            if q_item:
                q_item.question_text = text
            else:
                q_item = Question(question_text=text, is_active=True)
                session.add(q_item)
            session.commit()
            await message.reply_text(f"✅ Onboarding Question updated successfully to:\n\n_{text}_", parse_mode=ParseMode.MARKDOWN)
            return

        # 6. Handling YES option label update
        if context.user_data.get("awaiting_yes_label"):
            context.user_data.pop("awaiting_yes_label")
            from bot.models.database import Question
            q_item = session.query(Question).filter_by(is_active=True).first()
            if q_item:
                q_item.yes_label = text
            else:
                q_item = Question(question_text="Are you ready?", yes_label=text, is_active=True)
                session.add(q_item)
            session.commit()
            await message.reply_text(f"✅ YES button option label updated to: `{text}`")
            return

        # 7. Handling NO option label update
        if context.user_data.get("awaiting_no_label"):
            context.user_data.pop("awaiting_no_label")
            from bot.models.database import Question
            q_item = session.query(Question).filter_by(is_active=True).first()
            if q_item:
                q_item.no_label = text
            else:
                q_item = Question(question_text="Are you ready?", no_label=text, is_active=True)
                session.add(q_item)
            session.commit()
            await message.reply_text(f"✅ NO button option label updated to: `{text}`")
            return

        # 8. Handling demo closing message update
        if context.user_data.get("awaiting_demo_msg"):
            context.user_data.pop("awaiting_demo_msg")
            set_config("demo_closing_text", text)
            await message.reply_text(f"✅ Demo closing message updated successfully to:\n\n{text}", parse_mode=ParseMode.MARKDOWN)
            return

    except Exception as e:
        session.rollback()
        logger.error(f"Admin text config error: {e}", exc_info=True)
        await message.reply_text(f"❌ Error: {e}")
    finally:
        session.close()


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Admin Panel button callbacks."""
    user = update.effective_user
    if not is_admin(user.id):
        return

    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    session = Session()

    try:
        if data.startswith("admin_edit_apk_meta_"):
            apk_id = int(data.split("_")[-1])
            context.user_data["awaiting_apk_version"] = True
            context.user_data["awaiting_apk_edit_id"] = apk_id
            await context.bot.send_message(
                chat_id=chat_id,
                text="✏️ *Please reply with the custom version and changelog.* \n\nFormat:\n`2.0\nYour changelog here...`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if data == "admin_save_content":
            file_id = context.user_data.pop("pending_file_id", None)
            file_name = context.user_data.pop("pending_file_name", "file")
            content_type = context.user_data.pop("pending_content_type", "document")
            caption = context.user_data.pop("pending_caption", "")
            
            max_order = 0
            for item in session.query(Content).all():
                if item.order_index and item.order_index > max_order:
                    max_order = item.order_index
            
            new_item = Content(
                content_type=content_type,
                file_id=file_id,
                file_name=file_name,
                caption=caption or None,
                is_active=True,
                order_index=max_order + 1,
            )
            session.add(new_item)
            session.commit()
            await query.edit_message_text(f"✅ General content added successfully at order position {max_order + 1}.")

        elif data == "admin_set_as_demo":
            file_id = context.user_data.pop("pending_file_id", None)
            file_name = context.user_data.pop("pending_file_name", "file")
            content_type = context.user_data.pop("pending_content_type", "document")
            caption = context.user_data.pop("pending_caption", "")

            # Archive old demos
            session.query(Content).filter(Content.content_type != "apk").update({"is_active": False})

            new_demo = Content(
                content_type=content_type,
                file_id=file_id,
                file_name=file_name,
                caption=caption or "Here is your exclusive demo content! 🌸",
                is_active=True,
                order_index=1,
            )
            session.add(new_demo)
            session.commit()
            await query.edit_message_text(f"🌸 Demo content set successfully to the new *{content_type}* file.")

        elif data == "admin_prompt_set_apk":
            await context.bot.send_message(
                chat_id=chat_id,
                text="📤 *Please send the new .apk file directly to this chat.*",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_remove_apk":
            session.query(Content).filter_by(content_type="apk").update({"is_active": False})
            session.commit()
            await query.edit_message_text("🗑️ Active APK has been removed. Users can no longer download it.")

        elif data == "admin_prompt_apk_name":
            context.user_data["awaiting_apk_name"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="✏️ *Please reply with the name you want to display for the APK file:*",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_prompt_apk_caption":
            context.user_data["awaiting_apk_caption"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="✏️ *Please reply with the caption / changelog description for the APK:*",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_prompt_welcome":
            context.user_data["awaiting_welcome_text"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="✏️ *Please reply with the new Welcome message text (Markdown supported):*",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_prompt_demo":
            context.user_data["awaiting_demo_media_list"] = []
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🌸 *Multi-Media Demo Builder active!* 🌸\n\n"
                    "Send me any files (videos, photos, voice notes, audio, text) one-by-one to build the demo sequence.\n\n"
                    "Tap **✅ Save Demo** when you've sent all files to complete setup."
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Save Demo", callback_data="admin_confirm_demo_media_done")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
                ])
            )

        elif data == "admin_confirm_demo_media_done":
            demo_list = context.user_data.pop("awaiting_demo_media_list", None)
            if not demo_list:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ No items added to demo sequence. Cancelled.")
                return

            # Archive existing demo items
            session.query(Content).filter(Content.content_type != "apk").update({"is_active": False})
            
            # Save new demo items
            for idx, item in enumerate(demo_list):
                new_demo = Content(
                    content_type=item["content_type"],
                    file_id=item["file_id"],
                    file_name="demo_file",
                    caption=item["caption"],
                    text_content=item["text_content"],
                    is_active=True,
                    order_index=idx + 1,
                )
                session.add(new_demo)
            session.commit()
            
            await query.edit_message_text(f"🌸 *Demo sequence successfully updated with {len(demo_list)} items!*")

        elif data == "admin_prompt_demo_msg":
            context.user_data["awaiting_demo_msg"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "✏️ *Please reply with the text to be shown AFTER the demo content delivery:*\n\n"
                    "💡 Use `{name}` in your text to dynamically replace it with the user's name (e.g. `✨ Enjoy the game, {name}!`)."
                ),
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_prompt_app_icon":
            context.user_data["awaiting_app_icon"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="🖼️ *Please send the Image or Sticker you want to use as the App Icon:*",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_prompt_edit_yes_opt":
            context.user_data["awaiting_yes_label"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="✏️ *Please reply with the new label text for the YES option button:*",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_prompt_edit_no_opt":
            context.user_data["awaiting_no_label"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="✏️ *Please reply with the new label text for the NO option button:*",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_prompt_edit_question":
            context.user_data["awaiting_onboarding_question"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="✏️ *Please reply with the new Onboarding Question text:*",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data in ("admin_toggle_demo", "admin_toggle_maintenance"):
            if data == "admin_toggle_demo":
                current = get_config("demo_enabled", "true").lower() == "true"
                set_config("demo_enabled", "false" if current else "true")
            else:
                current = get_config("bot_enabled", "true").lower() == "true"
                set_config("bot_enabled", "false" if current else "true")

            text, keyboard = get_admin_panel_details(user_id=user.id)
            await _safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

        elif data == "admin_how_to_use":
            guide_text = (
                "❓ *NexusBot Quick Help*\n\n"
                "• Send *any* file directly to this bot chat, and it will ask where to save it.\n"
                "• Send an `.apk` file directly to instantly set the new active download.\n"
                "• Tap *Get Report* to see detailed user sign-ups and referral statistics."
            )
            await context.bot.send_message(chat_id=chat_id, text=guide_text, parse_mode=ParseMode.MARKDOWN)

        elif data == "admin_guide":
            guide_text = (
                "📖 *Admin Command & Operations Guide*\n\n"
                "1. **Welcome Message**: Set the onboarding greeting message.\n"
                "2. **Set Demo**: Set the video/media that YES answers will trigger.\n"
                "3. **Broadcast**: Push the active APK directly into user chats with the push button."
            )
            await context.bot.send_message(chat_id=chat_id, text=guide_text, parse_mode=ParseMode.MARKDOWN)

        elif data == "admin_get_report":
            total_users = session.query(User).count()
            yes_users = session.query(User).filter_by(answer_yes=True).count()
            no_users = session.query(User).filter_by(answer_yes=False).count()
            downloads = session.query(Analytics).filter_by(event="apk_download").count()
            
            report = (
                "📊 *NexusBot Active Report*\n"
                "──────────────────────────\n"
                f"👤 Total Joined Users: *{total_users}*\n"
                f"✅ Said YES to question: *{yes_users}*\n"
                f"❌ Said NO to question: *{no_users}*\n"
                f"📥 Total APK Downloads: *{downloads}*\n"
                "──────────────────────────\n"
                "All stats updated in real-time."
            )
            await context.bot.send_message(chat_id=chat_id, text=report, parse_mode=ParseMode.MARKDOWN)

        elif data == "admin_broadcast_apk":
            active_apk = session.query(Content).filter_by(content_type="apk", is_active=True).first()
            if not active_apk:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ Cannot broadcast: No active APK file set!")
                return

            # Trigger background broadcast
            from bot.services.broadcast import execute_broadcast
            
            # Save broadcast job
            broadcast_job = Broadcast(
                message_type="apk",
                file_id=active_apk.file_id,
                caption=active_apk.changelog or "New APK Update is live! 🚀",
                has_apk_button=True,
                apk_button_text="⬇️ Download App",
                status="pending"
            )
            session.add(broadcast_job)
            session.commit()
            
            # Run asynchronously in background thread
            import threading
            def run_bg():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(execute_broadcast(broadcast_job.id, context.bot.token))
                except Exception as thread_err:
                    logger.error(f"Telegram thread broadcast error: {thread_err}")
                finally:
                    loop.close()

            threading.Thread(target=run_bg, daemon=True).start()
            await query.edit_message_text("📲 *APK Broadcast started in the background!* Users will receive it shortly.")

        elif data == "admin_prompt_broadcast_media":
            context.user_data["awaiting_broadcast_media_list"] = []
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "📢 *Multi-Media Broadcast Builder active!* 📢\n\n"
                    "Send me any files or messages you want to include in this broadcast (Texts, Voice Notes, Photos, Videos, Audio, Documents/APKs) one-by-one.\n\n"
                    "Tap **✅ Done (Confirm)** when you've sent all files to launch the broadcast."
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Done (Confirm)", callback_data="admin_confirm_bc_media_done")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
                ])
            )

        elif data == "admin_confirm_bc_media_done":
            media_list = context.user_data.get("awaiting_broadcast_media_list", [])
            if not media_list:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ No items added yet. Please send some media or text first.")
                return
                
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Attach APK Button", callback_data="admin_confirm_bc_yes_apk"),
                    InlineKeyboardButton("❌ No APK Button", callback_data="admin_confirm_bc_no_apk")
                ],
                [InlineKeyboardButton("Cancel", callback_data="admin_cancel")]
            ])
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 *Multi-Media sequence contains {len(media_list)} items.*\n\nDo you want to attach the APK download button below this broadcast?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )

        elif data in ("admin_confirm_bc_yes_apk", "admin_confirm_bc_no_apk"):
            has_apk = (data == "admin_confirm_bc_yes_apk")
            media_list = context.user_data.pop("awaiting_broadcast_media_list", None)
            
            import json
            if media_list:
                bc_type = "multimedia"
                bc_file_id = None
                bc_caption = None
                bc_text = json.dumps(media_list)
            else:
                # Fallback to single media item
                bc_type = context.user_data.pop("broadcast_type", "text")
                bc_file_id = context.user_data.pop("broadcast_file_id", None)
                bc_caption = context.user_data.pop("broadcast_caption", None)
                bc_text = context.user_data.pop("broadcast_text", None)

            # Build and commit broadcast database record
            new_bc = Broadcast(
                message_type=bc_type,
                file_id=bc_file_id,
                caption=bc_caption,
                content_text=bc_text,
                has_apk_button=has_apk,
                apk_button_text="⬇️ Download App",
                status="pending"
            )
            session.add(new_bc)
            session.commit()
            bc_id = new_bc.id

            # Trigger background sending thread
            from bot.services.broadcast import execute_broadcast
            import threading
            
            def run_custom_bg():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(execute_broadcast(bc_id, context.bot.token))
                except Exception as thread_err:
                    logger.error(f"Telegram thread broadcast error: {thread_err}")
                finally:
                    loop.close()

            threading.Thread(target=run_custom_bg, daemon=True).start()
            await query.edit_message_text(f"📲 *Broadcast #{bc_id} ({bc_type}) started in background!* Sending to users...")

        elif data.startswith("admin_remove_sub_admin_"):
            remove_id = int(data.split("_")[-1])
            await _remove_sub_admin_render(query, remove_id, chat_id)

        elif data == "admin_manage_sub_admins":
            if get_admin_role(user.id) != "super_admin":
                await context.bot.send_message(chat_id=chat_id, text="⛔ Only super admin can manage admins.")
                return
            sub_admin_data = fb_request("GET", "sub_admins") or {}
            msg_lines = ["👥 *Sub Admins:*\n"]
            keyboard_buttons = []
            if sub_admin_data and isinstance(sub_admin_data, dict):
                for tid, info in sub_admin_data.items():
                    if info and info.get("is_active"):
                        name = info.get("name", "Unknown")
                        username = info.get("username", "")
                        label = f"{name} (@{username})" if username else name
                        msg_lines.append(f"• {label}")
                        keyboard_buttons.append([
                            InlineKeyboardButton(f"❌ Remove {name}", callback_data=f"admin_remove_sub_admin_{tid}")
                        ])
            else:
                msg_lines.append("_No sub-admins appointed._")
            keyboard_buttons.append([InlineKeyboardButton("➕ Add Sub Admin", callback_data="admin_prompt_add_sub_admin")])
            keyboard_buttons.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back_to_panel")])
            await _safe_edit(query, "\n".join(msg_lines), parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard_buttons))

        elif data == "admin_prompt_add_sub_admin":
            if get_admin_role(user.id) != "super_admin":
                return
            context.user_data["awaiting_sub_admin_forward"] = True
            await _safe_edit(query,
                "📤 *Forward me a message from the user you want to appoint as Sub Admin.*\n\n"
                "Any message they sent to this bot will work.",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == "admin_back_to_panel":
            context.user_data.clear()
            text, keyboard = get_admin_panel_details(user_id=user.id)
            await _safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

        elif data == "admin_cancel":
            context.user_data.clear()
            await _safe_edit(query, "❌ Operations cancelled.")

    except Exception as e:
        session.rollback()
        logger.error(f"Callback admin error: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error: {e}")
    finally:
        session.close()


def get_admin_panel_details(user_id: int = 0):
    session = Session()
    try:
        total_users = session.query(User).count()

        active_apk = session.query(Content).filter_by(content_type="apk", is_active=True).first()
        app_status = "Set" if active_apk else "Not set"
        app_name = active_apk.file_name if active_apk else "None"

        active_demo = session.query(Content).filter(Content.content_type != "apk", Content.is_active == True).first()
        demo_status = "Set" if active_demo else "Not set"

        demo_on = get_config("demo_enabled", "true").lower() == "true"
        bot_active = get_config("bot_enabled", "true").lower() == "true"

        text = (
            "⚙️ *ADMIN CONTROL PANEL* ⚙️\n"
            "──────────────────────────\n"
            f"👥 Total Verified Users: *{total_users}*\n"
            f"📱 App Status: *{app_status}*\n"
            f"📛 App Name: *{app_name}*\n"
            f"🌸 Demo URL: *{demo_status}*\n"
            "──────────────────────────\n"
            "👇 _Niche diye buttons se manage karein:_"
        )

        from bot.utils.keyboards import admin_panel_keyboard
        role = get_admin_role(user_id) if user_id else "super_admin"
        keyboard = admin_panel_keyboard(demo_on, bot_active, role)
        return text, keyboard
    finally:
        session.close()
