"""Shared fixtures for router tests.

Provides:
- MockedBot instance
- Update factory helpers (make_message, make_callback)
- Real DB session with rollback (PostgreSQL)
- Seed data fixture (event, rooms, projects, slots)
- Dispatcher factory with all routers and custom middlewares
"""

import os
import datetime
from datetime import date, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Update,
    Message,
    Chat,
    User as TgUser,
    CallbackQuery,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

from tests.mocked_bot import MockedBot

# Env vars must be set before any src imports
os.environ.setdefault("BOT_TOKEN", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://eventai:eventai@localhost:5432/eventai",
)
os.environ.setdefault("REDIS_URL", "redis://:testpassword@localhost:6379/0")
os.environ.setdefault("REDIS_PASSWORD", "testpassword")


# -----------------------------------------------------------------------
# MockedBot fixture
# -----------------------------------------------------------------------


@pytest.fixture
def bot():
    return MockedBot()


# -----------------------------------------------------------------------
# Update factory helpers
# -----------------------------------------------------------------------

_MSG_COUNTER = 0


def make_message(
    text: str,
    user_id: int = 42,
    chat_id: int = 42,
    message_id: int | None = None,
) -> Update:
    global _MSG_COUNTER
    _MSG_COUNTER += 1
    mid = message_id or _MSG_COUNTER
    return Update(
        update_id=mid,
        message=Message(
            message_id=mid,
            date=datetime.datetime.now(),
            text=text,
            chat=Chat(id=chat_id, type="private"),
            from_user=TgUser(
                id=user_id,
                is_bot=False,
                first_name="TestUser",
                username="testuser",
            ),
        ),
    )


def make_callback(
    data: str,
    user_id: int = 42,
    chat_id: int = 42,
    message_id: int = 1,
) -> Update:
    global _MSG_COUNTER
    _MSG_COUNTER += 1
    return Update(
        update_id=_MSG_COUNTER + 10000,
        callback_query=CallbackQuery(
            id=str(uuid4()),
            from_user=TgUser(
                id=user_id,
                is_bot=False,
                first_name="TestUser",
                username="testuser",
            ),
            chat_instance="test",
            data=data,
            message=Message(
                message_id=message_id,
                date=datetime.datetime.now(),
                text="button",
                chat=Chat(id=chat_id, type="private"),
                from_user=TgUser(id=42, is_bot=True, first_name="Bot"),
            ),
        ),
    )


# -----------------------------------------------------------------------
# Database fixtures (real PostgreSQL with rollback)
# -----------------------------------------------------------------------

TEST_DB_URL = os.environ["DATABASE_URL"]


@pytest_asyncio.fixture
async def db():
    eng = create_async_engine(TEST_DB_URL, pool_size=2)
    session_factory = async_sessionmaker(
        eng, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()
    await eng.dispose()


@pytest_asyncio.fixture
async def seed(db: AsyncSession):
    """Create test event + rooms + projects + schedule slots.

    Returns dict with event, rooms, projects, slots.
    """
    from src.models.event import Event
    from src.models.project import Project
    from src.models.room import Room
    from src.models.schedule_slot import ScheduleSlot

    event = Event(
        id=uuid4(),
        name="Test Demo Day",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=1),
        description="Test event",
        is_active=True,
        evaluation_criteria=[
            "Техническая сложность",
            "Практическая применимость",
            "Инновационность",
        ],
    )
    db.add(event)

    room1 = Room(id=uuid4(), event_id=event.id, name="Зал NLP", display_order=1)
    room2 = Room(id=uuid4(), event_id=event.id, name="Зал CV", display_order=2)
    db.add_all([room1, room2])

    project_data = [
        (
            "ChatLaw",
            "Чат-бот для юридических консультаций на основе GPT и RAG",
            ["NLP", "LLM", "RAG"],
            ["Python", "LangChain", "FAISS"],
        ),
        (
            "MedVision",
            "AI-система для анализа медицинских снимков",
            ["CV", "медицина"],
            ["Python", "PyTorch", "MONAI"],
        ),
        (
            "SentimentScope",
            "Анализ тональности отзывов в реальном времени",
            ["NLP", "анализ тональности"],
            ["Python", "Transformers", "FastAPI"],
        ),
    ]
    projects = []
    tomorrow = datetime.datetime.now(timezone.utc) + timedelta(hours=24)
    slots = []
    for i, (title, desc, tags, stack) in enumerate(project_data):
        p = Project(
            id=uuid4(),
            event_id=event.id,
            title=title,
            description=desc,
            tags=tags,
            tech_stack=stack,
            author=f"Author {i + 1}",
            telegram_contact=f"@author{i + 1}",
        )
        projects.append(p)
        db.add(p)

        room = room1 if i < 2 else room2
        slot_time = tomorrow + timedelta(minutes=20 * i)
        slot = ScheduleSlot(
            id=uuid4(),
            event_id=event.id,
            room_id=room.id,
            project_id=p.id,
            start_time=slot_time,
            end_time=slot_time + timedelta(minutes=20),
            day_number=1,
        )
        slots.append(slot)
        db.add(slot)

    await db.flush()

    return {
        "event": event,
        "rooms": [room1, room2],
        "projects": projects,
        "slots": slots,
    }
