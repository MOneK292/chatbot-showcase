import hashlib
import logging
from typing import List
from google import genai
from pydantic_settings import BaseSettings
from app.utils.warp import rotate_warp_proxy, is_geo_blocked_error

logger = logging.getLogger(__name__)

class EmbeddingConfig(BaseSettings):
    GEMINI_API_KEY: str
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"

    class Config:
        env_file = ".env"
        extra = "ignore"

class EmbeddingResult:
    def __init__(self, text: str, embedding: List[float], model: str, hash_val: str):
        self.text = text
        self.embedding = embedding
        self.model = model
        self.hash_val = hash_val

class EmbeddingService:
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model = config.GEMINI_EMBEDDING_MODEL

    @staticmethod
    def compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    async def get_embedding(self, text: str, retry_on_geo: bool = True) -> EmbeddingResult:
        """Fetch embedding from Gemini."""
        if not text.strip():
            raise ValueError("Text cannot be empty")
            
        logger.debug(f"Fetching embedding for text (length: {len(text)})")
        
        try:
            response = await self.client.aio.models.embed_content(
                model=self.model,
                contents=text
            )
            
            if not response.embeddings or not response.embeddings[0].values:
                raise RuntimeError("Received empty embedding from Gemini")
                
            vector = response.embeddings[0].values
            hash_val = self.compute_hash(text)
            
            return EmbeddingResult(
                text=text, 
                embedding=vector, 
                model=self.model, 
                hash_val=hash_val
            )
        except Exception as e:
            if retry_on_geo and is_geo_blocked_error(e):
                logger.warning(f"[WARP] Gemini geo-block in get_embedding: {e}. Rotating WARP and retrying...")
                rotated = await rotate_warp_proxy()
                if rotated:
                    return await self.get_embedding(text, retry_on_geo=False)
            raise

    async def extract_fact(self, text: str, retry_on_geo: bool = True):
        """Shadow mode: Extract long-term fact or return NO_MEMORY."""
        prompt = f"""
Ты должен извлечь долговременные факты о пользователе из его сообщения.
ПРАВИЛА:
1. Если сообщение содержит долговременную информацию о пользователе (имя, город, профессия, технологии, версии, хобби, серверы, проекты и т.д.), верни её как утверждение от 3-го лица: "Пользователь...".
2. НЕ ТЕРЯЙ ДЕТАЛИ. Сохраняй конкретные версии (Python 3.12), названия ПО (VS Code), должности, города, серверы.
3. Не придумывай ничего, чего нет в тексте.
4. Запрещено обобщать (например, писать "занимается программированием" вместо конкретных языков/программ).
5. Если сообщение - это вопрос, мат, шутка, или не содержит долгосрочных фактов, верни ровно одно слово: NO_MEMORY.

Текст сообщения:
{text}

Результат:
"""
        import time
        import os
        start = time.time()
        model_name = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-lite")
        try:
            res = await self.client.aio.models.generate_content(
                model=model_name,
                contents=prompt
            )
            latency = (time.time() - start) * 1000
            extracted = res.text.strip()
            if extracted.upper() in ["NULL", "NO MEMORY", "NO_MEMORY", "NO_MEMORY."]:
                extracted = "NO_MEMORY"
                
            in_tokens = res.usage_metadata.prompt_token_count if res.usage_metadata else 0
            out_tokens = res.usage_metadata.candidates_token_count if res.usage_metadata else 0
            
            return {
                "classification": "FACT" if extracted != "NO_MEMORY" else "NO_MEMORY",
                "extracted": extracted,
                "latency_ms": int(latency),
                "input_tokens": in_tokens,
                "output_tokens": out_tokens
            }
        except Exception as e:
            if retry_on_geo and is_geo_blocked_error(e):
                logger.warning(f"[WARP] Gemini geo-block in extract_fact: {e}. Rotating WARP and retrying...")
                rotated = await rotate_warp_proxy()
                if rotated:
                    return await self.extract_fact(text, retry_on_geo=False)
            raise

