from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class GuestProfile(Base):
    __tablename__ = "guest_profiles"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("events.id"),
        index=True,
    )
    selected_tags: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    keywords: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    raw_text: Mapped[str | None] = mapped_column(Text, default=None)
    nl_summary: Mapped[str | None] = mapped_column(Text, default=None)
    company: Mapped[str | None] = mapped_column(String(255), default=None)
    position: Mapped[str | None] = mapped_column(String(255), default=None)
    objective: Mapped[str | None] = mapped_column(Text, default=None)
    business_objectives: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        default=None,
        onupdate=func.now(),
    )
