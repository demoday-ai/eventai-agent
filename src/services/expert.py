import logging
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.models.expert import Expert
from src.models.expert_score import ExpertScore
from src.models.project import Project
from src.models.schedule_slot import ScheduleSlot

logger = logging.getLogger(__name__)


async def get_expert_by_invite(db: AsyncSession, invite_code: str) -> Expert | None:
    result = await db.execute(
        select(Expert).where(Expert.invite_code == invite_code)
    )
    return result.scalar_one_or_none()


async def get_expert_by_user(db: AsyncSession, user_id: UUID) -> Expert | None:
    result = await db.execute(
        select(Expert).where(Expert.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_room_projects(db: AsyncSession, room_id: UUID, event_id: UUID) -> list[Project]:
    """Get projects assigned to a room via schedule slots."""
    result = await db.execute(
        select(Project)
        .join(ScheduleSlot, ScheduleSlot.project_id == Project.id)
        .where(ScheduleSlot.room_id == room_id, ScheduleSlot.event_id == event_id)
        .order_by(ScheduleSlot.start_time)
    )
    return list(result.scalars().all())


async def get_expert_progress(
    db: AsyncSession, expert_id: UUID, room_id: UUID, event_id: UUID
) -> dict:
    """Get expert scoring progress: total projects, scored count, scores."""
    projects = await get_room_projects(db, room_id, event_id)

    result = await db.execute(
        select(ExpertScore).where(ExpertScore.expert_id == expert_id)
    )
    scores = {s.project_id: s for s in result.scalars().all()}

    return {
        "projects": projects,
        "scores": scores,
        "total": len(projects),
        "scored": len(scores),
    }


async def save_score(
    db: AsyncSession,
    expert_id: UUID,
    project_id: UUID,
    room_id: UUID,
    criteria_scores: dict,
    comment: str | None,
) -> bool:
    """Save expert score with room_id validation. Returns True if saved."""
    # Verify project is in expert's room
    result = await db.execute(
        select(ScheduleSlot).where(
            ScheduleSlot.project_id == project_id,
            ScheduleSlot.room_id == room_id,
        )
    )
    if not result.scalar_one_or_none():
        logger.warning("Expert %s tried to score project %s not in their room %s",
                       expert_id, project_id, room_id)
        return False

    # Upsert score
    stmt = pg_insert(ExpertScore).values(
        expert_id=expert_id,
        project_id=project_id,
        criteria_scores=criteria_scores,
        comment=comment,
    ).on_conflict_do_update(
        index_elements=["expert_id", "project_id"],
        set_={
            "criteria_scores": criteria_scores,
            "comment": comment,
        },
    )

    await db.execute(stmt)
    await db.flush()
    return True
