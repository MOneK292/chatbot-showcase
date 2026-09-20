import asyncio
import os
import sys
from sqlalchemy import inspect, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import async_engine, DATABASE_URL

async def check_database():
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            
            def check_tables(sync_conn):
                inspector = inspect(sync_conn)
                return inspector.get_table_names()
            
            tables = await conn.run_sync(check_tables)
            required = {"users", "chats", "chat_members", "messages"}
            missing = required - set(tables)
            if missing:
                print(f"[Healthcheck Warning] Missing tables: {missing}")
                return False
            return True
    except Exception as e:
        print(f"[Healthcheck Error] Database connection failed ({DATABASE_URL}): {e}")
        return False

async def check_redis():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(redis_url)
        pong = await client.ping()
        await client.aclose()
        return bool(pong)
    except Exception as e:
        print(f"[Healthcheck Warning] Redis connection failed ({redis_url}): {e}")
        return False

async def main():
    print("=== Health Check Status ===")
    db_ok = await check_database()
    redis_ok = await check_redis()
    
    print(f"Database ({'SQLite' if 'sqlite' in DATABASE_URL else 'PostgreSQL'}) : {'OK' if db_ok else 'FAILED / MISSING TABLES'}")
    print(f"Redis                          : {'OK' if redis_ok else 'WARNING (Not reachable)'}")
    
    if not db_ok:
        sys.exit(1)
    print("Health check completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
