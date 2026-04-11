from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.models.project import Project


def expert_dashboard_keyboard(projects: list[Project], scored_ids: set) -> InlineKeyboardMarkup:
    buttons = []
    for p in projects:
        if p.id in scored_ids:
            continue
        buttons.append([
            InlineKeyboardButton(
                text=f"Оценить: {p.title[:30]}",
                callback_data=f"eval:{p.id}",
            )
        ])
    if not buttons:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def score_keyboard(criterion_index: int) -> InlineKeyboardMarkup:
    """1-5 score buttons for a criterion."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"score:{criterion_index}:{i}") for i in range(1, 6)]
    ])


def confirm_score_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Подтвердить", callback_data="score:confirm"),
            InlineKeyboardButton(text="Назад", callback_data="score:cancel"),
        ],
    ])
