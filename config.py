import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")

# ── Admin & Force-Join ────────────────────────────────────
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@AdminUsername")
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL", "@YourChannel")

# ── MongoDB ───────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "osint_bot")

# ── RapidAPI (Instagram) ──────────────────────────────────
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "instagram-data1.p.rapidapi.com")

# ── Bot Rules ─────────────────────────────────────────────
FREE_SEARCH_LIMIT = 1  # How many free searches a user gets
