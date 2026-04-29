from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
from database.db import connect_db, close_db
from handlers.start import register_start_handler
from handlers.search import register_search_handler
from handlers.admin import register_admin_handlers


def create_app() -> Client:
    return Client(
        name="instagram_osint_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )


async def main():
    app = create_app()

    # Connect to MongoDB
    await connect_db()

    # Register all handlers
    register_start_handler(app)
    register_search_handler(app)
    register_admin_handlers(app)

    print("[Bot] Starting...")
    await app.start()
    print("[Bot] Running. Press Ctrl+C to stop.")

    await app.idle()

    await app.stop()
    await close_db()
    print("[Bot] Stopped.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
