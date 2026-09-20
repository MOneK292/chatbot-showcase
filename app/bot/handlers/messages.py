import logging
from typing import Optional
from aiogram import Router
from aiogram.types import Message as AiogramMessage
from app.database.session import AsyncSessionLocal
from app.services.messages import MessageService

logger = logging.getLogger(__name__)
router = Router()

import asyncio
import os
import time
from contextlib import suppress
from html import escape
from aiogram import Bot
from aiogram.enums import ChatAction
from datetime import datetime, timezone
import re

def format_gemini_to_html(text: str) -> str:
    # 1. Escape HTML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 2. Extract code blocks
    code_blocks = []
    def replace_code_block(match):
        code = match.group(1)
        code_blocks.append(f"<pre><code>{code}</code></pre>")
        return f"@@CODE_BLOCK_{len(code_blocks)-1}@@"
    text = re.sub(r'```(?:.*?)\n(.*?)```', replace_code_block, text, flags=re.DOTALL)
    # Also handle code blocks without newline
    text = re.sub(r'```(.*?)```', replace_code_block, text, flags=re.DOTALL)
    
    # 3. Extract inline code
    inline_codes = []
    def replace_inline_code(match):
        code = match.group(1)
        inline_codes.append(f"<code>{code}</code>")
        return f"@@INLINE_CODE_{len(inline_codes)-1}@@"
    text = re.sub(r'`(.*?)`', replace_inline_code, text)
    
    # 4. Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    
    # 5. Italic
    text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text, flags=re.DOTALL)
    text = re.sub(r'(?<!_)_(?!_)(.*?)(?<!_)_(?!_)', r'<i>\1</i>', text, flags=re.DOTALL)
    
    # 6. Links
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    
    # 7. Restore code
    for i, code in enumerate(inline_codes):
        text = text.replace(f"@@INLINE_CODE_{i}@@", code)
    for i, code in enumerate(code_blocks):
        text = text.replace(f"@@CODE_BLOCK_{i}@@", code)
        
    return text

from app.memory.context_builder import ContextBuilder
from app.memory.embedding_service import EmbeddingService, EmbeddingConfig
from app.ai.router import GeminiRouter
from app.ai.gemini_service import GeminiService
from app.bot.bot import bot_context

# Keep strong references to background tasks to prevent garbage collection
active_generations: set[asyncio.Task] = set()

async def typing_loop(bot: Bot, chat_id: int):
    """Cyclic typing indicator."""
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in typing loop: {e}")

async def process_ai_response(
    bot: Bot, 
    chat_id: int, 
    user_id: int, 
    text: str, 
    reply_to_message_id: int, 
    message_db_id: int,
    user_name: Optional[str] = None
):
    """Background task to generate and send AI response."""
    # Check LLM_ENABLED
    if os.getenv("LLM_ENABLED", "true").lower() != "true":
        logger.info("[AI] LLM is disabled. Skipping generation.")
        return

    typer_task = asyncio.create_task(typing_loop(bot, chat_id))
    
    try:
        logger.info(f"[AI] Starting generation for chat {chat_id}")
        async with AsyncSessionLocal() as session:
            emb_service = EmbeddingService(EmbeddingConfig())
            builder = ContextBuilder(session, emb_service)
            router = GeminiRouter()
            gemini = GeminiService()

            logger.info(f"[AI] Building context for chat {chat_id}")
            context = await builder.build_context(
                chat_id=chat_id, 
                user_query=text, 
                message_db_id=message_db_id,
                user_id=user_id,
                user_name=user_name
            )
            
            # Fast deterministic response for identity queries with ZERO saved facts
            if context.is_identity_query and not context.retrieved_memories:
                logger.info(f"[AI] Fast identity response (no personal memory) for user {user_id}")
                await bot.send_message(
                    chat_id=chat_id,
                    text="Я не знаю вашего имени и в моей памяти пока нет сохранённых фактов о вас.",
                    reply_to_message_id=reply_to_message_id
                )
                return

            logger.info(f"[AI] Routing decision for chat {chat_id}")
            decision = router.choose_model(text, context)
            
            logger.info(f"[AI] Calling Gemini generate for chat {chat_id}")
            response_text = await gemini.generate(session, chat_id, user_id, decision.model, context)
            logger.info(f"[AI] Generation finished for chat {chat_id}")
            
            if not response_text:
                response_text = "Сейчас я временно не могу сформировать ответ. Попробуйте позже."
            else:
                response_text = format_gemini_to_html(response_text)
            
            # Truncate to Telegram's 4096 character limit
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "..."
                
            await bot.send_message(chat_id=chat_id, text=response_text, reply_to_message_id=reply_to_message_id)
            logger.info(f"[AI] Message sent for chat {chat_id}")
            
    except asyncio.CancelledError:
        logger.info(f"[AI] Generation for chat {chat_id} was cancelled (deduplication).")
        raise
    except Exception as e:
        logger.error(f"[AI Error] Failed to generate response: {e}", exc_info=True)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="Сейчас я временно не могу сформировать ответ. Попробуйте позже.",
                reply_to_message_id=reply_to_message_id
            )
        except Exception as send_err:
            logger.error(f"Failed to send error message: {send_err}")
    finally:
        typer_task.cancel()
        with suppress(asyncio.CancelledError):
            await typer_task

async def process_media_intelligence_response(bot: Bot, chat_id: int, message: AiogramMessage, reply_msg: AiogramMessage, query_text: str):
    """Background task to transcribe and summarize media."""
    from app.services.media_intelligence import MediaIntelligenceService
    
    typer_task = asyncio.create_task(typing_loop(bot, chat_id))
    try:
        user_cmd = query_text.lower().strip()
        cmd_mode = "normal"
        if "кратко" in user_cmd:
            cmd_mode = "summary_only"
        elif "полный текст" in user_cmd:
            cmd_mode = "transcript_only"
        elif "задачи" in user_cmd:
            cmd_mode = "tasks_only"
            
        file_size = 0
        if reply_msg.voice:
            file_id = reply_msg.voice.file_id
            mime_type = reply_msg.voice.mime_type or "audio/ogg"
            file_size = reply_msg.voice.file_size
        elif reply_msg.audio:
            file_id = reply_msg.audio.file_id
            mime_type = reply_msg.audio.mime_type or "audio/mpeg"
            file_size = getattr(reply_msg.audio, "file_size", 0)
        elif reply_msg.video_note:
            file_id = reply_msg.video_note.file_id
            mime_type = "video/mp4"
            file_size = getattr(reply_msg.video_note, "file_size", 0)
        elif reply_msg.video:
            file_id = reply_msg.video.file_id
            mime_type = reply_msg.video.mime_type or "video/mp4"
            file_size = getattr(reply_msg.video, "file_size", 0)
        else:
            return

        service = MediaIntelligenceService()
        
        try:
            if cmd_mode == "normal":
                final_text = await service.process_media_single_shot(bot, file_id, mime_type, file_size)
            else:
                transcribe_result = await service.transcribe_media(bot, file_id, mime_type, file_size)
                transcription = transcribe_result["text"]
                
                summary = ""
                if cmd_mode == "summary_only":
                    summary = await service.summarize_transcript(transcription, mode="normal")
                elif cmd_mode == "tasks_only":
                    summary = await service.summarize_transcript(transcription, mode="tasks")
                    
                MAX_TRANSCRIPT_LEN = 3000
                if len(transcription) > MAX_TRANSCRIPT_LEN:
                    transcription = transcription[:MAX_TRANSCRIPT_LEN] + "\n[обрезано]"
                    
                display_transcript = escape(transcription.strip())
                
                if cmd_mode == "summary_only":
                    final_text = f"📌 Кратко\n\n{summary}"
                elif cmd_mode == "transcript_only":
                    final_text = f"📝 Расшифровка\n\n<blockquote expandable>{display_transcript}</blockquote>"
                elif cmd_mode == "tasks_only":
                    final_text = summary
        except ValueError as ve:
            await bot.send_message(chat_id=chat_id, text=f"❌ {ve}", reply_to_message_id=message.message_id)
            return
        except RuntimeError as re:
            await bot.send_message(chat_id=chat_id, text=f"❌ {re}", reply_to_message_id=message.message_id)
            return
            
        await bot.send_message(
            chat_id=chat_id,
            text=final_text,
            reply_to_message_id=message.message_id
        )
    except TimeoutError as te:
        logger.error(f"[MEDIA_ERROR] Timeout: {te}")
        try:
            await bot.send_message(chat_id=chat_id, text="❌ Превышено время ожидания ответа от модели.", reply_to_message_id=message.message_id)
        except:
            pass
    except Exception as e:
        logger.error(f"[MEDIA_ERROR] Failed to process media intelligence: {e}")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось обработать медиафайл.",
                reply_to_message_id=message.message_id
            )
        except:
            pass
    finally:
        typer_task.cancel()
        with suppress(asyncio.CancelledError):
            await typer_task

@router.message()
async def handle_incoming_message(message: AiogramMessage, bot: Bot):
    """Ingest-only handler for all incoming messages, plus triggering AI generation if needed."""
    try:
        async with AsyncSessionLocal() as session:
            service = MessageService(session)
            db_msg = await service.process_aiogram_message(message, is_edited=False)
            await session.commit()
            logger.info(
                f"[Ingest] Saved msg_id={message.message_id} chat_id={message.chat.id} db_id={db_msg.id}"
            )
    except Exception as e:
        logger.error(f"[Ingest Error] Failed to process message {message.message_id}: {e}", exc_info=True)
        return

    # Check if we should reply
    if message.from_user and message.from_user.is_bot:
        return
        
    text = message.text or message.caption
    if not text:
        return

    # Application-level limit on user query length for downstream AI pipeline.
    # The original message is already saved to DB above, this only affects LLM/embedding input.
    MAX_USER_MESSAGE_LENGTH = 4000
    if len(text) > MAX_USER_MESSAGE_LENGTH:
        logger.info(f"[AI] Truncating user message from {len(text)} to {MAX_USER_MESSAGE_LENGTH} chars for chat {message.chat.id}")
        text = text[:MAX_USER_MESSAGE_LENGTH]

    # Message age check
    age_seconds = (datetime.now(timezone.utc) - message.date).total_seconds()
    if age_seconds > 300:
        logger.info(f"Message {message.message_id} is too old ({age_seconds}s). Skipping AI.")
        return

    is_private = message.chat.type == "private"
    is_mention = bot_context.bot_username and f"@{bot_context.bot_username}" in text
    is_reply_to_bot = (
        message.reply_to_message and 
        message.reply_to_message.from_user and 
        message.reply_to_message.from_user.id == bot_context.bot_id
    )

    if is_private or is_mention or is_reply_to_bot:
        chat_id = message.chat.id
        
        if is_mention and message.reply_to_message:
            r_msg = message.reply_to_message
            if r_msg.voice or r_msg.audio or r_msg.video_note or r_msg.video:
                task = asyncio.create_task(process_media_intelligence_response(
                    bot=bot,
                    chat_id=chat_id,
                    message=message,
                    reply_msg=r_msg,
                    query_text=text
                ))
                active_generations.add(task)
                task.add_done_callback(active_generations.discard)
                return
            
        user_name = message.from_user.full_name if message.from_user else "Unknown"
        task = asyncio.create_task(process_ai_response(
            bot=bot,
            chat_id=chat_id,
            user_id=message.from_user.id,
            text=text,
            reply_to_message_id=message.message_id,
            message_db_id=db_msg.id,
            user_name=user_name
        ))
        active_generations.add(task)
        task.add_done_callback(active_generations.discard)

@router.edited_message()
async def handle_edited_message(message: AiogramMessage):
    """Ingest-only handler for edited messages."""
    try:
        async with AsyncSessionLocal() as session:
            service = MessageService(session)
            db_msg = await service.process_aiogram_message(message, is_edited=True)
            await session.commit()
            logger.info(
                f"[Ingest Edit] Updated msg_id={message.message_id} chat_id={message.chat.id} db_id={db_msg.id}"
            )
    except Exception as e:
        logger.error(f"[Ingest Edit Error] Failed to process edit {message.message_id}: {e}", exc_info=True)
