import asyncio
import os
from sqlalchemy import select, update
from app.database.session import AsyncSessionLocal
from app.database.models.message import Message
from app.database.models.embedding_job import EmbeddingJob

async def backfill():
    os.environ["DATABASE_URL"] = "postgresql+psycopg://chatbot_staging:CAgiTx9O9tpcuoKh@127.0.0.1:5432/chatbot_staging"
    
    async with AsyncSessionLocal() as session:
        # Find all text messages > 10 chars that don't have needs_embedding
        stmt = select(Message).where(Message.text.is_not(None))
        result = await session.execute(stmt)
        messages = result.scalars().all()
        
        count = 0
        for msg in messages:
            if msg.text and len(msg.text.strip()) >= 10:
                msg.needs_embedding = True
                
                # Check if job exists
                job_stmt = select(EmbeddingJob).where(
                    EmbeddingJob.source_type == 'message',
                    EmbeddingJob.source_id == msg.id
                )
                existing = (await session.execute(job_stmt)).scalar_one_or_none()
                
                if not existing:
                    job = EmbeddingJob(
                        source_type='message',
                        source_id=msg.id,
                        status='pending'
                    )
                    session.add(job)
                    count += 1
        
        await session.commit()
        print(f"Backfilled {count} messages for embedding.")

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(backfill())
