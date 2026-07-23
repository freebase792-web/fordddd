"""
WSGI entry point — combines Flask admin app with bot webhook.
This is what Gunicorn runs: gunicorn wsgi:app
"""
import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Initialize database on startup
from bot.models.database import init_db
try:
    init_db()
except Exception as e:
    logging.warning(f"DB init warning: {e}")

# Import the Flask app (which includes all routes + webhook endpoint)
from admin.app import app

# ── Dual Execution Mode (Polling for Local, Webhook for Render) ──────
def start_bot_engine():
    import urllib.request
    import json
    import threading
    
    # Check if WEBHOOK_URL is local or empty
    is_local = (
        not WEBHOOK_URL or 
        "localhost" in WEBHOOK_URL or 
        "127.0.0.1" in WEBHOOK_URL or
        "your-bot-name" in WEBHOOK_URL
    )
    
    if is_local:
        logging.info("💻 Local environment detected. Starting bot in POLLING MODE...")
        
        # Helper to run updater.start_polling() in a background event loop
        def run_polling_thread():
            from bot.main import init_application, get_ptb_app
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            ptb_app = get_ptb_app()
            
            # Delete any existing webhook on Telegram before starting polling
            try:
                loop.run_until_complete(ptb_app.bot.delete_webhook(drop_pending_updates=True))
                logging.info("🧹 Cleared old webhook from Telegram.")
            except Exception as e:
                logging.warning(f"Failed to clear webhook: {e}")

            loop.run_until_complete(init_application())
            loop.run_until_complete(ptb_app.start())
            loop.run_until_complete(ptb_app.updater.start_polling())
            logging.info("🤖 Bot is polling for updates successfully!")
            loop.run_forever()

        t = threading.Thread(target=run_polling_thread, daemon=True)
        t.start()
        
    else:
        # Production mode (Render) -> register webhook
        webhook_path = f"{WEBHOOK_URL.rstrip('/')}/webhook/{BOT_TOKEN}"
        api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        logging.info(f"🚀 Production environment detected. Registering Webhook: {webhook_path}")
        
        try:
            data = json.dumps({
                "url": webhook_path,
                "drop_pending_updates": True,
                "allowed_updates": ["message", "callback_query"]
            }).encode("utf-8")
            
            req = urllib.request.Request(
                api_url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                if res_data.get("ok"):
                    logging.info(f"✅ Webhook registered successfully: {webhook_path}")
                else:
                    logging.warning(f"❌ Telegram setWebhook failed: {res_data.get('description')}")
        except Exception as err:
            logging.warning(f"❌ Failed to connect to Telegram setWebhook API: {err}")

start_bot_engine()

# ── Initialize shared bot Application on background event loop ─────
from admin.app import _start_bot_event_loop, _run_async
from bot.main import init_application
_start_bot_event_loop()
try:
    _run_async(init_application())
except Exception as e:
    logging.warning(f"Application init warning: {e}")

# ── Keep Alive Self-Pinger (Bypasses Render Free Tier Sleep) ────────
def run_keep_alive():
    import time
    import urllib.request
    
    # Wait for the server to spin up fully
    time.sleep(10)
    
    ping_url = f"{WEBHOOK_URL.rstrip('/')}/health"
    root_url = f"{WEBHOOK_URL.rstrip('/')}/"
    logging.info(f"🟢 Keep-alive service active. Targets: {ping_url} and {root_url}")
    
    while True:
        try:
            # 1. Ping /health
            req = urllib.request.Request(
                ping_url,
                headers={"User-Agent": "NexusBot-KeepAlive-Daemon"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                pass

            # 2. Ping / (root) to simulate a real user hitting the landing page
            root_req = urllib.request.Request(
                root_url,
                headers={"User-Agent": "NexusBot-KeepAlive-Daemon"}
            )
            with urllib.request.urlopen(root_req, timeout=15) as response:
                if response.getcode() in (200, 302):
                    logging.info("💓 Keep-alive self-ping sequence successful.")
                else:
                    logging.warning(f"⚠️ Keep-alive sequence returned status: {response.getcode()}")
        except Exception as ping_err:
            logging.warning(f"❌ Keep-alive self-ping sequence failed: {ping_err}")
        
        # Sleep for 3 minutes (180 seconds) to aggressively prevent sleeping
        time.sleep(180)

if WEBHOOK_URL:
    import threading
    keep_alive_thread = threading.Thread(target=run_keep_alive, daemon=True)
    keep_alive_thread.start()
    logging.info("🚀 Keep-alive background daemon thread started.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
