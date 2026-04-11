from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("profile_id", "project_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("guest_profiles.id"),
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    relevance_score: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(32))
    rank: Mapped[int] = mapped_column(Integer)
    slot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("schedule_slots.id"),
        default=None,
    )
    visit_order: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
