"""
Unit tests for ThrottleMiddleware and ReconcileMiddleware.
Uses mock Redis, handler, event, state - no real external services.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

os.environ.setdefault("BOT_TOKEN", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://eventai:eventai@localhost:5432/eventai")
os.environ.setdefault("REDIS_URL", "redis://:testpassword@localhost:6379/0")

from src.bot.middlewares.throttle import ThrottleMiddleware
from src.bot.middlewares.reconcile import ReconcileMiddleware
from src.bot.states import BotStates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message_event(user_id: int = 12345, text: str = "hello") -> MagicMock:
    """Create a mock aiogram Message with from_user."""
    event = MagicMock()
    event.from_user = MagicMock()
    event.from_user.id = user_id
    event.text = text
    event.answer = AsyncMock()
    # isinstance checks
    from aiogram.types import Message
    event.__class__ = Message
    return event


def _make_callback_event(user_id: int = 12345) -> MagicMock:
    """Create a mock aiogram CallbackQuery with from_user."""
    event = MagicMock()
    event.from_user = MagicMock()
    event.from_user.id = user_id
    event.answer = AsyncMock()
    from aiogram.types import CallbackQuery
    event.__class__ = CallbackQuery
    return event


def _make_redis_mock(
    incr_value: int = 1,
    set_result: bool = True,
) -> AsyncMock:
    """Create a mock Redis instance."""
    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=incr_value)
    redis.expire = AsyncMock()
    redis.set = AsyncMock(return_value=set_result)
    redis.eval = AsyncMock(return_value=1)
    redis.get = AsyncMock(return_value=None)
    return redis


# ---------------------------------------------------------------------------
# ThrottleMiddleware tests
# ---------------------------------------------------------------------------


class TestThrottleMiddleware:
    """Tests for ThrottleMiddleware rate limiting and mutex."""

    @pytest.mark.asyncio
    async def test_throttle_allows_first_request(self):
        """First message passes through - rate count=1, lock acquired."""
        redis = _make_redis_mock(incr_value=1, set_result=True)
        handler = AsyncMock(return_value="ok")
        event = _make_message_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        result = await mw(handler, event, data)

        assert result == "ok"
        handler.assert_awaited_once()
        redis.incr.assert_awaited_once()
        redis.set.assert_awaited_once()
        # Redis injected into data
        assert data["redis"] is redis

    @pytest.mark.asyncio
    async def test_throttle_blocks_concurrent(self):
        """Second message while first is processing gets 'Подождите'."""
        redis = _make_redis_mock(incr_value=2, set_result=False)  # lock NOT acquired
        handler = AsyncMock()
        event = _make_message_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        result = await mw(handler, event, data)

        assert result is None
        handler.assert_not_awaited()
        event.answer.assert_awaited_once()
        call_text = event.answer.call_args[0][0]
        assert "Подождите" in call_text

    @pytest.mark.asyncio
    async def test_throttle_blocks_concurrent_callback(self):
        """CallbackQuery while lock held gets 'Подождите...'."""
        redis = _make_redis_mock(incr_value=2, set_result=False)
        handler = AsyncMock()
        event = _make_callback_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        result = await mw(handler, event, data)

        assert result is None
        handler.assert_not_awaited()
        event.answer.assert_awaited_once()
        call_kwargs = event.answer.call_args
        assert call_kwargs[1].get("show_alert") is True

    @pytest.mark.asyncio
    async def test_throttle_rate_limit(self):
        """After 10 messages in a minute, next gets 'Слишком много'."""
        redis = _make_redis_mock(incr_value=11, set_result=True)
        handler = AsyncMock()
        event = _make_message_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        result = await mw(handler, event, data)

        assert result is None
        handler.assert_not_awaited()
        event.answer.assert_awaited_once()
        call_text = event.answer.call_args[0][0]
        assert "Слишком много" in call_text

    @pytest.mark.asyncio
    async def test_throttle_rate_limit_callback(self):
        """CallbackQuery rate limited gets alert."""
        redis = _make_redis_mock(incr_value=11, set_result=True)
        handler = AsyncMock()
        event = _make_callback_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        result = await mw(handler, event, data)

        assert result is None
        handler.assert_not_awaited()
        event.answer.assert_awaited_once()
        call_kwargs = event.answer.call_args
        assert call_kwargs[1].get("show_alert") is True

    @pytest.mark.asyncio
    async def test_throttle_releases_lock(self):
        """After handler completes, lock is released via Lua script."""
        redis = _make_redis_mock(incr_value=1, set_result=True)
        handler = AsyncMock(return_value="done")
        event = _make_message_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        await mw(handler, event, data)

        # eval called in finally block to release lock
        redis.eval.assert_awaited_once()
        # Verify Lua script is passed
        call_args = redis.eval.call_args[0]
        assert "redis.call('get'" in call_args[0]
        assert "redis.call('del'" in call_args[0]

    @pytest.mark.asyncio
    async def test_throttle_releases_lock_on_handler_error(self):
        """Lock is released even if handler raises an exception."""
        redis = _make_redis_mock(incr_value=1, set_result=True)
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        event = _make_message_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        with pytest.raises(RuntimeError, match="boom"):
            await mw(handler, event, data)

        # Lock still released in finally
        redis.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_throttle_lua_delete_only_own_lock(self):
        """Lua script only deletes lock if value matches owner token."""
        from src.bot.middlewares.throttle import _LUA_DELETE_IF_OWNER

        # Lua script checks ARGV[1] against stored value
        assert "ARGV[1]" in _LUA_DELETE_IF_OWNER
        assert "redis.call('get', KEYS[1])" in _LUA_DELETE_IF_OWNER
        assert "redis.call('del', KEYS[1])" in _LUA_DELETE_IF_OWNER

        # When called, it passes lock_key as KEYS[1] and lock_value as ARGV[1]
        redis = _make_redis_mock(incr_value=1, set_result=True)
        handler = AsyncMock(return_value="ok")
        event = _make_message_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        await mw(handler, event, data)

        call_args = redis.eval.call_args[0]
        # Args: script, numkeys=1, lock_key, lock_value
        assert call_args[1] == 1  # numkeys
        assert call_args[2].startswith("lock:")  # lock key
        # lock_value is a uuid4 string
        lock_value = call_args[3]
        assert len(lock_value) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_throttle_no_user(self):
        """Event without from_user passes directly to handler."""
        redis = _make_redis_mock()
        handler = AsyncMock(return_value="pass")
        event = MagicMock()
        event.from_user = None
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        result = await mw(handler, event, data)

        assert result == "pass"
        handler.assert_awaited_once()
        redis.incr.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_throttle_expire_set_on_first_incr(self):
        """TTL is set only when count == 1 (first increment)."""
        redis = _make_redis_mock(incr_value=1, set_result=True)
        handler = AsyncMock(return_value="ok")
        event = _make_message_event(user_id=999)
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        await mw(handler, event, data)

        redis.expire.assert_awaited_once()
        # Expire called with key and 60 seconds
        call_args = redis.expire.call_args[0]
        assert call_args[0] == "rate:min:999"
        assert call_args[1] == 60

    @pytest.mark.asyncio
    async def test_throttle_no_expire_on_subsequent_incr(self):
        """TTL is NOT reset on subsequent increments (count > 1)."""
        redis = _make_redis_mock(incr_value=5, set_result=True)
        handler = AsyncMock(return_value="ok")
        event = _make_message_event()
        data: dict = {}

        mw = ThrottleMiddleware(redis, rate_limit=10)
        await mw(handler, event, data)

        redis.expire.assert_not_awaited()


# ---------------------------------------------------------------------------
# ReconcileMiddleware tests
# ---------------------------------------------------------------------------


class TestReconcileMiddleware:
    """Tests for ReconcileMiddleware FSM reconciliation."""

    @pytest.mark.asyncio
    async def test_reconcile_skips_non_start(self):
        """Middleware does nothing for regular messages when state exists."""
        handler = AsyncMock(return_value="ok")
        event = _make_message_event(text="hello")

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=BotStates.view_program.state)

        data: dict = {"state": state}

        mw = ReconcileMiddleware()
        result = await mw(handler, event, data)

        assert result == "ok"
        handler.assert_awaited_once()
        # State should not be changed
        state.set_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_on_start_with_profile(self):
        """/start with existing guest profile -> reconcile to view_program."""
        handler = AsyncMock(return_value="ok")
        event = _make_message_event(user_id=111, text="/start")

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)  # no current state

        # Mock DB session with User and GuestProfile
        db_user = MagicMock()
        db_user.id = uuid4()

        profile = MagicMock()
        profile.user_id = db_user.id

        # DB execute results
        db = AsyncMock()
        # First call: select(User) -> returns db_user
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = db_user
        # Second call: select(Expert) -> returns None
        expert_result = MagicMock()
        expert_result.scalar_one_or_none.return_value = None
        # Third call: select(GuestProfile) -> returns profile
        profile_result = MagicMock()
        profile_result.scalar_one_or_none.return_value = profile

        db.execute = AsyncMock(side_effect=[user_result, expert_result, profile_result])

        data: dict = {"state": state, "db": db}

        mw = ReconcileMiddleware()
        result = await mw(handler, event, data)

        assert result == "ok"
        state.set_state.assert_awaited_once_with(BotStates.view_program)

    @pytest.mark.asyncio
    async def test_reconcile_on_start_new_user(self):
        """/start without any DB data -> lets handler proceed (new user flow)."""
        handler = AsyncMock(return_value="ok")
        event = _make_message_event(user_id=222, text="/start")

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)

        # DB: no user found
        db = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=user_result)

        data: dict = {"state": state, "db": db}

        mw = ReconcileMiddleware()
        result = await mw(handler, event, data)

        assert result == "ok"
        handler.assert_awaited_once()
        state.set_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_on_start_expert(self):
        """/start with existing expert (bot_started=True) -> expert_dashboard."""
        handler = AsyncMock(return_value="ok")
        event = _make_message_event(user_id=333, text="/start")

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)

        db_user = MagicMock()
        db_user.id = uuid4()

        expert = MagicMock()
        expert.bot_started = True

        db = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = db_user
        expert_result = MagicMock()
        expert_result.scalar_one_or_none.return_value = expert

        db.execute = AsyncMock(side_effect=[user_result, expert_result])

        data: dict = {"state": state, "db": db}

        mw = ReconcileMiddleware()
        result = await mw(handler, event, data)

        assert result == "ok"
        state.set_state.assert_awaited_once_with(BotStates.expert_dashboard)

    @pytest.mark.asyncio
    async def test_reconcile_no_state_context(self):
        """If no FSM state in data, passes directly to handler."""
        handler = AsyncMock(return_value="ok")
        event = _make_message_event(text="/start")
        data: dict = {}

        mw = ReconcileMiddleware()
        result = await mw(handler, event, data)

        assert result == "ok"
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconcile_no_db(self):
        """If no db session in data, passes to handler."""
        handler = AsyncMock(return_value="ok")
        event = _make_message_event(text="/start")

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)

        data: dict = {"state": state}

        mw = ReconcileMiddleware()
        result = await mw(handler, event, data)

        assert result == "ok"
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconcile_expert_deep_link(self):
        """/start expert_<code> -> let handler parse payload, skip reconcile."""
        handler = AsyncMock(return_value="ok")
        event = _make_message_event(user_id=444, text="/start expert_abc123")

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)

        db = AsyncMock()
        data: dict = {"state": state, "db": db}

        mw = ReconcileMiddleware()
        result = await mw(handler, event, data)

        assert result == "ok"
        handler.assert_awaited_once()
        # DB should not be queried for expert deep link
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_no_from_user(self):
        """Event without from_user passes directly."""
        handler = AsyncMock(return_value="ok")
        event = MagicMock()
        event.from_user = None
        event.text = "/start"
        from aiogram.types import Message
        event.__class__ = Message

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)

        data: dict = {"state": state}

        mw = ReconcileMiddleware()
        result = await mw(handler, event, data)

        assert result == "ok"
        handler.assert_awaited_once()
