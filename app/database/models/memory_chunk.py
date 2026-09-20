from sqlalchemy import BigInteger, Integer, String, Text, ARRAY, Float, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, TimestampMixin

class MemoryChunk(Base, TimestampMixin):
    __tablename__ = "memory_chunks"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    
    # Polymorphic relation
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True) # e.g. 'message', 'summary'
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    
    text_chunk: Mapped[str] = mapped_column(Text, nullable=False)
    
    # In-memory vector store (NumPy compatible)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=True)
    
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=True)
    embedding_hash: Mapped[str] = mapped_column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index("ix_memory_chunks_source", "source_type", "source_id"),
    )

    def __repr__(self) -> str:
        return f"<MemoryChunk(id={self.id}, source={self.source_type}:{self.source_id})>"
