import asyncio
import logging
import os
import sys
from typing import Optional

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.database.session import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("telegram_ai_bot")

class BotContext:
    bot_id: Optional[int] = None
    bot_username: Optional[str] = None
    bot_first_name: Optional[str] = None

bot_context = BotContext()

async def on_startup(bot: Bot):
    logger.info("Initializing Database...")
    await init_db()

    logger.info("Fetching Bot Identity via getMe()...")
    me = await bot.get_me()
    bot_context.bot_id = me.id
    bot_context.bot_username = me.username
    bot_context.bot_first_name = me.first_name
    logger.info(f"Bot initialized: {bot_context.bot_first_name} (@{bot_context.bot_username})")

async def on_shutdown(bot: Bot):
    logger.info("Bot is shutting down cleanly...")

async def main():
    from dotenv import load_dotenv
    load_dotenv()
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set in environment!")
        print("\nERROR: TELEGRAM_BOT_TOKEN is missing from .env file.")
        print("Please set TELEGRAM_BOT_TOKEN in .env to run live bot ingest.\n")
        sys.exit(1)

    from aiogram.client.session.aiohttp import AiohttpSession
    import aiohttp
    import socket
    
    class IPv4Session(AiohttpSession):
        async def create_session(self) -> aiohttp.ClientSession:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(family=socket.AF_INET),
                    trust_env=True
                )
            return self._session

    session = IPv4Session()

    bot = Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    from app.bot.router import main_router
    dp.include_router(main_router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting Telegram Bot...")
    
    # Start health server
    from aiohttp import web
    from sqlalchemy import text
    from app.database.session import async_engine

    async def health_check(request):
        status = {"status": "ok"}
        try:
            async with async_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
                
                # Check for dead worker: any pending jobs older than 5 minutes
                # AND worker heartbeat is older than 2 minutes
                res = await conn.execute(text("SELECT COUNT(*) FROM embedding_jobs WHERE status = 'pending' AND created_at < NOW() - INTERVAL '5 minutes'"))
                stale_jobs = res.scalar() or 0
                
                import time
                import os
                heartbeat_file = os.getenv("WORKER_HEARTBEAT_FILE", "/tmp/embedding_worker_heartbeat")
                worker_alive = False
                if os.path.exists(heartbeat_file):
                    try:
                        with open(heartbeat_file, "r") as f:
                            last_hb = float(f.read().strip())
                        if time.time() - last_hb < 120:
                            worker_alive = True
                    except Exception:
                        pass
                
                # Health logic: If there are stale jobs, the worker MUST be processing them (alive). 
                # If worker is dead AND there are stale jobs, it's an error.
                status["memory_worker"] = worker_alive
                
            status["database"] = True
        except Exception as e:
            status["database"] = False
            status["memory_worker"] = False
            status["status"] = "error"
            logger.error(f"Health check DB error: {e}")

        has_gemini = bool(os.getenv("GEMINI_API_KEY"))
        llm_enabled_env = os.getenv("LLM_ENABLED", "true").lower() == "true"
        status["gemini_key"] = has_gemini
        status["llm_enabled"] = llm_enabled_env

        http_status = 200 if status["status"] == "ok" else 503
        return web.json_response(status, status=http_status)

    app = web.Application()
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Health server listening on 0.0.0.0:8080")

    await dp.start_polling(bot)


