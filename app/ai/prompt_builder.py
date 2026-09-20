from dataclasses import dataclass
from typing import Optional
from app.memory.context_builder import ContextBundle

@dataclass
class PromptPayload:
    system_prompt: str
    user_prompt: str
    token_estimate: int

class PromptBuilder:
    def __init__(self):
        self.base_system_prompt = (
            "You are a helpful, intelligent AI assistant in a Telegram group chat.\n"
            "CRITICAL IDENTITY AND ATTRIBUTION RULES:\n"
            "1. The current user asking the question is explicitly specified in the '=== CURRENT SPEAKER ===' section.\n"
            "2. In group chats, messages from other users are provided ONLY for conversational context in '=== SHORT TERM MEMORY ==='. NEVER confuse the current speaker with other group members, reply quote authors, or forwarded authors.\n"
            "3. If the user asks about their identity, name, or what you know about them (e.g., 'Кто я?', 'Как меня зовут?', 'Помнишь меня?'):\n"
            "   - Use ONLY facts explicitly provided in '=== LONG TERM MEMORY (Personal) ===' or their display name in '=== CURRENT SPEAKER ==='.\n"
            "   - If no personal fact or name exists in memory for this user, respond strictly: 'Я не знаю вашего имени и в моей памяти пока нет сохранённых фактов о вас.'\n"
            "   - NEVER guess, assume, or adopt names from other users in the chat history.\n"
            "Always be polite, concise, and helpful."
        )

    def build_prompt(self, context: ContextBundle) -> PromptPayload:
        system_prompt = self.base_system_prompt
        user_prompt_parts = []
        
        # Add Short-term Memory (Recent Messages) ONLY if not an identity query
        if context.recent_messages:
            user_prompt_parts.append("=== SHORT TERM MEMORY (Group Context) ===")
            user_prompt_parts.append("\n".join(context.recent_messages))
            user_prompt_parts.append("")
            
        # Add Long-term Memory (Personal memories of THIS user only)
        if context.retrieved_memories:
            user_prompt_parts.append(f"=== LONG TERM MEMORY (Personal for {context.current_user_name}) ===")
            user_prompt_parts.append("\n".join(context.retrieved_memories))
            user_prompt_parts.append("")
            
        # Add Current Speaker and User Query
        user_prompt_parts.append("=== CURRENT SPEAKER ===")
        user_id_str = f" (User ID: {context.current_user_id})" if context.current_user_id else ""
        user_prompt_parts.append(f"Author: {context.current_user_name}{user_id_str}")
        user_prompt_parts.append(f"Query: {context.user_query}")
        
        user_prompt = "\n".join(user_prompt_parts)
        
        total_chars = len(system_prompt) + len(user_prompt)
        token_estimate = total_chars // 4
        
        return PromptPayload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            token_estimate=token_estimate
        )

