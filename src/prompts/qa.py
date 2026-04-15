"""Prompts for Q&A generation and project comparison matrix.

Adapted from demoday-core/backend/app/prompts/guest/qa.py.
"""

# ---------------------------------------------------------------------------
# System prompts (shared)
# ---------------------------------------------------------------------------

GUEST_QA_SYSTEM = (
    "Ты - помощник для гостей Demo Day. Генерируй вопросы на русском языке.\n"
    "Вопросы должны быть конкретными, содержательными и учитывать профиль гостя.\n"
    "Формат: нумерованный список (1. вопрос, 2. вопрос, ...). Без лишнего текста."
)

BUSINESS_QA_SYSTEM = (
    "Ты - помощник для бизнес-партнеров Demo Day. Генерируй вопросы на русском языке.\n"
    "Вопросы должны быть бизнес-ориентированными и учитывать цель партнера.\n"
    "Формат: нумерованный список (1. вопрос, 2. вопрос, ...). Без лишнего текста."
)

COMPARISON_MATRIX_SYSTEM = (
    "Ты - аналитик Demo Day. Создай матрицу сравнения проектов.\n"
    "Оцени каждый проект по каждому критерию кратко (1-3 слова или оценка).\n"
    "КРИТИЧНО: используй ТОЛЬКО информацию из описания проекта. "
    "НЕ ДОМЫСЛИВАЙ стадию, размер команды, зрелость, бизнес-модель или другие факты, "
    "которых нет в описании. Если данных нет - пиши 'нет данных'.\n"
    'Формат ответа: JSON объект с полем "matrix" - словарь {{project_title: {{criterion: value}}}}.'
)

# ---------------------------------------------------------------------------
# Objective label mapping (business)
# ---------------------------------------------------------------------------

_OBJECTIVE_MAP: dict[str, str] = {
    "investment": "Инвестор",
    "hiring": "HR / нанимающий менеджер",
    "technology": "Технологический партнер",
    "partnership": "Бизнес-партнер",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_guest_qa_prompt(
    subtype: str,
    interests: str,
    project_title: str,
    project_description: str,
    project_tech_stack: str,
) -> tuple[str, str]:
    """Build LLM prompt pair for guest Q&A generation.

    Args:
        subtype: Guest subtype ("student", "applicant", "other").
        interests: Comma-separated interests string.
        project_title: Project title.
        project_description: Truncated project description (<= 500 chars).
        project_tech_stack: Comma-separated tech stack.

    Returns:
        Tuple (system_prompt, user_prompt).
    """
    subtype_map: dict[str, str] = {
        "student": "Студент / AI-практик",
        "applicant": "Абитуриент",
        "other": "Гость",
    }
    subtype_desc = subtype_map.get(subtype, "Гость")

    interests_line = f"\n- Интересы: {interests}" if interests else ""

    user_prompt = (
        "Сгенерируй 3-5 вопросов для гостя, который хочет посетить проект.\n\n"
        "Профиль гостя:\n"
        f"- Тип: {subtype_desc}{interests_line}\n\n"
        "Проект:\n"
        f"- Название: {project_title}\n"
        f"- Описание: {project_description}\n"
        f"- Технологии: {project_tech_stack}\n\n"
        "Правила генерации:\n"
        "- Абитуриент: фокус на обучении, команде, технологиях для изучения, карьерном пути\n"
        "- AI-практик: фокус на архитектуре, подходах, метриках, воспроизводимости, инновациях\n"
        "- Гость: общие вопросы про ценность проекта, применимость, планы развития\n\n"
        "Ответь нумерованным списком из 3-5 вопросов."
    )

    return GUEST_QA_SYSTEM, user_prompt


def build_business_qa_prompt(
    objective: str,
    industries: str,
    tech_stack: str,
    project_title: str,
    project_description: str,
    project_tech_stack: str,
) -> tuple[str, str]:
    """Build LLM prompt pair for business partner Q&A generation.

    Args:
        objective: Business objective code
            ("investment", "hiring", "technology", "partnership").
        industries: Comma-separated partner industries.
        tech_stack: Comma-separated partner tech focus.
        project_title: Project title.
        project_description: Truncated project description (<= 500 chars).
        project_tech_stack: Comma-separated project tech stack.

    Returns:
        Tuple (system_prompt, user_prompt).
    """
    objective_desc = _OBJECTIVE_MAP.get(objective, "Партнер")
    industries_str = industries if industries else "Не указано"
    tech_str = tech_stack if tech_stack else "Не указано"

    user_prompt = (
        "Сгенерируй 3-5 бизнес-вопросов для партнера, оценивающего проект.\n\n"
        "Профиль партнера:\n"
        f"- Цель: {objective_desc}\n"
        f"- Отрасли: {industries_str}\n"
        f"- Технологический фокус: {tech_str}\n\n"
        "Проект:\n"
        f"- Название: {project_title}\n"
        f"- Описание: {project_description}\n"
        f"- Технологии: {project_tech_stack}\n\n"
        "Правила генерации по цели:\n"
        "- Инвестор: unit-экономика, рынок, команда, стадия, раунд, метрики\n"
        "- HR: стек, опыт команды, готовность к работе, интересы, мотивация\n"
        "- Технологический партнер: интеграция, API, масштабирование, лицензия\n"
        "- Бизнес-партнер: бизнес-модель, готовность к пилоту, условия сотрудничества\n\n"
        "Ответь нумерованным списком из 3-5 вопросов."
    )

    return BUSINESS_QA_SYSTEM, user_prompt


def build_comparison_matrix_prompt(
    projects_text: str,
    criteria: list[str],
) -> tuple[str, str]:
    """Build LLM prompt pair for project comparison matrix.

    Args:
        projects_text: Formatted list of projects with descriptions.
        criteria: Comparison criteria list.

    Returns:
        Tuple (system_prompt, user_prompt).
    """
    criteria_list = ", ".join(criteria)

    user_prompt = (
        "Сравни проекты по критериям.\n\n"
        "Проекты:\n"
        f"{projects_text}\n\n"
        f"Критерии: {criteria_list}\n\n"
        "Для каждого проекта укажи значение по каждому критерию.\n"
        'Ответь JSON: {{"matrix": {{"Название проекта": {{"Критерий1": "значение", ...}}, ...}}}}'
    )

    return COMPARISON_MATRIX_SYSTEM, user_prompt
