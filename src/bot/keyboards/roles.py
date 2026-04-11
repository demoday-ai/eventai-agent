from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Студент", callback_data="role:guest:student")],
        [InlineKeyboardButton(text="Абитуриент", callback_data="role:guest:applicant")],
        [InlineKeyboardButton(text="Бизнес-партнер", callback_data="role:business")],
        [InlineKeyboardButton(text="Другое", callback_data="role:guest:other")],
        [InlineKeyboardButton(text="Показать все проекты", callback_data="role:shortcut")],
    ])
