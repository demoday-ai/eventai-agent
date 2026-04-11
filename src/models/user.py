from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

role_enum = Enum("guest", "business", "expert", name="role_enum")


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    telegram_user_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255), default=None)
    role_code: Mapped[str | None] = mapped_column(role_enum, default=None)
    subrole: Mapped[str | None] = mapped_column(String(128), default=None)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
