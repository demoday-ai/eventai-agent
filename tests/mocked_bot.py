"""MockedBot and MockedSession for aiogram 3.x testing.

Copied from aiogram's test suite pattern. Allows feeding Updates through
the full Dispatcher pipeline (middleware -> filter -> handler) without
hitting the real Telegram API.
"""

from collections import deque
from collections.abc import AsyncGenerator
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.methods.base import Response, TelegramType
from aiogram.types import UNSET_PARSE_MODE, ResponseParameters, User


class MockedSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.responses: deque[Response[TelegramType]] = deque()
        self.requests: deque[TelegramMethod[TelegramType]] = deque()
        self.closed = True

    def add_result(self, response: Response[TelegramType]) -> Response[TelegramType]:
        self.responses.append(response)
        return response

    def get_request(self) -> TelegramMethod[TelegramType]:
        return self.requests.popleft()

    async def close(self):
        self.closed = True

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout=UNSET_PARSE_MODE,
    ) -> TelegramType:
        self.closed = False
        self.requests.append(method)
        response: Response[TelegramType] = self.responses.popleft()
        self.check_response(
            bot=bot,
            method=method,
            status_code=response.error_code,
            content=response.model_dump_json(),
        )
        return response.result

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b""


class MockedBot(Bot):
    def __init__(self, **kwargs):
        super().__init__(
            kwargs.pop("token", "42:TEST"),
            session=MockedSession(),
            **kwargs,
        )
        self._me = User(
            id=42,
            is_bot=True,
            first_name="TestBot",
            username="testbot",
            language_code="en",
        )

    def add_result_for(
        self,
        method,
        ok,
        result=None,
        description=None,
        error_code=200,
        **kwargs,
    ):
        response = Response[method.__returning__](
            ok=ok,
            result=result,
            description=description,
            error_code=error_code,
            parameters=ResponseParameters(**kwargs) if kwargs else None,
        )
        self.session.add_result(response)
        return response

    def get_request(self):
        return self.session.get_request()
