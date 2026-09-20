import asyncio
import logging
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from app.database.session import async_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("cleanup_cron")

async def run_cleanup():
    logger.info("Starting database cleanup cron job...")
    
    queries = [
        (
            "DELETE FROM llm_logs WHERE created_at < NOW() - INTERVAL '90 days'",
            "Deleted old llm_logs"
        ),
        (
            "DELETE FROM embedding_jobs WHERE status='completed' AND created_at < NOW() - INTERVAL '30 days'",
            "Deleted old completed embedding_jobs"
        ),
        (
            "DELETE FROM embedding_jobs WHERE status='failed' AND created_at < NOW() - INTERVAL '7 days'",
            "Deleted old failed embedding_jobs"
        ),
        (
            "UPDATE embedding_jobs SET status='pending', updated_at=NOW() WHERE status='processing' AND updated_at < NOW() - INTERVAL '1 day'",
            "Reanimated stalled processing embedding_jobs"
        )
    ]
    
    try:
        async with async_engine.begin() as conn:
            for sql, description in queries:
                result = await conn.execute(text(sql))
                logger.info(f"{description}: {result.rowcount} rows affected.")
                
        logger.info("Cleanup completed successfully.")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_cleanup())
