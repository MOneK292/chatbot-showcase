from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.message import Message

class MessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, chat_db_id: int, telegram_message_id: int) -> Optional[Message]:
        stmt = select(Message).where(
            Message.chat_id == chat_db_id,
            Message.telegram_message_id == telegram_message_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def resolve_pending_replies(self, chat_db_id: int, parent_telegram_id: int, parent_db_id: int) -> int:
        """Resolve any messages that were waiting for this parent message to arrive."""
        stmt = (
            update(Message)
            .where(
                Message.chat_id == chat_db_id,
                Message.telegram_reply_to_message_id == parent_telegram_id,
                Message.reply_to_message_id.is_(None)
            )
            .values(reply_to_message_id=parent_db_id, updated_at=datetime.now(timezone.utc))
        )
        res = await self.session.execute(stmt)
        return res.rowcount

    async def upsert_message(
        self,
        chat_db_id: int,
        telegram_message_id: int,
        user_db_id: Optional[int],
        date: datetime,
        text: Optional[str] = None,
        telegram_reply_to_message_id: Optional[int] = None,
        edited_at: Optional[datetime] = None,
        message_type: str = "text",
        is_forward: bool = False,
        is_edited: bool = False,
        needs_embedding: bool = False,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        now = datetime.now(timezone.utc)
        
        # Check if parent message exists in DB to resolve reply_to_message_id
        reply_to_message_id: Optional[int] = None
        if telegram_reply_to_message_id is not None:
            parent = await self.get_by_telegram_id(chat_db_id, telegram_reply_to_message_id)
            if parent:
                reply_to_message_id = parent.id

        existing = await self.get_by_telegram_id(chat_db_id, telegram_message_id)
        if existing:
            # Update existing message (e.g. edit)
            existing.text = text if text is not None else existing.text
            existing.edited_at = edited_at or (now if is_edited else existing.edited_at)
            existing.is_edited = is_edited or existing.is_edited
            existing.needs_embedding = needs_embedding or existing.needs_embedding
            existing.message_type = message_type
            existing.is_forward = is_forward
            if raw_metadata is not None:
                existing.raw_metadata = raw_metadata
            if telegram_reply_to_message_id is not None:
                existing.telegram_reply_to_message_id = telegram_reply_to_message_id
            if reply_to_message_id is not None:
                existing.reply_to_message_id = reply_to_message_id
            existing.updated_at = now
            msg = existing
        else:
            msg = Message(
                telegram_message_id=telegram_message_id,
                chat_id=chat_db_id,
                user_id=user_db_id,
                telegram_reply_to_message_id=telegram_reply_to_message_id,
                reply_to_message_id=reply_to_message_id,
                text=text,
                date=date,
                edited_at=edited_at,
                message_type=message_type,
                is_forward=is_forward,
                is_edited=is_edited,
                needs_embedding=needs_embedding,
                raw_metadata=raw_metadata,
                created_at=now,
                updated_at=now,
            )
            self.session.add(msg)

        await self.session.flush()

        # Perform deferred resolution for any children messages that were waiting for this message
        await self.resolve_pending_replies(chat_db_id, telegram_message_id, msg.id)

        return msg

    async def get_reply_chain(self, message_db_id: int, max_depth: int = 10) -> List[Message]:
        """Fetch the recursive reply chain for a given message up to max_depth."""
        from sqlalchemy import literal_column
        from sqlalchemy.orm import selectinload, aliased
        
        # Base case: the target message (depth = 0)
        base_stmt = (
            select(Message.id, Message.reply_to_message_id, literal_column("0").label("depth"))
            .where(Message.id == message_db_id)
            .cte(name="reply_tree", recursive=True)
        )
        
        # Recursive case: parents of the messages in reply_tree
        m = aliased(Message)
        recursive_stmt = (
            select(m.id, m.reply_to_message_id, (base_stmt.c.depth + 1).label("depth"))
            .join(base_stmt, base_stmt.c.reply_to_message_id == m.id)
            .where(base_stmt.c.depth < max_depth)
        )
        
        cte = base_stmt.union_all(recursive_stmt)
        
        # Final query: fetch the messages in chronological order
        stmt = (
            select(Message)
            .where(Message.id.in_(select(cte.c.id)))
            .order_by(Message.date.asc())
            .options(selectinload(Message.user))
        )
        
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_recent_messages(self, chat_db_id: int, limit: int = 15) -> List[Message]:
        from sqlalchemy.orm import selectinload
        stmt = (
            select(Message)
            .where(Message.chat_id == chat_db_id)
            .order_by(Message.date.desc())
            .limit(limit)
            .options(selectinload(Message.user))
        )
        res = await self.session.execute(stmt)
        messages = res.scalars().all()
        # They come back latest first, we want chronological order
        return list(reversed(messages))
