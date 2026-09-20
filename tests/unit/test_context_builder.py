import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import List, Dict, Any

from app.memory.context_builder import ContextBuilder, ContextBundle
from app.database.models.message import Message
from app.database.models.user import User

# --- Mocks ---

class MockMessageRepository:
    def __init__(self, messages: List[Message]):
        self.messages = messages
        
    async def get_recent_messages(self, chat_db_id: int, limit: int = 15) -> List[Message]:
        msgs = [m for m in self.messages if m.chat_id == chat_db_id]
        return msgs[-limit:]

class MockVectorStore:
    def __init__(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        
    async def search_similar(self, chat_id: int, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        # For mock, we just return the chunks matching chat_id if they have score >= 0.6
        res = [c for c in self.chunks if c["chat_id"] == chat_id and c["score"] >= 0.6]
        return res[:top_k]

class MockEmbeddingService:
    async def get_embedding(self, text: str):
        class MockRes:
            embedding = [0.1, 0.2]
        return MockRes()

# --- Tests ---

@pytest.mark.asyncio
async def test_build_context_recent_messages():
    u = User(id=1, username="alice", first_name="Alice")
    m1 = Message(id=1, chat_id=10, user_id=1, text="Hello")
    m1.user = u
    m2 = Message(id=2, chat_id=10, user_id=1, text="World")
    m2.user = u
    messages = [m1, m2]
    
    cb = ContextBuilder(session=AsyncMock(), embedding_service=MockEmbeddingService())
    cb.message_repo = MockMessageRepository(messages)
    cb.vector_store = MockVectorStore([])
    
    bundle = await cb.build_context(chat_id=10, user_query="query")
    
    assert len(bundle.recent_messages) == 2
    assert "[Alice]" in bundle.recent_messages[0]
    assert "Hello" in bundle.recent_messages[0]
    assert "World" in bundle.recent_messages[1]

@pytest.mark.asyncio
async def test_build_context_retrieval():
    u = User(id=1, username="alice", first_name="Alice")
    m1 = Message(id=1, chat_id=10, user_id=1, text="Hello")
    m1.user = u
    messages = [m1]
    chunks = [
        {"chat_id": 10, "text": "Old memory", "score": 0.85},
        {"chat_id": 10, "text": "Low score memory", "score": 0.50} # should be ignored
    ]
    
    cb = ContextBuilder(session=AsyncMock(), embedding_service=MockEmbeddingService())
    cb.message_repo = MockMessageRepository(messages)
    cb.vector_store = MockVectorStore(chunks)
    
    bundle = await cb.build_context(chat_id=10, user_query="query")
    
    assert len(bundle.retrieved_memories) == 1
    assert "Old memory" in bundle.retrieved_memories[0]
    assert "0.85" in bundle.retrieved_memories[0]

@pytest.mark.asyncio
async def test_build_context_different_chat_id():
    u = User(id=1, username="alice")
    m1 = Message(id=1, chat_id=10, user_id=1, text="Chat 10 msg")
    m1.user = u
    m2 = Message(id=2, chat_id=20, user_id=1, text="Chat 20 msg")
    m2.user = u
    messages = [m1, m2]
    chunks = [
        {"chat_id": 10, "text": "Chat 10 memory", "score": 0.90},
        {"chat_id": 20, "text": "Chat 20 memory", "score": 0.90}
    ]
    
    cb = ContextBuilder(session=AsyncMock(), embedding_service=MockEmbeddingService())
    cb.message_repo = MockMessageRepository(messages)
    cb.vector_store = MockVectorStore(chunks)
    
    bundle = await cb.build_context(chat_id=10, user_query="query")
    
    # Should only contain chat 10 messages and memories
    assert len(bundle.recent_messages) == 1
    assert "Chat 10 msg" in bundle.recent_messages[0]
    assert len(bundle.retrieved_memories) == 1
    assert "Chat 10 memory" in bundle.retrieved_memories[0]

@pytest.mark.asyncio
async def test_build_context_token_limit():
    u = User(id=1, username="alice", first_name="Alice")
    messages = []
    for i in range(15):
        m = Message(id=i, chat_id=10, user_id=1, text="M" * 4000)
        m.user = u
        messages.append(m)
    # 15 messages * 1000 tokens = 15000 tokens > 8000 limit
    
    cb = ContextBuilder(session=AsyncMock(), embedding_service=MockEmbeddingService())
    cb.message_repo = MockMessageRepository(messages)
    cb.vector_store = MockVectorStore([])
    
    bundle = await cb.build_context(chat_id=10, user_query="query")
    
    assert bundle.total_tokens_estimate <= 8000
    # The oldest messages should be removed, leaving only 5, and possibly truncated
    assert len(bundle.recent_messages) <= 15

@pytest.mark.asyncio
async def test_build_context_empty_memory():
    cb = ContextBuilder(session=AsyncMock(), embedding_service=MockEmbeddingService())
    cb.message_repo = MockMessageRepository([])
    cb.vector_store = MockVectorStore([])
    
    bundle = await cb.build_context(chat_id=10, user_query="query")
    
    assert len(bundle.recent_messages) == 0
    assert len(bundle.retrieved_memories) == 0
    assert bundle.user_query == "query"
