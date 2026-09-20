from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.chat import Chat
from app.database.models.chat_member import ChatMember

class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_chat_id(self, telegram_chat_id: int) -> Optional[Chat]:
        stmt = select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_chat(
        self,
        telegram_chat_id: int,
        chat_type: str,
        title: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Chat:
        chat = await self.get_by_telegram_chat_id(telegram_chat_id)
        now = datetime.now(timezone.utc)
        if chat:
            chat.type = chat_type
            chat.title = title
            chat.username = username
            chat.updated_at = now
        else:
            chat = Chat(
                telegram_chat_id=telegram_chat_id,
                type=chat_type,
                title=title,
                username=username,
                created_at=now,
                updated_at=now,
            )
            self.session.add(chat)
        await self.session.flush()
        return chat

    async def update_member(self, chat_db_id: int, user_db_id: int) -> ChatMember:
        stmt = select(ChatMember).where(
            ChatMember.chat_id == chat_db_id,
            ChatMember.user_id == user_db_id
        )
        res = await self.session.execute(stmt)
        member = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if member:
            member.last_seen_at = now
            member.updated_at = now
        else:
            member = ChatMember(
                chat_id=chat_db_id,
                user_id=user_db_id,
                joined_at=now,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
            self.session.add(member)
        await self.session.flush()
        return member
