from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.database.models.embedding_job import EmbeddingJob
from app.database.models.memory_chunk import MemoryChunk
from app.database.models.message import Message

class EmbeddingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_pending_jobs(self, limit: int = 10) -> List[EmbeddingJob]:
        """Fetch strictly new pending jobs (attempts < 3). Failed jobs are never retried automatically."""
        stmt = (
            select(EmbeddingJob)
            .where(EmbeddingJob.status == "pending")
            .where(EmbeddingJob.attempts < 3)
            .order_by(EmbeddingJob.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_job_status(self, job_id: int, status: str, error: Optional[str] = None):
        """Update job status and handle attempts/timestamps."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(EmbeddingJob)
            .where(EmbeddingJob.id == job_id)
            .values(
                status=status,
                last_error=error,
                attempts=EmbeddingJob.attempts + (1 if status == "processing" else 0),
                processed_at=now if status in ["completed", "failed"] else None,
                updated_at=now
            )
        )
        await self.session.execute(stmt)

    async def delete_chunks_by_source(self, source_type: str, source_id: int):
        """Delete all chunks for a given source."""
        from sqlalchemy import delete
        stmt = delete(MemoryChunk).where(
            MemoryChunk.source_type == source_type,
            MemoryChunk.source_id == source_id
        )
        await self.session.execute(stmt)

    async def is_semantic_duplicate(self, source_type: str, embedding: List[float], threshold: float = 0.92, user_id: Optional[int] = None) -> bool:
        """Check if a semantically similar memory chunk already exists (cosine similarity >= threshold)."""
        import numpy as np
        stmt = select(MemoryChunk.embedding).where(
            MemoryChunk.source_type == source_type,
            MemoryChunk.embedding.is_not(None)
        )
        if user_id is not None and source_type == "message":
            stmt = stmt.join(
                Message,
                (MemoryChunk.source_id == Message.id) & (MemoryChunk.source_type == "message")
            ).where(Message.user_id == user_id)

        result = await self.session.execute(stmt)
        existing_vectors = result.scalars().all()
        if not existing_vectors:
            return False
            
        vecs_np = np.array(existing_vectors)
        query_np = np.array(embedding)
        
        query_norm = np.linalg.norm(query_np)
        if query_norm == 0:
            return False
            
        vecs_norm = np.linalg.norm(vecs_np, axis=1, keepdims=True)
        vecs_norm[vecs_norm == 0] = 1.0
        
        sims = np.dot(vecs_np / vecs_norm, query_np / query_norm)
        return bool(np.any(sims >= threshold))

    async def save_chunk(self, source_type: str, source_id: int, text_chunk: str, embedding: List[float], model: str, hash_val: str) -> MemoryChunk:
        """Save a new memory chunk."""
        # Check if exactly the same chunk for the same source already exists
        stmt = select(MemoryChunk).where(
            MemoryChunk.source_type == source_type,
            MemoryChunk.source_id == source_id,
            MemoryChunk.embedding_hash == hash_val
        )
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        
        if existing:
            return existing
            
        chunk = MemoryChunk(
            source_type=source_type,
            source_id=source_id,
            text_chunk=text_chunk,
            embedding=embedding,
            embedding_model=model,
            embedding_hash=hash_val
        )
        self.session.add(chunk)
        return chunk

