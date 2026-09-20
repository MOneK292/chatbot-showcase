import os
import logging
from aiogram import Router, F
from aiogram.types import Message as AiogramMessage
from aiogram.filters import Command
from sqlalchemy import select, func, text
from datetime import datetime, timedelta, timezone

from app.database.session import AsyncSessionLocal
from app.database.models.llm_log import LlmLog
from app.memory.embedding_service import EmbeddingService, EmbeddingConfig
from app.memory.vector_store import NumpyVectorStore

logger = logging.getLogger(__name__)
router = Router()

def is_admin(user_id: int) -> bool:
    admin_id_str = os.getenv("ADMIN_ID")
    if not admin_id_str:
        return False
    try:
        return user_id == int(admin_id_str)
    except ValueError:
        return False

@router.message(Command("stats"))
async def cmd_stats(message: AiogramMessage):
    if not message.from_user or not is_admin(message.from_user.id):
        return
        
    async with AsyncSessionLocal() as session:
        stmt = select(
            func.count(LlmLog.id).label("total_requests"),
            func.sum(LlmLog.prompt_tokens).label("total_prompt"),
            func.sum(LlmLog.completion_tokens).label("total_completion"),
            func.sum(LlmLog.cost_usd).label("total_cost")
        )
        result = await session.execute(stmt)
        row = result.first()
        
        if not row or not row.total_requests:
            await message.reply("No LLM usage data available.")
            return
            
        text_resp = (
            f"📊 <b>LLM Usage Stats</b>\n"
            f"Total Requests: {row.total_requests}\n"
            f"Prompt Tokens: {row.total_prompt or 0:,}\n"
            f"Completion Tokens: {row.total_completion or 0:,}\n"
            f"Total Cost: ${row.total_cost or 0:.4f}"
        )
        await message.reply(text_resp)

@router.message(Command("cost"))
async def cmd_cost(message: AiogramMessage):
    if not message.from_user or not is_admin(message.from_user.id):
        return
        
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    async with AsyncSessionLocal() as session:
        # Daily breakdown by model
        stmt_daily = select(
            LlmLog.model,
            func.sum(LlmLog.cost_usd).label("cost")
        ).where(LlmLog.created_at >= today_start).group_by(LlmLog.model)
        
        # Monthly breakdown by model
        stmt_monthly = select(
            LlmLog.model,
            func.sum(LlmLog.cost_usd).label("cost")
        ).where(LlmLog.created_at >= month_start).group_by(LlmLog.model)
        
        daily_res = await session.execute(stmt_daily)
        monthly_res = await session.execute(stmt_monthly)
        
        text_resp = "💸 <b>Cost Breakdown</b>\n\n<b>Today:</b>\n"
        daily_total = 0.0
        for model, cost in daily_res:
            cost = cost or 0
            daily_total += cost
            text_resp += f"- {model}: ${cost:.4f}\n"
        text_resp += f"Total Today: ${daily_total:.4f}\n\n"
        
        text_resp += "<b>This Month:</b>\n"
        monthly_total = 0.0
        for model, cost in monthly_res:
            cost = cost or 0
            monthly_total += cost
            text_resp += f"- {model}: ${cost:.4f}\n"
        text_resp += f"Total Month: ${monthly_total:.4f}"
        
        await message.reply(text_resp)

@router.message(Command("memory"))
async def cmd_memory(message: AiogramMessage):
    if not message.from_user or not is_admin(message.from_user.id):
        return
        
    if os.getenv("ENABLE_MEMORY_DEBUG", "false").lower() != "true":
        await message.reply("Memory debug is disabled.")
        return
        
    query = message.text[len("/memory"):].strip()
    if not query:
        await message.reply("Please provide a query. Usage: /memory <query>")
        return
        
    await message.reply(f"Searching memory for: '{query}'...")
    
    try:
        async with AsyncSessionLocal() as session:
            emb_service = EmbeddingService(EmbeddingConfig())
            vector_store = NumpyVectorStore(session)
            
            emb_res = await emb_service.get_embedding(query)
            # search_similar with chat_id=None searches globally
            results = await vector_store.search_similar(None, emb_res.embedding, top_k=5)
            
            if not results:
                await message.reply("No memories found.")
                return
                
            resp = "🧠 <b>Memory Debug Results</b>\n\n"
            for r in results:
                score = r['score']
                text_chunk = r['text']
                chat_id = r.get('chat_id', 'Unknown')
                if len(text_chunk) > 200:
                    text_chunk = text_chunk[:197] + "..."
                resp += f"<b>Score:</b> {score:.2f} | <b>Chat ID:</b> {chat_id}\n{text_chunk}\n\n"
                
            await message.reply(resp)
    except Exception as e:
        logger.error(f"Error in /memory command: {e}", exc_info=True)
        await message.reply(f"An error occurred: {e}")
