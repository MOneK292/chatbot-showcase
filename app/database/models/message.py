from datetime import datetime
from typing import Optional, Any, Dict
from sqlalchemy import BigInteger, Integer, String, Boolean, ForeignKey, UniqueConstraint, DateTime, Text, Index, JSON, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.models.base import Base, TimestampMixin

class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user: Mapped[Optional["User"]] = relationship("User")
    
    # External Telegram Message ID of the message being replied to
    telegram_reply_to_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    
    # Internal FK referencing messages.id when resolved
    reply_to_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)

    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    message_type: Mapped[str] = mapped_column(String(64), default="text", nullable=False)
    is_forward: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_embedding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    raw_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("chat_id", "telegram_message_id", name="uq_messages_chat_telegram_msg"),
        Index("ix_messages_chat_date", "chat_id", "date"),
        Index("ix_messages_user_date", "user_id", "date"),
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, tg_msg_id={self.telegram_message_id}, chat_id={self.chat_id}, type={self.message_type})>"
