from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Expert(Base):
    __tablename__ = "experts"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"))
    invite_code: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    room_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("rooms.id"),
        default=None,
    )
    tags: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    bot_started: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
