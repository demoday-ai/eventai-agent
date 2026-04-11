from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def program_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Профиль", callback_data="cmd:profile"),
            InlineKeyboardButton(text="Если успеете", callback_data="cmd:if_time"),
        ],
    ])


def detail_keyboard(project_rank: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Назад", callback_data="cmd:back"),
            InlineKeyboardButton(text="Вопросы к проекту", callback_data=f"questions:{project_rank}"),
        ],
    ])


def confirm_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Все верно", callback_data="profile:confirm"),
            InlineKeyboardButton(text="Заново", callback_data="profile:retry"),
        ],
    ])


def support_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад к программе", callback_data="support:back")],
    ])
