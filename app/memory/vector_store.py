import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.memory.interfaces import VectorStoreInterface
from app.database.models.memory_chunk import MemoryChunk
from app.database.models.message import Message

class NumpyVectorStore(VectorStoreInterface):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_chunk(self, source_type: str, source_id: int, text_chunk: str, embedding: List[float], model: str, embedding_hash: str) -> None:
        """Handled by EmbeddingRepository directly in worker for simplicity. 
        But we can implement it here to satisfy the interface if needed."""
        pass

    async def search_similar(
        self, 
        chat_id: Optional[int], 
        query_embedding: List[float], 
        top_k: int = 10,
        user_db_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Search for the most similar chunks strictly for a specific user using NumPy in memory."""
        
        stmt = (
            select(MemoryChunk, Message)
            .join(Message, (MemoryChunk.source_id == Message.id) & (MemoryChunk.source_type == 'message'))
            .where(MemoryChunk.embedding.is_not(None))
        )
        if user_db_id is not None:
            # STRICT ISOLATION: Memory belongs ONLY to the author of the current message
            stmt = stmt.where(Message.user_id == user_db_id)
        elif chat_id is not None:
            stmt = stmt.where(Message.chat_id == chat_id)
        
        result = await self.session.execute(stmt)
        rows = result.all()
        
        if not rows:
            return []
            
        chunks = []
        vectors = []
        
        for chunk, msg in rows:
            chunks.append({
                "chunk_id": chunk.id,
                "text": chunk.text_chunk,
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "date": msg.date,
                "user_id": msg.user_id,
                "chat_id": msg.chat_id
            })
            vectors.append(chunk.embedding)
            
        if not vectors:
            return []
            
        # 2. Compute Cosine Similarity via NumPy
        vectors_np = np.array(vectors)
        query_np = np.array(query_embedding)
        
        vectors_norm = np.linalg.norm(vectors_np, axis=1, keepdims=True)
        query_norm = np.linalg.norm(query_np)
        
        vectors_norm[vectors_norm == 0] = 1.0
        if query_norm == 0:
            query_norm = 1.0
            
        normalized_vectors = vectors_np / vectors_norm
        normalized_query = query_np / query_norm
        
        similarities = np.dot(normalized_vectors, normalized_query)
        
        # 3. Sort and get top K
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            res = dict(chunks[idx])
            res["score"] = float(similarities[idx])
            results.append(res)
            
        return results

    async def get_user_memories(self, user_db_id: int) -> List[str]:
        """Fetch all text chunks for a specific user directly without embedding search."""
        stmt = (
            select(MemoryChunk.text_chunk)
            .join(Message, (MemoryChunk.source_id == Message.id) & (MemoryChunk.source_type == 'message'))
            .where(Message.user_id == user_db_id)
            .order_by(MemoryChunk.id.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

