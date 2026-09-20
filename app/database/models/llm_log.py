from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, Text, DateTime, Float, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, TimestampMixin

class LlmLog(Base, TimestampMixin):
    __tablename__ = "llm_logs"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    request_type: Mapped[str] = mapped_column(String(50), default="chat", nullable=False, index=True)
    
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def __repr__(self) -> str:
        return f"<LlmLog(id={self.id}, type={self.request_type}, model={self.model}, success={self.success})>"
