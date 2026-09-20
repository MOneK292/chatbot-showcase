from abc import ABC, abstractmethod
from typing import List

class EmbeddingWorkerInterface(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Start the worker to process background jobs."""
        pass

    @abstractmethod
    async def process_job(self, job_id: int) -> None:
        """Process a specific embedding job by its ID."""
        pass

class VectorStoreInterface(ABC):
    @abstractmethod
    async def save_chunk(self, source_type: str, source_id: int, text_chunk: str, embedding: List[float], model: str, embedding_hash: str) -> None:
        """Save a new memory chunk with its embedding."""
        pass

    @abstractmethod
    async def search_similar(self, chat_id: int, query_embedding: List[float], top_k: int = 5) -> List[dict]:
        """Search for the most similar chunks within a specific chat."""
        pass
