from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.user import User

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        is_bot: bool = False,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        now = datetime.now(timezone.utc)
        if user:
            # Update user profile info if changed
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.is_bot = is_bot
            user.updated_at = now
        else:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_bot=is_bot,
                created_at=now,
                updated_at=now,
            )
            self.session.add(user)
        await self.session.flush()
        return user
