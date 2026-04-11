"""
Unit tests for PlatformClient and profiling service.
Uses mock httpx - no real network calls.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

os.environ.setdefault("BOT_TOKEN", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://eventai:eventai@localhost:5432/eventai")
os.environ.setdefault("REDIS_URL", "redis://:testpassword@localhost:6379/0")

from src.services.platform_client import PlatformClient
from src.services.profiling import chat_for_profile, build_profile_text


# ---------------------------------------------------------------------------
# PlatformClient tests
# ---------------------------------------------------------------------------


class TestPlatformClient:

    @pytest.mark.asyncio
    async def test_platform_client_register(self):
        """Mock httpx, verify POST /agents called correctly."""
        client = PlatformClient(
            platform_url="http://platform:8000",
            master_token="master-secret",
            agent_name="test-agent",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": "agent-123",
            "token": "bearer-token-xyz",
        }

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.register()

        assert result == "agent-123"
        assert client.token == "bearer-token-xyz"

        # Verify POST call
        client._client.post.assert_awaited_once()
        call_args = client._client.post.call_args
        assert "/agents" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["name"] == "test-agent"
        assert "chat_completion" in payload["methods"]

    @pytest.mark.asyncio
    async def test_platform_client_chat_completion(self):
        """Mock httpx, verify request format for chat completions."""
        client = PlatformClient(
            platform_url="http://platform:8000",
            master_token="master-secret",
        )
        from pydantic import SecretStr
        client._token = SecretStr("test-token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
        }

        client._client = AsyncMock()
        client._client.request = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        result = await client.chat_completion(messages=messages)

        assert result["choices"][0]["message"]["content"] == "Hello!"

        # Verify request
        client._client.request.assert_awaited_once()
        call_args = client._client.request.call_args
        assert call_args[0][0] == "POST"
        assert "/v1/chat/completions" in call_args[0][1]
        assert "Authorization" in call_args[1]["headers"]
        payload = call_args[1]["json"]
        assert payload["messages"] == messages

    @pytest.mark.asyncio
    async def test_platform_client_chat_completion_with_tools(self):
        """Tools and response_format included in payload when provided."""
        client = PlatformClient(
            platform_url="http://platform:8000",
            master_token="master-secret",
        )
        from pydantic import SecretStr
        client._token = SecretStr("test-token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "{}"}}]}

        client._client = AsyncMock()
        client._client.request = AsyncMock(return_value=mock_response)

        tools = [{"type": "function", "function": {"name": "test"}}]
        response_format = {"type": "json_object"}

        await client.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            tools=tools,
            response_format=response_format,
        )

        call_args = client._client.request.call_args
        payload = call_args[1]["json"]
        assert payload["tools"] == tools
        assert payload["response_format"] == response_format

    @pytest.mark.asyncio
    async def test_platform_client_auto_reregister_on_401(self):
        """First call returns 401, triggers register, second call succeeds."""
        client = PlatformClient(
            platform_url="http://platform:8000",
            master_token="master-secret",
        )
        from pydantic import SecretStr
        client._token = SecretStr("old-token")

        # First response: 401
        resp_401 = MagicMock()
        resp_401.status_code = 401

        # Register response
        register_resp = MagicMock()
        register_resp.status_code = 200
        register_resp.raise_for_status = MagicMock()
        register_resp.json.return_value = {
            "id": "agent-new",
            "token": "new-token",
        }

        # Second response after re-register: 200
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.raise_for_status = MagicMock()
        resp_200.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
        }

        mock_client = AsyncMock()
        # request calls: 1st -> 401, then after register 2nd -> 200
        mock_client.request = AsyncMock(side_effect=[resp_401, resp_200])
        mock_client.post = AsyncMock(return_value=register_resp)
        client._client = mock_client

        result = await client.chat_completion(
            messages=[{"role": "user", "content": "test"}],
        )

        assert result["choices"][0]["message"]["content"] == "ok"
        # Register was called (via post)
        mock_client.post.assert_awaited_once()
        # Two request calls: first 401, then success
        assert mock_client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_platform_client_token_not_registered(self):
        """Accessing token before register raises RuntimeError."""
        client = PlatformClient(
            platform_url="http://platform:8000",
            master_token="master-secret",
        )

        with pytest.raises(RuntimeError, match="not registered"):
            _ = client.token

    @pytest.mark.asyncio
    async def test_platform_client_embedding(self):
        """Embedding call returns vector."""
        client = PlatformClient(
            platform_url="http://platform:8000",
            master_token="master-secret",
        )
        from pydantic import SecretStr
        client._token = SecretStr("test-token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
        }

        client._client = AsyncMock()
        client._client.request = AsyncMock(return_value=mock_response)

        result = await client.embedding("test text")

        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_platform_client_repr(self):
        """String representation is informative."""
        client = PlatformClient(
            platform_url="http://platform:8000",
            master_token="master-secret",
        )
        assert "platform:8000" in repr(client)
        assert "registered=False" in repr(client)

    @pytest.mark.asyncio
    async def test_platform_client_register_rate_limit(self):
        """Too many registration attempts raises RuntimeError."""
        client = PlatformClient(
            platform_url="http://platform:8000",
            master_token="master-secret",
        )
        import time
        # Simulate 3 recent attempts
        client._register_attempts = 3
        client._last_register_time = time.monotonic()

        with pytest.raises(RuntimeError, match="Too many registration attempts"):
            await client.register()


# ---------------------------------------------------------------------------
# Profiling service tests
# ---------------------------------------------------------------------------


class TestProfilingService:

    @pytest.mark.asyncio
    async def test_profiling_chat_for_profile_reply(self):
        """LLM returns action=reply with message."""
        platform = AsyncMock()
        platform.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "action": "reply",
                        "message": "Tell me more about your interests.",
                    }),
                },
            }],
        })

        result = await chat_for_profile(
            platform=platform,
            system_prompt="You are a profiling agent.",
            conversation=[{"role": "user", "content": "I like NLP"}],
        )

        assert result["action"] == "reply"
        assert "interests" in result["message"]

    @pytest.mark.asyncio
    async def test_profiling_chat_for_profile_extract(self):
        """LLM returns action=profile with interests extracted."""
        platform = AsyncMock()
        platform.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "action": "profile",
                        "interests": ["NLP", "chatbots"],
                        "goals": ["learn transformers"],
                        "summary": "Student interested in NLP",
                    }),
                },
            }],
        })

        result = await chat_for_profile(
            platform=platform,
            system_prompt="You are a profiling agent.",
            conversation=[{"role": "user", "content": "I am a student studying NLP and chatbots."}],
        )

        assert result["action"] == "profile"
        assert "NLP" in result["interests"]
        assert "chatbots" in result["interests"]
        assert result["summary"] == "Student interested in NLP"

    @pytest.mark.asyncio
    async def test_profiling_fallback_on_json_error(self):
        """LLM returns non-JSON, fallback to reply."""
        platform = AsyncMock()
        platform.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": "This is not JSON at all, just plain text.",
                },
            }],
        })

        result = await chat_for_profile(
            platform=platform,
            system_prompt="You are a profiling agent.",
            conversation=[{"role": "user", "content": "hi"}],
        )

        assert result["action"] == "reply"
        assert "This is not JSON" in result["message"]

    @pytest.mark.asyncio
    async def test_profiling_fallback_on_empty_content(self):
        """LLM returns empty content, fallback to default message."""
        platform = AsyncMock()
        platform.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": "",
                },
            }],
        })

        result = await chat_for_profile(
            platform=platform,
            system_prompt="You are a profiling agent.",
            conversation=[{"role": "user", "content": "hi"}],
        )

        assert result["action"] == "reply"
        assert "Расскажите подробнее" in result["message"]

    @pytest.mark.asyncio
    async def test_profiling_fallback_on_exception(self):
        """Platform raises exception, fallback to default reply."""
        platform = AsyncMock()
        platform.chat_completion = AsyncMock(side_effect=RuntimeError("connection failed"))

        result = await chat_for_profile(
            platform=platform,
            system_prompt="You are a profiling agent.",
            conversation=[{"role": "user", "content": "hi"}],
        )

        assert result["action"] == "reply"
        assert "Расскажите подробнее" in result["message"]

    @pytest.mark.asyncio
    async def test_profiling_no_action_field(self):
        """LLM returns valid JSON without 'action' field -> defaults to reply."""
        platform = AsyncMock()
        platform.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "message": "Some response without action",
                    }),
                },
            }],
        })

        result = await chat_for_profile(
            platform=platform,
            system_prompt="You are a profiling agent.",
            conversation=[{"role": "user", "content": "hi"}],
        )

        assert result["action"] == "reply"


# ---------------------------------------------------------------------------
# build_profile_text tests
# ---------------------------------------------------------------------------


class TestBuildProfileText:

    def test_build_profile_text(self):
        """Various inputs produce correct embedding text."""
        text = build_profile_text(
            selected_tags=["NLP", "CV"],
            keywords=["chatbot"],
            nl_summary="Student interested in AI",
            company="ITMO",
            business_objectives=["automate processes"],
        )

        assert "Student interested in AI" in text
        assert "NLP" in text
        assert "CV" in text
        assert "chatbot" in text
        assert "ITMO" in text
        assert "automate processes" in text

    def test_build_profile_text_empty(self):
        """No data -> default text."""
        text = build_profile_text(
            selected_tags=None,
            keywords=None,
            nl_summary=None,
        )

        assert text == "Интерес к AI проектам"

    def test_build_profile_text_only_tags(self):
        """Only tags provided."""
        text = build_profile_text(
            selected_tags=["robotics"],
            keywords=None,
            nl_summary=None,
        )

        assert "robotics" in text
        assert "Интересы" in text

    def test_build_profile_text_with_raw_text(self):
        """Raw text is included and truncated to 500 chars."""
        long_text = "x" * 1000
        text = build_profile_text(
            selected_tags=None,
            keywords=None,
            nl_summary=None,
            raw_text=long_text,
        )

        # raw_text truncated to 500
        assert len(text) == 500

    def test_build_profile_text_parts_joined_with_dot(self):
        """Parts joined with '. ' separator."""
        text = build_profile_text(
            selected_tags=["NLP"],
            keywords=["bot"],
            nl_summary="AI researcher",
        )

        assert ". " in text
