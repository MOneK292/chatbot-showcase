from typing import Optional
from sqlalchemy import BigInteger, Integer, String, Identity
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, TimestampMixin

class Chat(Base, TimestampMixin):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)  # private, group, supergroup, channel
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, telegram_chat_id={self.telegram_chat_id}, type={self.type}, title={self.title})>"
