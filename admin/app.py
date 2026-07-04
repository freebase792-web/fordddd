"""
NexusBot Admin Panel — Flask Application
Completely hidden from users. Secured by admin secret token.
Features: Dashboard, Content, Questions, Broadcast, Users, APK Manager, Bot Config
"""
import os
import asyncio
import logging
import json
import threading

from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, g
)


from bot.models.database import (
    Session as DBSession, User, Content, Question, Broadcast,
    Analytics, BotConfig, get_config, set_config, init_db
)

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "nexusbot-dev-secret")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB max upload

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin123")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")





# ─────────────────────────────────────────
# Auth
# ─────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_SECRET:
            session["admin_logged_in"] = True
            flash("✅ Welcome back, Admin!", "success")
            return redirect(url_for("dashboard"))
        flash("❌ Invalid credentials", "danger")
    return render_template("admin/login.html")


@app.route("/admin/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────

@app.route("/admin")
@app.route("/admin/dashboard")
@login_required
def dashboard():
    db = DBSession()
    try:
        total_users = db.query(User).count()
        banned_users = db.query(User).filter_by(is_banned=True).count()
        yes_users = db.query(User).filter_by(answer_yes=True).count()
        no_users = db.query(User).filter_by(answer_yes=False).count()

        apk_downloads = db.query(Analytics).filter_by(event="apk_download").count()
        active_content = db.query(Content).filter_by(is_active=True).count()

        recent_broadcasts = (
            db.query(Broadcast)
            .order_by(Broadcast.created_at.desc())
            .limit(5)
            .all()
        )

        # Daily joins (last 7 days)
        from sqlalchemy import func, cast, Date
        daily_stats = (
            db.query(
                cast(User.joined_at, Date).label("day"),
                func.count(User.id).label("count")
            )
            .group_by(cast(User.joined_at, Date))
            .order_by(cast(User.joined_at, Date).desc())
            .limit(7)
            .all()
        )

        bot_enabled = get_config("bot_enabled", "true") == "true"
        active_apk = db.query(Content).filter_by(is_active=True, content_type="apk").order_by(Content.id.desc()).first()

        return render_template("admin/dashboard.html",
            total_users=total_users,
            banned_users=banned_users,
            yes_users=yes_users,
            no_users=no_users,
            apk_downloads=apk_downloads,
            active_content=active_content,
            recent_broadcasts=recent_broadcasts,
            daily_stats=list(reversed(daily_stats)),
            bot_enabled=bot_enabled,
            active_apk=active_apk,
        )
    finally:
        db.close()


# ─────────────────────────────────────────
# Bot Toggle
# ─────────────────────────────────────────

@app.route("/admin/bot/toggle", methods=["POST"])
@login_required
def toggle_bot():
    current = get_config("bot_enabled", "true")
    new_val = "false" if current == "true" else "true"
    set_config("bot_enabled", new_val)
    status = "enabled ✅" if new_val == "true" else "disabled 🔴"
    flash(f"Bot is now {status}", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/webhook/register", methods=["POST"])
@login_required
def register_webhook():
    """Re-register the bot webhook."""
    try:
        import requests as req
        webhook_path = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
        resp = req.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": webhook_path, "drop_pending_updates": True},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            flash(f"✅ Webhook registered: {webhook_path}", "success")
        else:
            flash(f"❌ Webhook error: {data.get('description')}", "danger")
    except Exception as e:
        flash(f"❌ Failed: {e}", "danger")
    return redirect(url_for("dashboard"))


# ─────────────────────────────────────────
# Content Manager
# ─────────────────────────────────────────

@app.route("/admin/content")
@login_required
def content_list():
    db = DBSession()
    try:
        contents = db.query(Content).order_by(Content.order_index.asc(), Content.id.asc()).all()
        return render_template("admin/content.html", contents=contents)
    finally:
        db.close()


@app.route("/admin/content/add", methods=["GET", "POST"])
@login_required
def content_add():
    if request.method == "POST":
        db = DBSession()
        try:
            content_type = request.form.get("content_type")
            file_id = request.form.get("file_id", "").strip()
            file_name = request.form.get("file_name", "").strip()
            caption = request.form.get("caption", "").strip()
            text_content = request.form.get("text_content", "").strip()
            version = request.form.get("version", "").strip()
            changelog = request.form.get("changelog", "").strip()
            order_index = int(request.form.get("order_index", 0))

            # If adding APK, archive old ones
            if content_type == "apk":
                db.query(Content).filter_by(content_type="apk", is_active=True).update({"is_active": False})

            item = Content(
                content_type=content_type,
                file_id=file_id or None,
                file_name=file_name or None,
                caption=caption or None,
                text_content=text_content or None,
                version=version or None,
                changelog=changelog or None,
                order_index=order_index,
                is_active=True,
            )
            db.add(item)
            db.commit()
            flash(f"✅ Content added successfully!", "success")
            return redirect(url_for("content_list"))
        except Exception as e:
            db.rollback()
            flash(f"❌ Error: {e}", "danger")
        finally:
            db.close()
    return render_template("admin/content_form.html", content=None, action="Add")


@app.route("/admin/content/edit/<int:cid>", methods=["GET", "POST"])
@login_required
def content_edit(cid):
    db = DBSession()
    try:
        item = db.get(Content, cid)
        if not item:
            flash("Content not found", "danger")
            return redirect(url_for("content_list"))

        if request.method == "POST":
            old_type = item.content_type
            new_type = request.form.get("content_type")
            item.content_type = new_type
            item.file_id = request.form.get("file_id", "").strip() or None
            item.file_name = request.form.get("file_name", "").strip() or None
            item.caption = request.form.get("caption", "").strip() or None
            item.text_content = request.form.get("text_content", "").strip() or None
            item.version = request.form.get("version", "").strip() or None
            item.changelog = request.form.get("changelog", "").strip() or None
            item.order_index = int(request.form.get("order_index", 0))

            # Archive other APKs if replacing with new APK
            if new_type == "apk" and old_type != "apk":
                db.query(Content).filter(
                    Content.content_type == "apk",
                    Content.is_active == True,
                    Content.id != cid
                ).update({"is_active": False})

            db.commit()
            flash("✅ Content updated!", "success")
            return redirect(url_for("content_list"))

        return render_template("admin/content_form.html", content=item, action="Edit")
    finally:
        db.close()


@app.route("/admin/content/toggle/<int:cid>", methods=["POST"])
@login_required
def content_toggle(cid):
    db = DBSession()
    try:
        item = db.get(Content, cid)
        if item:
            item.is_active = not item.is_active
            db.commit()
            status = "enabled" if item.is_active else "disabled"
            flash(f"Content {status}.", "success")
    finally:
        db.close()
    return redirect(url_for("content_list"))


@app.route("/admin/content/delete/<int:cid>", methods=["POST"])
@login_required
def content_delete(cid):
    db = DBSession()
    try:
        item = db.get(Content, cid)
        if item:
            db.delete(item)
            db.commit()
            flash("🗑️ Content deleted.", "success")
    finally:
        db.close()
    return redirect(url_for("content_list"))


# ─────────────────────────────────────────
# APK Manager (dedicated)
# ─────────────────────────────────────────

@app.route("/admin/apk")
@login_required
def apk_manager():
    db = DBSession()
    try:
        all_apks = (
            db.query(Content)
            .filter_by(content_type="apk")
            .order_by(Content.id.desc())
            .all()
        )
        active_apk = next((a for a in all_apks if a.is_active), None)
        archived_apks = [a for a in all_apks if not a.is_active]
        return render_template("admin/apk.html",
            active_apk=active_apk,
            archived_apks=archived_apks
        )
    finally:
        db.close()


@app.route("/admin/apk/replace", methods=["POST"])
@login_required
def apk_replace():
    """Replace active APK — archive old, activate new."""
    db = DBSession()
    try:
        file_id = request.form.get("file_id", "").strip()
        file_name = request.form.get("file_name", "App.apk").strip()
        version = request.form.get("version", "1.0").strip()
        changelog = request.form.get("changelog", "").strip()

        if not file_id:
            flash("❌ File ID is required (forward the APK to @userinfobot or check below)", "danger")
            return redirect(url_for("apk_manager"))

        # Archive all existing active APKs
        db.query(Content).filter_by(content_type="apk", is_active=True).update({"is_active": False})

        # Create new active APK
        new_apk = Content(
            content_type="apk",
            file_id=file_id,
            file_name=file_name,
            version=version,
            changelog=changelog,
            is_active=True,
        )
        db.add(new_apk)
        db.commit()
        flash(f"✅ APK v{version} is now active! Old APKs archived.", "success")
    except Exception as e:
        db.rollback()
        flash(f"❌ Error: {e}", "danger")
    finally:
        db.close()
    return redirect(url_for("apk_manager"))


# ─────────────────────────────────────────
# Questions Manager
# ─────────────────────────────────────────

@app.route("/admin/questions")
@login_required
def questions_list():
    db = DBSession()
    try:
        questions = db.query(Question).order_by(Question.order_index.asc()).all()
        return render_template("admin/questions.html", questions=questions)
    finally:
        db.close()


@app.route("/admin/questions/add", methods=["GET", "POST"])
@login_required
def question_add():
    if request.method == "POST":
        db = DBSession()
        try:
            q = Question(
                question_text=request.form.get("question_text", "").strip(),
                yes_label=request.form.get("yes_label", "✅ Yes, I'm in!").strip(),
                no_label=request.form.get("no_label", "❌ Not now").strip(),
                yes_response=request.form.get("yes_response", "").strip() or None,
                no_response=request.form.get("no_response", "").strip() or None,
                order_index=int(request.form.get("order_index", 0)),
                is_active=request.form.get("is_active") == "on",
            )
            db.add(q)
            db.commit()
            flash("✅ Question added!", "success")
            return redirect(url_for("questions_list"))
        except Exception as e:
            db.rollback()
            flash(f"❌ Error: {e}", "danger")
        finally:
            db.close()
    return render_template("admin/question_form.html", question=None, action="Add")


@app.route("/admin/questions/edit/<int:qid>", methods=["GET", "POST"])
@login_required
def question_edit(qid):
    db = DBSession()
    try:
        q = db.get(Question, qid)
        if not q:
            flash("Question not found", "danger")
            return redirect(url_for("questions_list"))
        if request.method == "POST":
            q.question_text = request.form.get("question_text", "").strip()
            q.yes_label = request.form.get("yes_label", "✅ Yes, I'm in!").strip()
            q.no_label = request.form.get("no_label", "❌ Not now").strip()
            q.yes_response = request.form.get("yes_response", "").strip() or None
            q.no_response = request.form.get("no_response", "").strip() or None
            q.order_index = int(request.form.get("order_index", 0))
            q.is_active = request.form.get("is_active") == "on"
            db.commit()
            flash("✅ Question updated!", "success")
            return redirect(url_for("questions_list"))
        return render_template("admin/question_form.html", question=q, action="Edit")
    finally:
        db.close()


@app.route("/admin/questions/delete/<int:qid>", methods=["POST"])
@login_required
def question_delete(qid):
    db = DBSession()
    try:
        q = db.get(Question, qid)
        if q:
            db.delete(q)
            db.commit()
            flash("🗑️ Question deleted.", "success")
    finally:
        db.close()
    return redirect(url_for("questions_list"))


# ─────────────────────────────────────────
# Broadcast Manager
# ─────────────────────────────────────────

@app.route("/admin/broadcast")
@login_required
def broadcast_list():
    db = DBSession()
    try:
        broadcasts = db.query(Broadcast).order_by(Broadcast.created_at.desc()).limit(50).all()
        user_count = db.query(User).filter_by(is_banned=False).count()
        active_apk = db.query(Content).filter_by(is_active=True, content_type="apk").order_by(Content.id.desc()).first()
        return render_template("admin/broadcast.html",
            broadcasts=broadcasts,
            user_count=user_count,
            active_apk=active_apk,
        )
    finally:
        db.close()


@app.route("/admin/broadcast/send", methods=["POST"])
@login_required
def broadcast_send():
    db = DBSession()
    try:
        msg_type = request.form.get("message_type", "text")
        content_text = request.form.get("content_text", "").strip() or None
        file_id = request.form.get("file_id", "").strip() or None
        caption = request.form.get("caption", "").strip() or None
        has_apk_button = request.form.get("has_apk_button") == "on"
        apk_button_text = request.form.get("apk_button_text", "⬇️ Download App").strip()

        if msg_type == "text" and not content_text:
            flash("❌ Text content is required for text broadcasts.", "danger")
            return redirect(url_for("broadcast_list"))
        if msg_type != "text" and not file_id:
            flash("❌ File ID is required for media broadcasts.", "danger")
            return redirect(url_for("broadcast_list"))

        user_count = db.query(User).filter_by(is_banned=False).count()

        broadcast = Broadcast(
            message_type=msg_type,
            content_text=content_text,
            file_id=file_id,
            caption=caption,
            has_apk_button=has_apk_button,
            apk_button_text=apk_button_text,
            total_users=user_count,
            status="pending",
        )
        db.add(broadcast)
        db.commit()
        broadcast_id = broadcast.id

        # Run broadcast in a background thread to avoid blocking the Flask request

        def run_broadcast_thread(bid, token):
            from bot.services.broadcast import execute_broadcast
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(execute_broadcast(bid, token))
            except Exception as thread_err:
                logger.error(f"Thread broadcast error: {thread_err}")
            finally:
                loop.close()

        thread = threading.Thread(
            target=run_broadcast_thread,
            args=(broadcast_id, BOT_TOKEN),
            daemon=True
        )
        thread.start()

        flash(f"🚀 Broadcast #{broadcast_id} triggered in background! Sending to {user_count} users...", "success")

    except Exception as e:
        db.rollback()
        flash(f"❌ Error: {e}", "danger")
    finally:
        db.close()
    return redirect(url_for("broadcast_list"))


@app.route("/admin/broadcast/status/<int:bid>")
@login_required
def broadcast_status(bid):
    """API endpoint for live broadcast progress."""
    db = DBSession()
    try:
        b = db.get(Broadcast, bid)
        if not b:
            return jsonify({"error": "Not found"}), 404
        progress = round((b.sent_count / b.total_users * 100) if b.total_users else 0, 1)
        return jsonify({
            "id": b.id,
            "status": b.status,
            "total": b.total_users,
            "sent": b.sent_count,
            "failed": b.failed_count,
            "progress": progress,
        })
    finally:
        db.close()


# ─────────────────────────────────────────
# Users Manager
# ─────────────────────────────────────────

@app.route("/admin/users")
@login_required
def users_list():
    db = DBSession()
    try:
        page = int(request.args.get("page", 1))
        per_page = 50
        search = request.args.get("search", "").strip()

        query = db.query(User)
        if search:
            query = query.filter(
                (User.username.ilike(f"%{search}%")) |
                (User.first_name.ilike(f"%{search}%"))
            )

        total = query.count()
        users = (
            query.order_by(User.joined_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        pages = (total + per_page - 1) // per_page

        return render_template("admin/users.html",
            users=users, page=page, pages=pages, total=total, search=search
        )
    finally:
        db.close()


@app.route("/admin/users/ban/<int:uid>", methods=["POST"])
@login_required
def user_ban(uid):
    db = DBSession()
    try:
        user = db.get(User, uid)
        if user:
            user.is_banned = not user.is_banned
            db.commit()
            action = "banned" if user.is_banned else "unbanned"
            flash(f"User {uid} {action}.", "success")
    finally:
        db.close()
    return redirect(url_for("users_list"))


# ─────────────────────────────────────────
# Bot Config / Settings
# ─────────────────────────────────────────

@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
def settings():
    config_keys = [
        "welcome_text", "welcome_gif_id", "yes_intro_text",
        "no_response_text", "maintenance_message", "apk_button_text",
    ]
    if request.method == "POST":
        try:
            for key in config_keys:
                value = request.form.get(key, "").strip()
                set_config(key, value)
            flash("✅ Settings saved!", "success")
        except Exception as e:
            flash(f"❌ Error: {e}", "danger")
        return redirect(url_for("settings"))

    configs = {key: get_config(key, "") for key in config_keys}
    return render_template("admin/settings.html", configs=configs)


# Cache bot user details and user_data globally to bypass get_me() requests and persist state across requests
_cached_bot_user = None
_global_user_data = {}

@app.route(f"/webhook/<token>", methods=["POST"])
def telegram_webhook(token):
    """Receive updates from Telegram via webhook."""
    if token != BOT_TOKEN:
        return "Forbidden", 403

    from telegram import Update, User as TGUser
    from telegram.ext import Application
    from bot.main import register_handlers

    data = request.get_json(force=True)

    # Process the update in a background thread to return 200 OK instantly to Telegram.
    # This prevents Gunicorn from blocking on slow API calls and eliminates all lag!
    def run_update_in_background(update_data):
        async def _handle_update_async():
            global _cached_bot_user, _global_user_data
            
            # Create a fresh Application instance for this thread's loop
            ptb_app = (
                Application.builder()
                .token(BOT_TOKEN)
                .build()
            )
            register_handlers(ptb_app)

            # Restore the user_data state mapping using the raw internal dict
            ptb_app._user_data.update(_global_user_data)

            # Inject the cached bot user to bypass the get_me() HTTP request
            if _cached_bot_user:
                ptb_app.bot._bot_user = _cached_bot_user

            try:
                await ptb_app.initialize()
                
                # Set Menu Button commands programmatically with user/admin scope separation
                from telegram import BotCommandScopeDefault, BotCommandScopeChat
                try:
                    # 1. Regular users only see the Start command
                    await ptb_app.bot.set_my_commands(
                        [("start", "🚀 Start Bot")],
                        scope=BotCommandScopeDefault()
                    )
                    # 2. Only the Admin ID sees the Admin Panel command
                    from bot.handlers.admin_upload import ADMIN_TELEGRAM_ID
                    if ADMIN_TELEGRAM_ID:
                        await ptb_app.bot.set_my_commands(
                            [
                                ("start", "🚀 Start Bot"),
                                ("admin", "⚡ Admin Control Panel")
                            ],
                            scope=BotCommandScopeChat(chat_id=ADMIN_TELEGRAM_ID)
                        )
                except Exception as cmd_err:
                    logger.error(f"Failed to set scoped bot commands: {cmd_err}")

                # Cache the bot user for future requests
                if not _cached_bot_user and ptb_app.bot._bot_user:
                    _cached_bot_user = ptb_app.bot._bot_user

                update = Update.de_json(update_data, ptb_app.bot)
                await ptb_app.process_update(update)
            except Exception as thread_err:
                logger.error(f"Error processing update in background: {thread_err}", exc_info=True)
            finally:
                # Save the updated user_data mapping back to the global process store
                _global_user_data.clear()
                _global_user_data.update(ptb_app._user_data)
                
                # Cleanly shutdown the HTTP client connections for this thread's loop
                await ptb_app.shutdown()

        try:
            asyncio.run(_handle_update_async())
        except Exception as loop_err:
            logger.error(f"Failed to run event loop in background: {loop_err}", exc_info=True)

    # Start the daemon thread and return instantly
    threading.Thread(target=run_update_in_background, args=(data,), daemon=True).start()
    return "ok", 200


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "NexusBot"}), 200


@app.route("/")
def index():
    return redirect(url_for("login"))
