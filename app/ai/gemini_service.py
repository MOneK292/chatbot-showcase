import logging
import json
import asyncio
from typing import Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.memory.context_builder import ContextBundle
from app.ai.prompt_builder import PromptBuilder
from app.ai.router import GeminiModels

import os
import time
from sqlalchemy.ext.asyncio import AsyncSession
from app.ai.token_guard import TokenGuard
from app.ai.cache import response_cache
from app.utils.warp import rotate_warp_proxy, is_geo_blocked_error

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self, api_key: Optional[str] = None):
        # By default, google-genai reads GEMINI_API_KEY from environment
        self.client = genai.Client(api_key=api_key)
        self.prompt_builder = PromptBuilder()
        self.token_guard = TokenGuard()

    async def generate(self, session: AsyncSession, chat_id: int, user_id: int, model: str, context: ContextBundle) -> Optional[str]:
        llm_enabled = os.getenv("LLM_ENABLED", "true").lower() == "true"
        if not llm_enabled:
            logger.info("LLM is disabled via LLM_ENABLED=false. Skipping generation.")
            return None
            
        if not self.token_guard.check_rate_limit(chat_id, user_id):
            return "Извините, вы превысили лимит запросов. Попробуйте позже."
            
        # Check cache
        has_heavy_context = bool(context.recent_messages or context.retrieved_memories)
        cached_resp = response_cache.get(context.user_query, has_context=has_heavy_context)
        if cached_resp:
            return cached_resp
            
        payload = self.prompt_builder.build_prompt(context)
        
        logger.info(
            f"[PROMPT_DEBUG]\n"
            f"=== SYSTEM PROMPT ===\n{payload.system_prompt}\n"
            f"=== USER PROMPT ===\n{payload.user_prompt}"
        )
        
        start_time = time.time()
        success = False
        error_type = None
        response_text = "Извините, сервис временно недоступен."
        final_model = model
        
        # We don't have exact token counts back from this simple API call yet,
        # so we will use the prompt builder's estimate for prompt, and estimate the response
        prompt_tokens = payload.token_estimate
        completion_tokens = 0
        
        try:
            response_text = await self._call_model(model, payload)
            completion_tokens = len(response_text) // 4
            success = True
            response_cache.set(context.user_query, response_text, has_context=has_heavy_context)
        except Exception as e:
            e_str = str(e)
            status_code = getattr(e, "code", None) or getattr(e, "status_code", None) or 500
            error_type = f"Error_{status_code}"
            
            is_exhausted = status_code in [429, 404, 500, 503] or "429" in e_str or "RESOURCE_EXHAUSTED" in e_str or "404" in e_str or "NOT_FOUND" in e_str
            
            if is_exhausted:
                logger.warning(f"[GeminiFallback] Primary model exhausted: {model}")
                
                fallback_models = []
                f1 = os.getenv("GEMINI_MODEL_FALLBACK_1")
                if f1: fallback_models.append(f1)
                f2 = os.getenv("GEMINI_MODEL_FALLBACK_2")
                if f2: fallback_models.append(f2)
                
                # Preserve legacy behavior
                if model == GeminiModels.COMPLEX.value and GeminiModels.DEFAULT.value not in fallback_models:
                    fallback_models.append(GeminiModels.DEFAULT.value)
                    
                for fallback_model in fallback_models:
                    if fallback_model == model:
                        continue
                    logger.warning(f"[GeminiFallback] Switching to: {fallback_model}")
                    try:
                        response_text = await self._call_model(fallback_model, payload)
                        final_model = fallback_model
                        completion_tokens = len(response_text) // 4
                        success = True
                        error_type = f"Fallback_Success_After_{status_code}"
                        break
                    except Exception as inner_e:
                        logger.error(f"[GeminiFallback] Fallback ({fallback_model}) failed: {inner_e}")
                        error_type = f"Fallback_Failed"
                
                if not success:
                    logger.error("All fallback models failed.")
            else:
                logger.error(f"Gemini API Error: {e}", exc_info=True)
                error_type = e.__class__.__name__
            
        latency_ms = int((time.time() - start_time) * 1000)
        
        await self.token_guard.log_request(
            session=session,
            chat_id=chat_id,
            user_id=user_id,
            model=final_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            success=success,
            error_type=error_type
        )
        
        return response_text if success else "Извините, сервис временно недоступен."
            
    async def _call_model(self, model: str, payload, retry_on_geo: bool = True) -> str:
        try:
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=payload.user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=payload.system_prompt
                )
            )
            return response.text
        except Exception as e:
            if retry_on_geo and is_geo_blocked_error(e):
                logger.warning(f"[WARP] Gemini geo-block detected in _call_model: {e}. Rotating WARP and retrying...")
                rotated = await rotate_warp_proxy()
                if rotated:
                    return await self._call_model(model, payload, retry_on_geo=False)
            raise
