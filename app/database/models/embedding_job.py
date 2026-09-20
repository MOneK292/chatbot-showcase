from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, TimestampMixin

class EmbeddingJob(Base, TimestampMixin):
    __tablename__ = "embedding_jobs"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    
    # Polymorphic relation to the entity that needs embedding
    source_type: Mapped[str] = mapped_column(String(64), nullable=False) # e.g. 'message', 'summary'
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    # pending, processing, completed, failed
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_embedding_jobs_source", "source_type", "source_id"),
    )

    def __repr__(self) -> str:
        return f"<EmbeddingJob(id={self.id}, source={self.source_type}:{self.source_id}, status={self.status})>"
