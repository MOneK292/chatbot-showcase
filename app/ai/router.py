from dataclasses import dataclass
from enum import Enum
from app.memory.context_builder import ContextBundle

import os

class GeminiModels(Enum):
    DEFAULT = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-lite")
    COMPLEX = os.getenv("GEMINI_MODEL_COMPLEX", "models/gemini-2.5-flash-lite")

@dataclass
class RoutingDecision:
    model: str
    reason: str

class GeminiRouter:
    def __init__(self):
        self.force_expensive = os.getenv("FORCE_EXPENSIVE_MODEL", "false").lower() == "true"

    def choose_model(self, query: str, context: ContextBundle) -> RoutingDecision:
        query_lower = query.lower()
        
        # If expensive model is not forced, always use efficient DEFAULT (Flash Lite)
        if not self.force_expensive and GeminiModels.COMPLEX.value == GeminiModels.DEFAULT.value:
            return RoutingDecision(
                model=GeminiModels.DEFAULT.value,
                reason="default_flash_lite"
            )
                
        # 1. Code blocks or explicit programming requests
        if "```" in query or query.count('\n') > 50:
            return RoutingDecision(
                model=GeminiModels.COMPLEX.value,
                reason="code_block_or_long_query"
            )

        # 2. Complex keywords (architecture, sql, refactoring, log analysis)
        complex_keywords = ("архитектур", "рефактор", "explain analyze", "dockerfile", "nginx config", "оптимизац")
        if any(kw in query_lower for kw in complex_keywords):
            return RoutingDecision(
                model=GeminiModels.COMPLEX.value,
                reason="complex_technical_keyword"
            )

        # 3. Query length
        if len(query) > 3000:
            return RoutingDecision(
                model=GeminiModels.COMPLEX.value,
                reason="query_length_exceeds_3000"
            )
            
        return RoutingDecision(
            model=GeminiModels.DEFAULT.value,
            reason="default_routing"
        )
