import os
import re
from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.repositories.message_repository import MessageRepository
from app.memory.vector_store import NumpyVectorStore
from app.memory.embedding_service import EmbeddingService

@dataclass
class ContextBundle:
    user_query: str
    recent_messages: List[str]
    retrieved_memories: List[str]
    total_tokens_estimate: int
    current_user_name: str = "Unknown"
    current_user_id: Optional[int] = None
    is_identity_query: bool = False

def is_identity_query(query: str) -> bool:
    """Check if query is asking about the user's personal identity or facts about themselves."""
    clean = re.sub(r'@[a-zA-Z0-9_]+', '', query).strip().lower()
    clean = re.sub(r'[^\w\s]', '', clean).strip()
    return clean in {
        "кто я", "кто я такой", "кто я такая", "как меня зовут", "скажи мое имя", "скажи моё имя",
        "скажи как меня зовут", "ты помнишь меня", "помнишь меня", "что ты обо мне знаешь",
        "что ты знаешь обо мне", "знаешь кто я", "как мое имя", "как моё имя", "мое имя", "моё имя",
        "ты знаешь кто я", "ты меня помнишь", "назови мое имя", "назови моё имя", "обо мне",
        "кто я для тебя", "кто я тебе"
    }

class ContextBuilder:
    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService):
        import os
        self.session = session
        self.message_repo = MessageRepository(session)
        self.vector_store = NumpyVectorStore(session)
        self.embedding_service = embedding_service
        self.max_tokens = int(os.getenv("MAX_CONTEXT_TOKENS", "8000"))
        self.memory_top_k = int(os.getenv("MEMORY_TOP_K", "10"))
        self.memory_min_score = float(os.getenv("MEMORY_MIN_SCORE", "0.70"))
        self.memory_context_top_k = int(os.getenv("MEMORY_CONTEXT_TOP_K", "5"))
        self.identity_memory_top_k = int(os.getenv("IDENTITY_MEMORY_TOP_K", "10"))
        
    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4
        
    def _calculate_total_tokens(self, query: str, recent: List[str], retrieved: List[str]) -> int:
        total = self._estimate_tokens(query)
        for msg in recent:
            total += self._estimate_tokens(msg)
        for mem in retrieved:
            total += self._estimate_tokens(mem)
        return total

    async def build_context(
        self, 
        chat_id: int, 
        user_query: str, 
        message_db_id: Optional[int] = None,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None
    ) -> ContextBundle:
        import logging
        logger = logging.getLogger(__name__)
        
        display_user_name = user_name or "Unknown"
        
        logger.info(
            f"[CONTEXT_DEBUG] chat_id={chat_id} user_id={user_id} user_name='{display_user_name}' "
            f"message_db_id={message_db_id} query='{user_query}'"
        )
        
        # Safety: truncate user_query if it exceeds the context budget
        max_query_chars = self.max_tokens * 4
        if len(user_query) > max_query_chars:
            user_query = user_query[:max_query_chars]
        
        # 0. Get internal chat DB ID & internal user DB ID
        from sqlalchemy import select
        from app.database.models.chat import Chat
        from app.database.models.user import User
        
        stmt = select(Chat.id).where(Chat.telegram_chat_id == chat_id)
        chat_db_id = (await self.session.execute(stmt)).scalar_one_or_none()
        
        user_db_id = None
        if user_id is not None:
            stmt_user = select(User.id).where(User.telegram_id == user_id)
            user_db_id = (await self.session.execute(stmt_user)).scalar_one_or_none()
        
        if not chat_db_id:
            return ContextBundle(
                user_query=user_query, 
                recent_messages=[], 
                retrieved_memories=[], 
                total_tokens_estimate=self._estimate_tokens(user_query),
                current_user_name=display_user_name,
                current_user_id=user_id
            )

        # 1. SPECIAL CASE: Identity Query ("Кто я?", "Как меня зовут?")
        # Strictly isolated: ZERO group short-term memory, ZERO reply context, ONLY user's personal memories.
        if is_identity_query(user_query):
            user_memories = []
            if user_db_id is not None:
                user_memories = await self.vector_store.get_user_memories(user_db_id)
                
            retrieved = [f"[Personal Memory]: {m}" for m in user_memories[:self.identity_memory_top_k]]
            logger.info(
                f"[IDENTITY_QUERY_DETECTED] user_id={user_id} db_id={user_db_id} "
                f"personal_memories_count={len(user_memories)}"
            )
            return ContextBundle(
                user_query=user_query,
                recent_messages=[], # ZERO group history to prevent bleed
                retrieved_memories=retrieved,
                total_tokens_estimate=self._estimate_tokens(user_query) + sum(self._estimate_tokens(m) for m in retrieved),
                current_user_name=display_user_name,
                current_user_id=user_id,
                is_identity_query=True
            )

        def _format_message(msg) -> str:
            if not msg.text:
                return ""
            author_name = msg.user.username if (msg.user and msg.user.username) else f"User {msg.user_id}"
            if msg.user and msg.user.first_name:
                author_name = msg.user.first_name
            
            timestamp = msg.date.strftime("%Y-%m-%d %H:%M")
            msg_text = f"[{timestamp}]\nAuthor: {author_name} (User ID: {msg.user_id})\n"
            
            if msg.is_forward:
                fwd_author = "Unknown"
                if msg.raw_metadata:
                    fwd_author = msg.raw_metadata.get("forward_origin", "Unknown")
                msg_text += f"[Forwarded from: {fwd_author}]\n"
                
            msg_text += f"Text:\n{msg.text}"
            return msg_text

        # 2. Fetch Reply Chain (if message_db_id is provided)
        reply_chain_msgs = []
        reply_chain_ids = set()
        
        if message_db_id:
            chain = await self.message_repo.get_reply_chain(message_db_id, max_depth=10)
            chain = [m for m in chain if m.id != message_db_id]
            
            current_chain_chars = 0
            MAX_REPLY_CONTEXT_CHARS = 2000
            
            for m in chain:
                if not m.text: continue
                fmt = _format_message(m)
                if current_chain_chars + len(fmt) > MAX_REPLY_CONTEXT_CHARS:
                    fmt = fmt[:MAX_REPLY_CONTEXT_CHARS - current_chain_chars] + "...\n(truncated)"
                    reply_chain_msgs.append(fmt)
                    reply_chain_ids.add(m.id)
                    break
                reply_chain_msgs.append(fmt)
                reply_chain_ids.add(m.id)
                current_chain_chars += len(fmt)

        # 3. Fetch short-term memory (recent 15 messages)
        recent_msgs_db = await self.message_repo.get_recent_messages(chat_db_id, limit=15)
        recent_messages = []
        for msg in recent_msgs_db:
            if msg.id == message_db_id or msg.id in reply_chain_ids:
                continue
            
            if not msg.text:
                continue
                
            recent_messages.append(_format_message(msg))
            
        # Combine into Hybrid Context
        final_recent = []
        if reply_chain_msgs:
            final_recent.append("=== [REPLY CONTEXT] ===\n" + "\n\n".join(reply_chain_msgs))
        if recent_messages:
            final_recent.append("=== [RECENT CONTEXT] ===\n" + "\n\n".join(recent_messages))
            
        # 4. Fetch long-term memory (STRICTLY ISOLATED TO CURRENT USER)
        retrieved_memories = []
        if user_query.strip():
            try:
                emb_res = await self.embedding_service.get_embedding(user_query)
                results = await self.vector_store.search_similar(
                    chat_id=chat_db_id, 
                    query_embedding=emb_res.embedding, 
                    top_k=self.memory_top_k,
                    user_db_id=user_db_id # STRICT USER ISOLATION
                )
                
                valid_results = [res for res in results if res["score"] >= self.memory_min_score]
                valid_results = valid_results[:self.memory_context_top_k]
                
                for res in valid_results:
                    retrieved_memories.append(f"[Score: {res['score']:.2f} | Personal Memory]: {res['text']}")
                    
                logger.info(
                    f"[MEMORY_DEBUG] query='{user_query}' user_id={user_id} user_db_id={user_db_id} "
                    f"retrieved_count={len(retrieved_memories)} retrieved_memories={retrieved_memories}"
                )
            except Exception as e:
                logger.error(f"[ContextBuilder] Failed to get embedding for query: {e}. Skipping retrieval.")
                    
        # 5. Limit context to max_tokens
        max_iterations = len(final_recent) + len(retrieved_memories) + 50
        iteration = 0
        prev_tokens = None
        
        while iteration < max_iterations:
            iteration += 1
            total_tokens = self._calculate_total_tokens(user_query, final_recent, retrieved_memories)
            if total_tokens <= self.max_tokens:
                break
            
            if prev_tokens is not None and total_tokens >= prev_tokens:
                break
            prev_tokens = total_tokens
                
            if retrieved_memories:
                retrieved_memories.pop()
                continue
                
            if len(final_recent) > 0:
                final_recent.pop(0) 
                continue
                
            break

        total_tokens = self._calculate_total_tokens(user_query, final_recent, retrieved_memories)
        
        return ContextBundle(
            user_query=user_query,
            recent_messages=final_recent,
            retrieved_memories=retrieved_memories,
            total_tokens_estimate=total_tokens,
            current_user_name=display_user_name,
            current_user_id=user_id,
            is_identity_query=False
        )

