"""Convert LLM markdown output to Telegram-safe format using entities.

Uses telegramify-markdown to convert standard markdown (**bold**, ```code```,
- lists, > quotes) into (text, entities) pairs that Telegram renders correctly
without parse_mode.

Usage:
    from src.core.telegram_format import send_formatted

    await send_formatted(message, llm_output)
    # or reply to a message:
    await send_formatted(message, llm_output, reply=True)
"""

import logging
from aiogram.types import Message, MessageEntity

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096


def md_to_entities(text: str) -> tuple[str, list[MessageEntity]]:
    """Convert markdown text to (plain_text, entities) for Telegram."""
    try:
        from telegramify_markdown import convert
        plain, raw_entities = convert(text)
        entities = [
            MessageEntity(
                type=e.type,
                offset=e.offset,
                length=e.length,
                url=getattr(e, "url", None),
                language=getattr(e, "language", None),
            )
            for e in raw_entities
        ]
        return plain, entities
    except Exception as e:
        logger.warning("Failed to convert markdown, sending as plain text: %s", e)
        return text, []


async def send_formatted(message: Message, text: str, reply: bool = False) -> None:
    """Send LLM output with proper Telegram formatting.

    Handles:
    - Markdown to entities conversion
    - Message splitting for long texts (>4096 chars)
    - Fallback to plain text on error
    """
    if not text:
        return

    plain, entities = md_to_entities(text)

    # Split long messages
    if len(plain) <= MAX_MESSAGE_LENGTH:
        try:
            if reply:
                await message.reply(plain, entities=entities)
            else:
                await message.answer(plain, entities=entities)
        except Exception as e:
            logger.warning("Failed to send with entities, falling back: %s", e)
            if reply:
                await message.reply(plain)
            else:
                await message.answer(plain)
    else:
        # Split into chunks
        chunks = _split_text(plain, entities)
        for chunk_text, chunk_entities in chunks:
            try:
                await message.answer(chunk_text, entities=chunk_entities)
            except Exception:
                await message.answer(chunk_text)


def _split_text(
    text: str, entities: list[MessageEntity], max_len: int = MAX_MESSAGE_LENGTH
) -> list[tuple[str, list[MessageEntity]]]:
    """Split text + entities into chunks that fit Telegram's limit."""
    if len(text) <= max_len:
        return [(text, entities)]

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + max_len, len(text))

        # Try to split at newline
        if end < len(text):
            newline_pos = text.rfind("\n", start, end)
            if newline_pos > start:
                end = newline_pos + 1

        chunk_text = text[start:end]

        # Filter and adjust entities for this chunk
        chunk_entities = []
        for e in entities:
            e_start = e.offset
            e_end = e.offset + e.length
            if e_end <= start or e_start >= end:
                continue  # entity outside chunk
            adj_start = max(e_start - start, 0)
            adj_end = min(e_end - start, len(chunk_text))
            if adj_end > adj_start:
                chunk_entities.append(
                    MessageEntity(
                        type=e.type,
                        offset=adj_start,
                        length=adj_end - adj_start,
                        url=e.url,
                        language=e.language,
                    )
                )

        chunks.append((chunk_text, chunk_entities))
        start = end

    return chunks
