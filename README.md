# 🤖 Instagram OSINT & Analytics Bot

A Telegram bot that performs deep-dive analysis of any public Instagram profile — engagement metrics, fake follower detection, cross-platform presence — with a built-in Freemium model.

---

## 📁 Files in This Repo

| File | Purpose |
|---|---|
| `bot.py` | The entire bot — one file, run this |
| `requirements.txt` | Python dependencies |
| `.env.example` | Config template — rename to `.env` and fill in |
| `Procfile` | For Koyeb / Heroku deployment |

---

## ⚡ Quick Start

```bash
# 1. Clone
git clone https://github.com/yourusername/instagram-osint-bot.git
cd instagram-osint-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up config
cp .env.example .env
# Open .env and fill in your values

# 4. Run
python bot.py
```

---

## 🔧 Configuration (`.env`)

| Variable | Description |
|---|---|
| `BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `API_ID` | From [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | From [my.telegram.org](https://my.telegram.org) |
| `ADMIN_ID` | Your Telegram numeric user ID |
| `ADMIN_USERNAME` | Your Telegram @username |
| `FORCE_JOIN_CHANNEL` | Channel users must join before using the bot |
| `MONGO_URI` | MongoDB connection string (e.g. from MongoDB Atlas) |
| `DB_NAME` | Database name (default: `osint_bot`) |
| `RAPIDAPI_KEY` | *(Optional)* RapidAPI key — fallback scraper if Instaloader fails |
| `RAPIDAPI_HOST` | RapidAPI host for Instagram endpoint |

---

## ✨ Features

- **Force Join** — user must join your channel before using the bot
- **1 Free Search** — first search is free, then upgrade required
- **Deep Analytics** — engagement rate, fake follower detection, like/comment ratios
- **Cross-Platform** — checks Twitter/X, TikTok, YouTube, Pinterest, Snapchat
- **Private Profile Handling** — shows basic info with a "Private" warning
- **Reverse Image Search** — button links profile pic to Google Lens
- **Admin Panel** — manage users and run broadcasts via commands

---

## 👤 Admin Commands

| Command | Description |
|---|---|
| `/addpremium [user_id]` | Grant Pro access |
| `/removepremium [user_id]` | Revoke Pro access |
| `/userinfo [user_id]` | View user details |
| `/stats` | Total users, Pro count, Free count |
| `/broadcast [message]` | Send message to all users |

---

## 💰 Freemium Logic

```
First search  → Free ✅
Second search → Blocked 🚫 → "Contact Admin to upgrade"
Admin runs /addpremium → User gets unlimited searches 💎
```

---

## 📊 What the Report Includes

- Full name, bio, category, verified status, link in bio
- Follower / following / post count
- Engagement rate with Healthy / Average / Suspicious verdict
- Like ratio fake-follower indicator
- Comment bot-activity detection
- Top 3 most liked posts (with links)
- Posting frequency label (Active / Ghost etc.)
- Cross-platform username presence on 5 platforms
- One-click Google Lens reverse image search button

---

## 🚀 Deployment

**VPS:**
```bash
screen -S bot
python bot.py
# Detach: Ctrl+A then D
```

**Koyeb:**
1. Push repo to GitHub
2. Connect to [Koyeb](https://www.koyeb.com)
3. Add all `.env` variables in the dashboard
4. Deploy — auto-restarts on crash

---

## ⚠️ Disclaimer

For educational and research purposes only. This bot only accesses publicly available Instagram data. Do not use it to harass or stalk anyone.

---

## 📄 License

MIT License
