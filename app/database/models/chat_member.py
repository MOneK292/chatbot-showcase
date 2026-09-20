from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import BigInteger, Integer, ForeignKey, UniqueConstraint, DateTime, Identity
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, TimestampMixin, utc_now

class ChatMember(Base, TimestampMixin):
    __tablename__ = "chat_members"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_members_chat_user"),
    )

    def __repr__(self) -> str:
        return f"<ChatMember(chat_id={self.chat_id}, user_id={self.user_id})>"
