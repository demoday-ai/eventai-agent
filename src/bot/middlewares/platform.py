from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.services.platform_client import PlatformClient


class PlatformMiddleware(BaseMiddleware):
    """Inject PlatformClient instance into handler data."""

    def __init__(self, platform: PlatformClient):
        self.platform = platform

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["platform"] = self.platform
        return await handler(event, data)
