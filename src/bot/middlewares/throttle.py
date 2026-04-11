import logging
from typing import Any, Awaitable, Callable
from uuid import uuid4

import redis.asyncio as aioredis
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)

# Lua script: delete key only if current value matches owner token.
# Prevents releasing a lock acquired by another request after TTL expiry.
_LUA_DELETE_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class ThrottleMiddleware(BaseMiddleware):
    """Per-user rate limiting (10 msg/min) and mutex via Redis.

    Rate limit uses INCR + EXPIRE on ``rate:min:{user_id}``.
    Mutex uses SET NX with a uuid4 owner token on ``lock:{user_id}``
    and a Lua script to delete only the own lock in the finally block.
    """

    def __init__(self, redis: aioredis.Redis, rate_limit: int = 10):
        self.redis = redis
        self.rate_limit = rate_limit

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        user_id = user.id

        # --- Rate limit: 10 msg/min ---
        rate_key = f"rate:min:{user_id}"
        count = await self.redis.incr(rate_key)
        if count == 1:
            await self.redis.expire(rate_key, 60)
        if count > self.rate_limit:
            logger.debug("Rate limit hit for user %s (%d/%d)", user_id, count, self.rate_limit)
            if isinstance(event, Message):
                await event.answer("Слишком много сообщений. Подождите минуту.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Подождите минуту.", show_alert=True)
            return None

        # --- Per-user mutex ---
        lock_key = f"lock:{user_id}"
        lock_value = str(uuid4())
        acquired = await self.redis.set(lock_key, lock_value, ex=60, nx=True)
        if not acquired:
            logger.debug("Mutex not acquired for user %s", user_id)
            if isinstance(event, Message):
                await event.answer("Подождите, обрабатываю предыдущий запрос...")
            elif isinstance(event, CallbackQuery):
                await event.answer("Подождите...", show_alert=True)
            return None

        try:
            data["redis"] = self.redis
            return await handler(event, data)
        finally:
            await self.redis.eval(_LUA_DELETE_IF_OWNER, 1, lock_key, lock_value)
