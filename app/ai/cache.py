import time
import hashlib
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class ResponseCache:
    """In-memory TTL cache for frequent/identical LLM queries."""
    def __init__(self, default_ttl_seconds: int = 900, max_size: int = 1000): # 15 minutes default
        self.default_ttl = default_ttl_seconds
        self.max_size = max_size
        # key -> (response_text, expires_at)
        self._cache: Dict[str, Tuple[str, float]] = {}

    @staticmethod
    def _make_key(query: str, has_context: bool) -> str:
        # Only cache when query is sufficiently generic or normalized
        normalized = query.strip().lower()
        key_str = f"ctx:{has_context}|q:{normalized}"
        return hashlib.sha256(key_str.encode('utf-8')).hexdigest()

    def get(self, query: str, has_context: bool = False) -> Optional[str]:
        # Do not cache long or multi-line questions
        if len(query.strip()) > 300:
            return None

        key = self._make_key(query, has_context)
        entry = self._cache.get(key)
        if not entry:
            return None

        response_text, expires_at = entry
        if time.time() > expires_at:
            self._cache.pop(key, None)
            return None

        logger.info(f"[LLM_CACHE_HIT] query_len={len(query)}")
        return response_text

    def set(self, query: str, response_text: str, has_context: bool = False, ttl_seconds: Optional[int] = None) -> None:
        if len(query.strip()) > 300 or len(response_text) < 5:
            return

        # Simple size eviction
        if len(self._cache) >= self.max_size:
            now = time.time()
            expired = [k for k, v in self._cache.items() if now > v[1]]
            for k in expired:
                self._cache.pop(k, None)
            if len(self._cache) >= self.max_size:
                # Evict oldest entry
                oldest_k = next(iter(self._cache))
                self._cache.pop(oldest_k, None)

        key = self._make_key(query, has_context)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        self._cache[key] = (response_text, time.time() + ttl)

# Global singleton
response_cache = ResponseCache()
