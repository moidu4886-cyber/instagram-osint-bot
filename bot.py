"""
Instagram OSINT & Analytics Bot
Single-file version — drop this + .env into any folder and run.
"""

import asyncio
import re
import os
import requests
import instaloader
from datetime import datetime, timezone
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, ChannelInvalid
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN          = os.getenv("BOT_TOKEN")
API_ID             = int(os.getenv("API_ID", 0))
API_HASH           = os.getenv("API_HASH")
ADMIN_ID           = int(os.getenv("ADMIN_ID", 0))
ADMIN_USERNAME     = os.getenv("ADMIN_USERNAME", "@AdminUsername")
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL", "@YourChannel")
MONGO_URI          = os.getenv("MONGO_URI")
DB_NAME            = os.getenv("DB_NAME", "osint_bot")
RAPIDAPI_KEY       = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST      = os.getenv("RAPIDAPI_HOST", "instagram-data1.p.rapidapi.com")
FREE_SEARCH_LIMIT  = 1

# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════

_mongo_client = None
_db = None

async def connect_db():
    global _mongo_client, _db
    _mongo_client = AsyncIOMotorClient(MONGO_URI)
    _db = _mongo_client[DB_NAME]
    print("[DB] Connected to MongoDB")

async def close_db():
    if _mongo_client:
        _mongo_client.close()

def users_col():
    return _db["users"]

def searches_col():
    return _db["searches"]

async def get_or_create_user(user_id, username=None, first_name=None):
    col = users_col()
    user = await col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "joined_at": datetime.now(timezone.utc),
            "search_count": 0,
            "is_premium": False,
            "premium_granted_by": None,
            "premium_granted_at": None,
            "last_search_at": None,
        }
        await col.insert_one(user)
    return user

async def get_user(user_id):
    return await users_col().find_one({"user_id": user_id})

async def get_all_users():
    return await users_col().find({}).to_list(length=None)

async def get_stats():
    col = users_col()
    total   = await col.count_documents({})
    premium = await col.count_documents({"is_premium": True})
    return {"total": total, "premium": premium, "free": total - premium}

async def increment_search(user_id):
    await users_col().update_one(
        {"user_id": user_id},
        {"$inc": {"search_count": 1}, "$set": {"last_search_at": datetime.now(timezone.utc)}}
    )

async def set_premium(user_id, granted_by):
    r = await users_col().update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": True, "premium_granted_by": granted_by,
                  "premium_granted_at": datetime.now(timezone.utc)}}
    )
    return r.matched_count > 0

async def revoke_premium(user_id):
    r = await users_col().update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": False, "premium_granted_by": None, "premium_granted_at": None}}
    )
    return r.matched_count > 0

async def log_search(user_id, ig_username, profile_type, result_summary):
    await searches_col().insert_one({
        "user_id": user_id,
        "instagram_username": ig_username,
        "searched_at": datetime.now(timezone.utc),
        "profile_type": profile_type,
        "result_summary": result_summary,
    })

# ══════════════════════════════════════════════════════════════════════════════
# INSTAGRAM SCRAPER
# ══════════════════════════════════════════════════════════════════════════════

def _scrape_instaloader(username):
    L = instaloader.Instaloader()
    try:
        profile = instaloader.Profile.from_username(L.context, username)
        posts_data = []
        for i, post in enumerate(profile.get_posts()):
            if i >= 10:
                break
            posts_data.append({
                "shortcode": post.shortcode,
                "likes": post.likes,
                "comments": post.comments,
                "url": f"https://www.instagram.com/p/{post.shortcode}/",
                "caption": (post.caption or "")[:100],
            })
        avg_likes    = round(sum(p["likes"]    for p in posts_data) / len(posts_data), 1) if posts_data else 0
        avg_comments = round(sum(p["comments"] for p in posts_data) / len(posts_data), 1) if posts_data else 0
        return {
            "username": profile.username,
            "full_name": profile.full_name,
            "bio": profile.biography,
            "followers": profile.followers,
            "following": profile.followees,
            "post_count": profile.mediacount,
            "is_private": profile.is_private,
            "is_verified": profile.is_verified,
            "profile_pic_url": profile.profile_pic_url,
            "category": getattr(profile, "business_category_name", "N/A"),
            "external_url": profile.external_url,
            "posts": posts_data,
            "avg_likes": avg_likes,
            "avg_comments": avg_comments,
        }
    except instaloader.exceptions.ProfileNotExistsException:
        return None
    except Exception as e:
        print(f"[Instaloader] {e}")
        return None

def _scrape_rapidapi(username):
    if not RAPIDAPI_KEY:
        return None
    try:
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST}
        resp = requests.get(f"https://{RAPIDAPI_HOST}/v1/info",
                            headers=headers, params={"username": username}, timeout=10)
        if resp.status_code != 200:
            return None
        user = resp.json().get("data", {}).get("user", {})
        if not user:
            return None
        edges = user.get("edge_owner_to_timeline_media", {}).get("edges", [])[:10]
        posts_data = []
        for e in edges:
            n = e.get("node", {})
            sc = n.get("shortcode", "")
            posts_data.append({
                "shortcode": sc,
                "likes": n.get("edge_liked_by", {}).get("count", 0),
                "comments": n.get("edge_media_to_comment", {}).get("count", 0),
                "url": f"https://www.instagram.com/p/{sc}/",
                "caption": "",
            })
        avg_likes    = round(sum(p["likes"]    for p in posts_data) / len(posts_data), 1) if posts_data else 0
        avg_comments = round(sum(p["comments"] for p in posts_data) / len(posts_data), 1) if posts_data else 0
        return {
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "bio": user.get("biography"),
            "followers": user.get("edge_followed_by", {}).get("count", 0),
            "following": user.get("edge_follow", {}).get("count", 0),
            "post_count": user.get("edge_owner_to_timeline_media", {}).get("count", 0),
            "is_private": user.get("is_private", False),
            "is_verified": user.get("is_verified", False),
            "profile_pic_url": user.get("profile_pic_url_hd", ""),
            "category": user.get("category_name", "N/A"),
            "external_url": user.get("external_url", ""),
            "posts": posts_data,
            "avg_likes": avg_likes,
            "avg_comments": avg_comments,
        }
    except Exception as e:
        print(f"[RapidAPI] {e}")
        return None

def fetch_instagram_profile(username):
    username = username.lstrip("@").strip()
    return _scrape_instaloader(username) or _scrape_rapidapi(username)

# ══════════════════════════════════════════════════════════════════════════════
# FAKE DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

BOT_PHRASES = ["great pic","nice photo","love this","amazing","follow me","check my page",
               "dm me","follow back","f4f","nice","cool","wow","🔥","❤️","👏","💯","🙌"]

def engagement_rate(followers, avg_likes, avg_comments):
    if not followers:
        return 0.0
    return round((avg_likes + avg_comments) / followers * 100, 2)

def engagement_label(rate):
    if rate >= 3:   return "✅ Healthy"
    if rate >= 1:   return "⚠️ Average"
    return              "🚨 Suspicious"

def like_ratio_verdict(followers, avg_likes):
    if not followers:
        return "N/A"
    r = avg_likes / followers * 100
    if r >= 1:    return f"✅ Normal ({r:.2f}%)"
    if r >= 0.2:  return f"⚠️ Low ({r:.2f}%)"
    return              f"🚨 Very Low — Fake Risk ({r:.2f}%)"

def comment_verdict(posts):
    captions = [p.get("caption","") for p in posts if p.get("caption")]
    if not captions:
        return "No captions to analyse"
    bots = sum(1 for c in captions if any(p in c.lower() for p in BOT_PHRASES))
    pct = round(bots / len(captions) * 100, 1)
    if pct >= 60:  return f"🚨 High bot activity ({pct}%)"
    if pct >= 30:  return f"⚠️ Moderate bot activity ({pct}%)"
    return              f"✅ Looks organic ({pct}%)"

def run_fake_analysis(profile):
    f = profile.get("followers", 0)
    l = profile.get("avg_likes", 0)
    c = profile.get("avg_comments", 0)
    rate = engagement_rate(f, l, c)
    return {
        "rate": rate,
        "label": engagement_label(rate),
        "like_ratio": like_ratio_verdict(f, l),
        "comment": comment_verdict(profile.get("posts", [])),
    }

# ══════════════════════════════════════════════════════════════════════════════
# CROSS-PLATFORM CHECK
# ══════════════════════════════════════════════════════════════════════════════

PLATFORMS = {
    "Twitter/X":  "https://twitter.com/{u}",
    "TikTok":     "https://www.tiktok.com/@{u}",
    "YouTube":    "https://www.youtube.com/@{u}",
    "Pinterest":  "https://www.pinterest.com/{u}/",
    "Snapchat":   "https://www.snapchat.com/add/{u}",
}
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def check_all_platforms(username):
    results = []
    for name, tmpl in PLATFORMS.items():
        url = tmpl.format(u=username)
        try:
            r = requests.get(url, headers=_HEADERS, timeout=6, allow_redirects=True)
            status = "🟢 Found" if r.status_code == 200 else ("⚪ Not Found" if r.status_code == 404 else f"🟡 {r.status_code}")
        except Exception:
            status = "🔴 Error"
        results.append({"name": name, "url": url, "status": status})
    return results

# ══════════════════════════════════════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════════════════════════════════════

def kb_join():
    ch = FORCE_JOIN_CHANNEL.lstrip("@")
    return InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{ch}")]])

def kb_admin():
    admin = ADMIN_USERNAME.lstrip("@")
    return InlineKeyboardMarkup([[InlineKeyboardButton("💎 Upgrade to Pro", url=f"https://t.me/{admin}")]])

def kb_report(pic_url):
    admin = ADMIN_USERNAME.lstrip("@")
    lens  = f"https://lens.google.com/uploadbyurl?url={pic_url}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Reverse Image Search", url=lens)],
        [InlineKeyboardButton("💎 Upgrade to Pro", url=f"https://t.me/{admin}")],
    ])

# ══════════════════════════════════════════════════════════════════════════════
# REPORT FORMATTER
# ══════════════════════════════════════════════════════════════════════════════

def format_private_report(p):
    return (
        f"🔒 **Private Account**\n\n"
        f"👤 **Name:** {p.get('full_name','N/A')}\n"
        f"📛 **Username:** @{p.get('username','N/A')}\n"
        f"👥 **Followers:** {p.get('followers',0):,}\n"
        f"📝 **Bio:** {p.get('bio','N/A')}\n\n"
        f"⚠️ This account is **Private**. Full analytics require a public profile."
    )

def format_full_report(p):
    username  = p.get("username","N/A")
    followers = p.get("followers",0)
    posts     = p.get("posts",[])
    fake      = run_fake_analysis(p)
    cp        = check_all_platforms(username)

    # Posting frequency label
    n = p.get("post_count",0)
    if n == 0:         freq = "👻 Ghost Account"
    elif n < 10:       freq = "🐢 Low Activity"
    elif n < 100:      freq = "📅 Moderate"
    else:              freq = "🚀 Very Active"

    # Top 3 posts
    top = "\n".join(
        f"  {i+1}. [{posts[i]['likes']:,}❤️ {posts[i]['comments']:,}💬]({posts[i]['url']})"
        for i in range(min(3, len(posts)))
    ) or "  No posts."

    # Cross-platform
    cp_str = "\n".join(f"  {r['status']} **{r['name']}** — [Link]({r['url']})" for r in cp)

    text = (
        f"📊 **Instagram OSINT Report**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**👤 Profile**\n"
        f"• Name: {p.get('full_name','N/A')}\n"
        f"• Username: [@{username}](https://instagram.com/{username})\n"
        f"• Verified: {'✅' if p.get('is_verified') else '❌'}\n"
        f"• Category: {p.get('category','N/A')}\n"
        f"• Bio: {(p.get('bio') or '—')[:200]}\n"
        f"• Link: {p.get('external_url') or '—'}\n\n"
        f"**📈 Stats**\n"
        f"• Followers: {followers:,}  |  Following: {p.get('following',0):,}\n"
        f"• Posts: {n:,}  |  Activity: {freq}\n\n"
        f"**🔬 Fake Analysis** (last 10 posts)\n"
        f"• Avg Likes: {p.get('avg_likes',0):,}  |  Avg Comments: {p.get('avg_comments',0):,}\n"
        f"• Engagement: {fake['rate']}% — {fake['label']}\n"
        f"• Like Ratio: {fake['like_ratio']}\n"
        f"• Comments: {fake['comment']}\n\n"
        f"**🏆 Top Posts**\n{top}\n\n"
        f"**🌐 Cross-Platform**\n{cp_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    return text, p.get("profile_pic_url","")

# ══════════════════════════════════════════════════════════════════════════════
# BOT APP
# ══════════════════════════════════════════════════════════════════════════════

app = Client("instagram_osint_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ── Helpers ────────────────────────────────────────────────────────────────

async def check_force_join(client, user_id):
    try:
        m = await client.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        return m.status.name not in ("BANNED","LEFT","RESTRICTED")
    except UserNotParticipant:
        return False
    except Exception:
        return True  # fail open

def admin_only(func):
    async def wrapper(client, message):
        if message.from_user.id != ADMIN_ID:
            return
        await func(client, message)
    return wrapper

# ── /start ─────────────────────────────────────────────────────────────────

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client, message: Message):
    user = message.from_user
    if not await check_force_join(client, user.id):
        await message.reply_text(
            "👋 **Welcome!**\n\nJoin our channel first, then send /start again.",
            reply_markup=kb_join()
        )
        return
    await get_or_create_user(user.id, user.username, user.first_name)
    await message.reply_text(
        f"🕵️ **Instagram OSINT Bot**\n\n"
        f"Hello {user.first_name}! Send any Instagram username for a deep-dive report.\n\n"
        f"**Example:** `@cristiano`\n\n"
        f"🎁 You get **1 free search**. Upgrade to Pro for unlimited.\n\n"
        f"/help — How to use  |  /status — Your plan"
    )

# ── /help ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command("help") & filters.private)
async def cmd_help(client, message: Message):
    await message.reply_text(
        "**📖 How to use**\n\n"
        "1️⃣ Send any Instagram username (with or without @)\n"
        "2️⃣ The bot analyses the public profile\n"
        "3️⃣ You get engagement stats, fake detection & cross-platform check\n\n"
        "🔒 Private profiles show basic info only.\n"
        "🆓 Free users: 1 search  |  💎 Pro: Unlimited"
    )

# ── /status ────────────────────────────────────────────────────────────────

@app.on_message(filters.command("status") & filters.private)
async def cmd_status(client, message: Message):
    u = await get_user(message.from_user.id)
    if not u:
        await message.reply_text("❌ Not registered. Send /start first.")
        return
    plan = "💎 Pro (Unlimited)" if u["is_premium"] else "🆓 Free"
    await message.reply_text(f"**Your Status**\n\n• Plan: {plan}\n• Searches Used: {u['search_count']}")

# ── Admin: /addpremium ─────────────────────────────────────────────────────

@app.on_message(filters.command("addpremium") & filters.private)
@admin_only
async def cmd_add_premium(client, message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply_text("Usage: /addpremium [user_id]")
        return
    uid = int(parts[1])
    if await set_premium(uid, message.from_user.id):
        await message.reply_text(f"✅ User `{uid}` upgraded to Pro.")
        try:
            await client.send_message(uid, "🎉 Your account is now **Pro**! Enjoy unlimited searches.")
        except Exception:
            pass
    else:
        await message.reply_text(f"❌ User `{uid}` not found.")

# ── Admin: /removepremium ──────────────────────────────────────────────────

@app.on_message(filters.command("removepremium") & filters.private)
@admin_only
async def cmd_remove_premium(client, message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply_text("Usage: /removepremium [user_id]")
        return
    uid = int(parts[1])
    if await revoke_premium(uid):
        await message.reply_text(f"✅ Pro revoked for `{uid}`.")
    else:
        await message.reply_text(f"❌ User `{uid}` not found.")

# ── Admin: /userinfo ───────────────────────────────────────────────────────

@app.on_message(filters.command("userinfo") & filters.private)
@admin_only
async def cmd_user_info(client, message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply_text("Usage: /userinfo [user_id]")
        return
    u = await get_user(int(parts[1]))
    if not u:
        await message.reply_text("❌ User not found.")
        return
    plan = "💎 Pro" if u["is_premium"] else "🆓 Free"
    joined = u["joined_at"].strftime("%Y-%m-%d") if u.get("joined_at") else "N/A"
    last   = u["last_search_at"].strftime("%Y-%m-%d %H:%M") if u.get("last_search_at") else "Never"
    await message.reply_text(
        f"**User Info**\n\n"
        f"• ID: `{u['user_id']}`\n• Name: {u.get('first_name','N/A')}\n"
        f"• Plan: {plan}\n• Searches: {u['search_count']}\n"
        f"• Joined: {joined}\n• Last Search: {last}"
    )

# ── Admin: /stats ──────────────────────────────────────────────────────────

@app.on_message(filters.command("stats") & filters.private)
@admin_only
async def cmd_stats(client, message: Message):
    s = await get_stats()
    await message.reply_text(
        f"**📊 Bot Stats**\n\n"
        f"• Total Users: {s['total']:,}\n"
        f"• Pro: {s['premium']:,}\n"
        f"• Free: {s['free']:,}"
    )

# ── Admin: /broadcast ──────────────────────────────────────────────────────

@app.on_message(filters.command("broadcast") & filters.private)
@admin_only
async def cmd_broadcast(client, message: Message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply_text("Usage: /broadcast [message]")
        return
    text  = parts[1]
    users = await get_all_users()
    sent, failed = 0, 0
    msg = await message.reply_text(f"📢 Sending to {len(users)} users...")
    for u in users:
        try:
            await client.send_message(u["user_id"], text)
            sent += 1
        except Exception:
            failed += 1
    await msg.edit_text(f"✅ Done.\n\n• Sent: {sent}\n• Failed: {failed}")

# ── Main search handler ────────────────────────────────────────────────────

IG_RE = re.compile(r"^@?[A-Za-z0-9_.]{1,30}$")

@app.on_message(
    filters.text & filters.private &
    ~filters.command(["start","help","status","addpremium","removepremium","userinfo","stats","broadcast"])
)
async def handle_search(client, message: Message):
    raw = message.text.strip()
    if not IG_RE.match(raw):
        await message.reply_text("❓ Send a valid Instagram username. Example: `@username`")
        return

    user = message.from_user

    if not await check_force_join(client, user.id):
        await message.reply_text("⚠️ Join our channel first.", reply_markup=kb_join())
        return

    user_data = await get_or_create_user(user.id, user.username, user.first_name)

    if not user_data["is_premium"] and user_data["search_count"] >= FREE_SEARCH_LIMIT:
        await message.reply_text(
            f"🚫 **Free Limit Reached!**\n\n"
            f"You've used your {FREE_SEARCH_LIMIT} free search(es).\n"
            f"Upgrade to Pro for unlimited access.\n"
            f"👤 Contact: {ADMIN_USERNAME}",
            reply_markup=kb_admin()
        )
        return

    ig_username = raw.lstrip("@").strip()
    status_msg  = await message.reply_text(f"🔍 Analysing `@{ig_username}`...")

    profile = fetch_instagram_profile(ig_username)
    if not profile:
        await status_msg.edit_text(
            f"❌ **Not Found**\n\n`@{ig_username}` doesn't exist or couldn't be retrieved."
        )
        return

    await increment_search(user.id)

    if profile.get("is_private"):
        await status_msg.edit_text(format_private_report(profile))
        await log_search(user.id, ig_username, "private", "Private profile")
        return

    report, pic_url = format_full_report(profile)
    await status_msg.delete()
    await message.reply_text(report, reply_markup=kb_report(pic_url), disable_web_page_preview=True)
    await log_search(user.id, ig_username, "public", f"ER: {profile.get('avg_likes',0)} avg likes")

# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    await connect_db()
    print("[Bot] Starting...")
    await app.start()
    print("[Bot] Running. Ctrl+C to stop.")
    await asyncio.Event().wait()
    await app.stop()
    await close_db()

if __name__ == "__main__":
    asyncio.run(main())
