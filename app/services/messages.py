from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import Message as AiogramMessage

from app.database.repositories.user_repository import UserRepository
from app.database.repositories.chat_repository import ChatRepository
from app.database.repositories.message_repository import MessageRepository
from app.database.models.message import Message

@dataclass
class NormalizedMessage:
    telegram_message_id: int
    telegram_chat_id: int
    chat_type: str
    date: datetime
    telegram_user_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_bot: bool = False
    chat_title: Optional[str] = None
    chat_username: Optional[str] = None
    text: Optional[str] = None
    telegram_reply_to_message_id: Optional[int] = None
    edited_at: Optional[datetime] = None
    message_type: str = "text"
    is_forward: bool = False
    is_edited: bool = False
    raw_metadata: Optional[Dict[str, Any]] = None

class MessageService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.chat_repo = ChatRepository(session)
        self.msg_repo = MessageRepository(session)

    @staticmethod
    def detect_message_type(msg: AiogramMessage) -> str:
        if msg.text:
            return "text"
        elif msg.photo:
            return "photo"
        elif msg.video:
            return "video"
        elif msg.document:
            return "document"
        elif msg.audio:
            return "audio"
        elif msg.voice:
            return "voice"
        elif msg.sticker:
            return "sticker"
        elif msg.animation:
            return "animation"
        elif msg.location:
            return "location"
        elif msg.contact:
            return "contact"
        elif msg.poll:
            return "poll"
        return "other"

    @classmethod
    def from_aiogram_message(cls, msg: AiogramMessage, is_edited: bool = False) -> NormalizedMessage:
        user = msg.from_user
        reply_to_id = None
        if msg.reply_to_message:
            reply_to_id = msg.reply_to_message.message_id

        text = msg.text or msg.caption or ""
        
        edited_at = None
        if is_edited and getattr(msg, "edit_date", None) is not None:
            if isinstance(msg.edit_date, datetime):
                edited_at = msg.edit_date
            else:
                edited_at = datetime.fromtimestamp(msg.edit_date, tz=timezone.utc)

        return NormalizedMessage(
            telegram_message_id=msg.message_id,
            telegram_chat_id=msg.chat.id,
            chat_type=msg.chat.type,
            date=msg.date if isinstance(msg.date, datetime) else datetime.fromtimestamp(msg.date, tz=timezone.utc),
            telegram_user_id=user.id if user else None,
            username=user.username if user else None,
            first_name=user.first_name if user else None,
            last_name=user.last_name if user else None,
            is_bot=user.is_bot if user else False,
            chat_title=msg.chat.title,
            chat_username=msg.chat.username,
            text=text,
            telegram_reply_to_message_id=reply_to_id,
            edited_at=edited_at,
            message_type=cls.detect_message_type(msg),
            is_forward=msg.forward_date is not None or msg.forward_from is not None or msg.forward_from_chat is not None,
            is_edited=is_edited,
            raw_metadata=cls._extract_raw_metadata(msg)
        )

    @staticmethod
    def _extract_raw_metadata(msg: AiogramMessage) -> dict:
        meta = {"message_id": msg.message_id, "chat_id": msg.chat.id}
        
        is_fwd = msg.forward_date is not None or msg.forward_from is not None or msg.forward_from_chat is not None
        if is_fwd:
            meta["forward_date"] = msg.forward_date.isoformat() if isinstance(msg.forward_date, datetime) else str(msg.forward_date)
            if msg.forward_from:
                meta["forward_origin"] = msg.forward_from.first_name
                meta["forward_type"] = "user"
                meta["forward_sender_name"] = msg.forward_from.full_name
                meta["forward_user_id"] = msg.forward_from.id
            elif msg.forward_from_chat:
                meta["forward_origin"] = msg.forward_from_chat.title
                meta["forward_type"] = "chat"
                meta["forward_chat_id"] = msg.forward_from_chat.id
            elif msg.forward_sender_name:
                meta["forward_origin"] = msg.forward_sender_name
                meta["forward_type"] = "hidden_user"
                meta["forward_sender_name"] = msg.forward_sender_name
                
        return meta

    async def save_normalized_message(self, norm: NormalizedMessage) -> Message:
        # 1. Resolve / Upsert Chat
        chat = await self.chat_repo.upsert_chat(
            telegram_chat_id=norm.telegram_chat_id,
            chat_type=norm.chat_type,
            title=norm.chat_title,
            username=norm.chat_username,
        )

        # 2. Resolve / Upsert User (if available)
        user_db_id: Optional[int] = None
        if norm.telegram_user_id is not None:
            user = await self.user_repo.upsert_user(
                telegram_id=norm.telegram_user_id,
                username=norm.username,
                first_name=norm.first_name,
                last_name=norm.last_name,
                is_bot=norm.is_bot,
            )
            user_db_id = user.id
            # Update ChatMember relationship
            await self.chat_repo.update_member(chat_db_id=chat.id, user_db_id=user.id)

        # 3. Smart Pre-filter & Deduplication for Memory (EmbeddingJob)
        text_len = len(norm.text.strip()) if norm.text else 0
        needs_embedding = False
        
        if norm.text and 10 <= text_len <= 8000:
            cleaned_text = norm.text.strip().lower()
            
            STOP_WORDS = {
                "ок", "да", "нет", "ага", "привет", "хай", "спасибо", "спс", "ясно",
                "понял", "лол", "кек", "лад", "ладно", "пока", "доброе утро", "добрый день",
                "спокойной ночи", "👍", "😂", "🔥", "🤝", "👌", "😊", "❤️", "норм", "круто"
            }
            QUESTION_STARTS = ("как", "где", "когда", "почему", "зачем", "что", "кто", "сколько", "какой", "какая", "какие", "куда", "откуда", "чей", "подскажи", "расскажи")
            FACT_MARKERS = ("меня зовут", "я живу", "мой сервер", "я работаю", "мой стек", "мой номер", "мой email", "я родился", "я учусь", "я использую", "мне нравится", "я люблю", "мой проект")
            
            has_fact_marker = any(m in cleaned_text for m in FACT_MARKERS)
            is_stop_word = cleaned_text in STOP_WORDS
            is_question = cleaned_text.endswith("?") or cleaned_text.startswith(QUESTION_STARTS)
            is_too_short = text_len < 20
            
            if not is_stop_word and (has_fact_marker or (not is_question and not is_too_short)):
                needs_embedding = True
        
        # Deduplication: check if identical to the user's previous message
        if needs_embedding and user_db_id is not None:
            from sqlalchemy import select
            stmt_prev = (
                select(Message.text)
                .where(Message.chat_id == chat.id, Message.user_id == user_db_id)
                .order_by(Message.date.desc())
                .limit(1)
            )
            prev_text = (await self.session.execute(stmt_prev)).scalar_one_or_none()
            if prev_text and prev_text.strip().lower() == norm.text.strip().lower():
                needs_embedding = False
        
        db_message = await self.msg_repo.upsert_message(
            chat_db_id=chat.id,
            telegram_message_id=norm.telegram_message_id,
            user_db_id=user_db_id,
            date=norm.date,
            text=norm.text,
            telegram_reply_to_message_id=norm.telegram_reply_to_message_id,
            edited_at=norm.edited_at,
            message_type=norm.message_type,
            is_forward=norm.is_forward,
            is_edited=norm.is_edited,
            needs_embedding=needs_embedding,
            raw_metadata=norm.raw_metadata,
        )
        
        # 4. Security Check & Create EmbeddingJob if needed
        if needs_embedding:
            from app.memory.security import is_prompt_injection
            import logging
            
            is_injection, category = is_prompt_injection(norm.text)
            if is_injection:
                # Log and drop the embedding task
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"[MEMORY_SECURITY] prompt_injection_detected "
                    f"message_id={db_message.id} "
                    f"user_id={user_db_id} "
                    f"length={text_len} "
                    f"reason={category}"
                )
                needs_embedding = False

        if needs_embedding:
            from app.database.models.embedding_job import EmbeddingJob
            from sqlalchemy import select
            
            # Check if pending job already exists (to prevent duplicates on edits before processing)
            stmt = select(EmbeddingJob).where(
                EmbeddingJob.source_type == 'message',
                EmbeddingJob.source_id == db_message.id,
                EmbeddingJob.status.in_(['pending', 'processing', 'failed'])
            )
            existing_job = (await self.session.execute(stmt)).scalar_one_or_none()
            
            if not existing_job:
                job = EmbeddingJob(
                    source_type='message',
                    source_id=db_message.id,
                    status='pending'
                )
                self.session.add(job)
                
        return db_message

    async def process_aiogram_message(self, msg: AiogramMessage, is_edited: bool = False) -> Message:
        norm = self.from_aiogram_message(msg, is_edited=is_edited)
        return await self.save_normalized_message(norm)
