import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import AsyncSessionLocal
from app.memory.interfaces import EmbeddingWorkerInterface
from app.memory.embedding_service import EmbeddingService
from app.database.repositories.embedding_repository import EmbeddingRepository
from app.database.models.embedding_job import EmbeddingJob
from app.database.models.message import Message

logger = logging.getLogger(__name__)

class InProcessWorker(EmbeddingWorkerInterface):
    def __init__(self, embedding_service: EmbeddingService, poll_interval: int = 5):
        self.embedding_service = embedding_service
        self.poll_interval = poll_interval
        self._running = False
        self._task = None
        self.shadow_semaphore = asyncio.Semaphore(5)

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"InProcessWorker started (poll interval: {self.poll_interval}s)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("InProcessWorker stopped")

    async def _loop(self) -> None:
        import time
        import os
        heartbeat_file = os.getenv("WORKER_HEARTBEAT_FILE", "/tmp/embedding_worker_heartbeat")
        while self._running:
            try:
                # Update heartbeat
                with open(heartbeat_file, "w") as f:
                    f.write(str(time.time()))
                
                await self._process_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in EmbeddingWorker loop: {e}", exc_info=True)
            await asyncio.sleep(self.poll_interval)



    async def _process_batch(self) -> None:
        async with AsyncSessionLocal() as session:
            repo = EmbeddingRepository(session)
            jobs = await repo.get_pending_jobs(limit=10)
            
            if not jobs:
                return
                
            for job in jobs:
                await self.process_job(job.id)

    async def process_job(self, job_id: int) -> None:
        async with AsyncSessionLocal() as session:
            repo = EmbeddingRepository(session)
            
            job = await session.get(EmbeddingJob, job_id)
            if not job:
                return
            
            try:
                await repo.update_job_status(job_id, "processing")
                await session.commit()
            except Exception as e:
                logger.error(f"Failed to lock job {job_id}: {e}")
                return

            try:
                # 1. Fetch Source Data
                # Currently we only support 'message'
                text_to_embed = None
                if job.source_type == "message":
                    message = await session.get(Message, job.source_id)
                    if message:
                        if message.message_type not in ("text",):
                            # Skip media types for now until Voice/Video Intelligence is ready
                            await repo.update_job_status(job_id, "completed", error="Skipped non-text message type")
                            await session.commit()
                            return
                        if message.text:
                            text_to_embed = message.text
                
                if not text_to_embed:
                    await repo.update_job_status(job_id, "completed", error="No text found or unsupported source_type")
                    await session.commit()
                    return

                # 2. Fact Extraction (ACTIVE MODE)
                extract_res = await self.embedding_service.extract_fact(text_to_embed)
                
                # Log Fact Extraction to llm_logs
                import os
                from app.database.models.llm_log import LlmLog
                in_tok = extract_res.get("input_tokens", 0)
                out_tok = extract_res.get("output_tokens", 0)
                lat_ms = extract_res.get("latency_ms", 0)
                cost_fact = (in_tok / 1_000_000 * 0.075) + (out_tok / 1_000_000 * 0.30)
                
                msg_chat_id = message.chat_id if message else None
                msg_user_id = message.user_id if message else None
                log_entry = LlmLog(
                    chat_id=msg_chat_id,
                    user_id=msg_user_id,
                    model=os.getenv("GEMINI_MODEL", "models/gemini-3.5-flash-lite"),
                    request_type="memory_extract",
                    prompt_tokens=in_tok,
                    completion_tokens=out_tok,
                    latency_ms=lat_ms,
                    cost_usd=cost_fact,
                    success=True
                )
                session.add(log_entry)
                
                # Cleanup old chunks if any
                await repo.delete_chunks_by_source(job.source_type, job.source_id)
                
                if extract_res["classification"] == "NO_MEMORY":
                    await repo.update_job_status(job_id, "completed")
                    await session.commit()
                    logger.info(f"Processed embedding job {job_id} for {job.source_type}:{job.source_id} -> NO_MEMORY (filtered)")
                    return
                    
                fact_text = extract_res["extracted"]

                # 3. Get Embedding for the Extracted Fact
                result = await self.embedding_service.get_embedding(fact_text)

                # 4. Check for Semantic Duplicates
                is_duplicate = await repo.is_semantic_duplicate(
                    source_type=job.source_type,
                    embedding=result.embedding,
                    threshold=0.92,
                    user_id=msg_user_id
                )
                
                if is_duplicate:
                    logger.info(f"Skipped duplicate fact for job {job_id}: '{fact_text}'")
                else:
                    # Save new chunk
                    versioned_model = f"{result.model}|v1"
                    await repo.save_chunk(
                        source_type=job.source_type,
                        source_id=job.source_id,
                        text_chunk=fact_text,
                        embedding=result.embedding,
                        model=versioned_model,
                        hash_val=result.hash_val
                    )
                    logger.info(f"Processed embedding job {job_id} for {job.source_type}:{job.source_id} -> FACT_SAVED: '{fact_text}'")

                # 5. Mark Completed
                await repo.update_job_status(job_id, "completed")
                await session.commit()
                
            except Exception as e:
                is_quota = False
                e_str = str(e)
                if "429" in e_str or "RESOURCE_EXHAUSTED" in e_str or getattr(e, "code", None) == 429:
                    is_quota = True
                    
                if is_quota:
                    logger.warning(f"[Embedding] Primary embedding model quota exhausted (429) for job {job_id}. Scheduled for backoff retry.")
                    await repo.update_job_status(job_id, "failed", error="QUOTA_EXHAUSTED")
                    await session.commit()
                    await asyncio.sleep(30)
                else:
                    logger.error(f"Failed to process embedding job {job_id}: {e}", exc_info=True)
                    await repo.update_job_status(job_id, "failed", error=str(e))
                    await session.commit()

async def main():
    from app.memory.embedding_service import EmbeddingConfig
    logging.basicConfig(level=logging.INFO)
    
    # Enable Windows loop if testing locally, but fine for Linux
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    worker = InProcessWorker(EmbeddingService(EmbeddingConfig()), poll_interval=5)
    await worker.start()
    
    # Run forever
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
