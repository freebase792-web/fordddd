# ⚡ NexusBot — God-Level Telegram Bot

A fully-featured Telegram bot with a powerful hidden admin panel.
Users enjoy a gamified content experience. Admins have complete control.

## 🚀 Features

### User Side
- Welcome animation + streak system + XP levels
- Admin-set Yes/No question flow
- Exclusive content delivery (video, images, voice, text)
- One-tap APK download (always latest version)
- Referral system with unique invite links
- XP leaderboard and gamification

### Admin Panel (`/admin`)
- **Dashboard** — Live stats: users, conversions, APK downloads
- **Content Manager** — Add/edit/delete video, image, voice, text, APK
- **APK Manager** — Replace APK with one click (old one archived, silent update)
- **Broadcast** — Send to ALL users: 📝 text, 🎵 voice note, 🖼️ image, 🎬 video, 🎤 audio, 📱 APK
- **Questions** — Create/edit the Yes/No onboarding question
- **Users** — View, search, ban/unban all users
- **Settings** — All bot messages customizable from panel

## 🛠️ Setup

### 1. Clone & Configure

```bash
git clone https://github.com/yourusername/nexusbot.git
cd nexusbot
cp .env.example .env
# Fill in your values in .env
```

### 2. Environment Variables

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | From @BotFather on Telegram |
| `ADMIN_SECRET` | Your admin panel password |
| `ADMIN_USERNAME` | Your admin panel username |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `WEBHOOK_URL` | Your Render app URL (e.g. `https://nexusbot.onrender.com`) |
| `SECRET_KEY` | Random secret for Flask sessions |

### 3. Local Development

```bash
pip install -r requirements.txt
python wsgi.py
```

## 🚀 Deploy to Render

### Option A: One-Click (render.yaml)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo
4. Render auto-creates: Web Service + Worker + Redis + PostgreSQL
5. Set your environment variables in Render dashboard
6. Done! 🎉

### Option B: Manual

1. Create a **Web Service** on Render
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn wsgi:app --workers 2 --threads 4 --bind 0.0.0.0:$PORT`
2. Create a **Worker** on Render
   - Start: `python -m bot.worker`
3. Add **PostgreSQL** database
4. Add **Redis** instance
5. Set all env vars

### GitHub Actions Auto-Deploy

Add these secrets to your GitHub repo:
- `RENDER_API_KEY` — from Render Account Settings
- `RENDER_SERVICE_ID` — your Render service ID

Every push to `main` auto-deploys to Render.

## 📱 APK Management

**Uploading a new APK:**
1. Send the APK file to your bot in Telegram
2. Forward that message to @userinfobot → copy the `file_id`
3. Go to Admin Panel → APK Manager → paste file_id + set version
4. Click "Replace APK" — old one is archived silently
5. **To notify users:** Go to Broadcast → select type → optionally add APK button → Send

> ⚠️ Users are **NEVER** auto-notified of new APKs. Only when you broadcast.

## 📢 Broadcast Types

| Type | Usage |
|------|-------|
| 📝 Text | Plain markdown message |
| 🎵 Voice Note | Native Telegram voice message |
| 🖼️ Image | Photo with optional caption |
| 🎬 Video | Streamable video with caption |
| 🎤 Audio | Music/podcast audio file |
| 📱 APK/File | Send document + optional APK button |

## 📊 Admin Panel URL

```
https://your-app.onrender.com/admin
```

> Admin panel is completely invisible to Telegram users.

## 🏗️ Architecture

```
nexusbot/
├── bot/
│   ├── handlers/     ← Telegram update handlers
│   ├── models/       ← SQLAlchemy DB models
│   ├── services/     ← Broadcast engine
│   └── utils/        ← Keyboards, helpers
├── admin/
│   ├── app.py        ← Flask admin app
│   └── templates/    ← Admin UI
├── wsgi.py           ← Entry point
├── render.yaml       ← Render blueprint
└── Procfile          ← Process definitions
```

## License

MIT — build something incredible.
