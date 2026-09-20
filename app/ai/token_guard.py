import os
import time
import logging
import asyncio
from typing import Dict, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.llm_log import LlmLog

logger = logging.getLogger(__name__)

class TokenGuard:
    def __init__(self):
        self.max_rpm_chat = int(os.getenv("MAX_REQUESTS_PER_MINUTE_PER_CHAT", "20"))
        self.max_rpm_user = int(os.getenv("MAX_REQUESTS_PER_MINUTE_PER_USER", "10"))
        
        # Simple in-memory rate limiting for this MVP.
        # In a real distributed setup, we would use Redis for this.
        self._user_requests: Dict[int, list[float]] = {}
        self._chat_requests: Dict[int, list[float]] = {}
        
    def check_rate_limit(self, chat_id: int, user_id: int) -> bool:
        now = time.time()
        one_min_ago = now - 60
        
        # Cleanup old entries and check User limit
        if user_id not in self._user_requests:
            self._user_requests[user_id] = []
        self._user_requests[user_id] = [t for t in self._user_requests[user_id] if t > one_min_ago]
        
        if len(self._user_requests[user_id]) >= self.max_rpm_user:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return False
            
        # Cleanup old entries and check Chat limit
        if chat_id not in self._chat_requests:
            self._chat_requests[chat_id] = []
        self._chat_requests[chat_id] = [t for t in self._chat_requests[chat_id] if t > one_min_ago]
        
        if len(self._chat_requests[chat_id]) >= self.max_rpm_chat:
            logger.warning(f"Rate limit exceeded for chat {chat_id}")
            return False
            
        # Register request
        self._user_requests[user_id].append(now)
        self._chat_requests[chat_id].append(now)
        
        return True

    async def log_request(
        self, 
        session: AsyncSession, 
        chat_id: int, 
        user_id: int, 
        model: str, 
        prompt_tokens: int, 
        completion_tokens: int, 
        latency_ms: int,
        success: bool,
        error_type: str = None,
        request_type: str = "chat"
    ) -> None:
        
        # Calculate approximate cost
        cost_usd = 0.0
        if "lite" in model.lower():
            cost_usd = (prompt_tokens / 1_000_000 * 0.075) + (completion_tokens / 1_000_000 * 0.30)
        else:
            cost_usd = (prompt_tokens / 1_000_000 * 0.35) + (completion_tokens / 1_000_000 * 1.05)
            
        llm_log = LlmLog(
            chat_id=chat_id,
            user_id=user_id,
            model=model,
            request_type=request_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=success,
            error_type=error_type
        )
        
        session.add(llm_log)
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to save LLM Log: {e}")
