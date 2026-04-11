import json
import logging
from src.services.platform_client import PlatformClient

logger = logging.getLogger(__name__)


async def chat_for_profile(
    platform: PlatformClient,
    system_prompt: str,
    conversation: list[dict],
) -> dict:
    """One turn of profiling dialogue.

    Returns dict with:
    - action: "reply" (continue dialog) or "profile" (profile extracted)
    - message: reply text (if action=reply)
    - interests, goals, summary: extracted profile (if action=profile)
    - company, position, business_objectives: business fields (if business)
    """
    content = ""
    try:
        messages = [{"role": "system", "content": system_prompt}] + conversation

        resp = await platform.chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
        )

        content = resp["choices"][0]["message"]["content"]
        result = json.loads(content)

        if "action" not in result:
            result["action"] = "reply"
            result["message"] = content

        return result
    except json.JSONDecodeError:
        logger.warning("Profiling LLM returned non-JSON, treating as reply")
        return {"action": "reply", "message": content if content else "Расскажите подробнее о ваших интересах."}
    except Exception as e:
        logger.error("Profiling failed: %s", e)
        return {"action": "reply", "message": "Расскажите подробнее о ваших интересах."}


def build_profile_text(
    selected_tags: list[str] | None,
    keywords: list[str] | None,
    nl_summary: str | None,
    company: str | None = None,
    business_objectives: list[str] | None = None,
    raw_text: str | None = None,
) -> str:
    """Build text for embedding from profile data."""
    parts: list[str] = []
    if nl_summary:
        parts.append(nl_summary)
    if selected_tags:
        parts.append(f"Интересы: {', '.join(selected_tags)}")
    if keywords:
        parts.append(f"Ключевые слова: {', '.join(keywords)}")
    if company:
        parts.append(f"Компания: {company}")
    if business_objectives:
        parts.append(f"Бизнес-цели: {', '.join(business_objectives)}")
    if raw_text:
        parts.append(raw_text[:500])

    return ". ".join(parts) if parts else "Интерес к AI проектам"
