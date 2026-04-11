from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("events.id"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255), default=None)
    telegram_contact: Mapped[str | None] = mapped_column(String(255), default=None)
    track: Mapped[str | None] = mapped_column(String(255), default=None)
    tags: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    tech_stack: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    github_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    presentation_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    parsed_content: Mapped[dict | None] = mapped_column(JSONB, default=None)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(3072),
        default=None,
    )
