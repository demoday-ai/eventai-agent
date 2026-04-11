from aiogram.fsm.state import State, StatesGroup


class BotStates(StatesGroup):
    choose_role = State()
    onboard_nl_profile = State()
    onboard_confirm = State()
    view_program = State()
    view_detail = State()
    support_chat = State()
    expert_dashboard = State()
    expert_evaluation = State()
