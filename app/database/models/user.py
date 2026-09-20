from typing import Optional
from sqlalchemy import BigInteger, Integer, String, Boolean, Identity
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"
