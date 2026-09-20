import asyncio
import os
import sys
from app.database.session import AsyncSessionLocal
from app.memory.embedding_service import EmbeddingService, EmbeddingConfig
from app.workers.embedding_worker import InProcessWorker
from app.database.repositories.embedding_repository import EmbeddingRepository

async def run_worker_once():
    os.environ["DATABASE_URL"] = "postgresql+psycopg://chatbot_staging:CAgiTx9O9tpcuoKh@127.0.0.1:5432/chatbot_staging"
    
    config = EmbeddingConfig()
    service = EmbeddingService(config)
    worker = InProcessWorker(service)
    
    async with AsyncSessionLocal() as session:
        repo = EmbeddingRepository(session)
        jobs = await repo.get_pending_jobs(limit=10)
        
        print(f"Found {len(jobs)} pending jobs.")
        for job in jobs:
            print(f"Processing job {job.id} (source: {job.source_type}:{job.source_id})...")
            await worker.process_job(job.id)
            
    print("Done processing jobs.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_worker_once())
