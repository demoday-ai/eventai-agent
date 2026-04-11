"""Tool implementations for the EventAI PydanticAI agent.

Five tools:
- show_project    -- show details of one recommended project
- show_profile    -- show current user profile
- compare_projects -- compare 2-5 projects via LLM-generated matrix
- generate_questions -- generate Q&A questions for a project
- get_summary     -- follow-up (guest) or pipeline (business)
"""

import asyncio
import json
import logging

from pydantic_ai import Agent, RunContext
from sqlalchemy import select

from src.agent.agent import AgentDeps
from src.models.business_followup import BusinessFollowup
from src.models.project import Project
from src.models.recommendation import Recommendation

logger = logging.getLogger(__name__)


def register_tools(agent: Agent[AgentDeps, str]) -> None:
    """Register all 5 tools on the given agent instance."""

    @agent.tool
    async def show_project(ctx: RunContext[AgentDeps], project_rank: int) -> str:
        """Показать детали проекта по номеру в рекомендациях."""
        deps = ctx.deps
        rec = _find_recommendation(deps.recommendations, project_rank)
        if not rec:
            return f"Проект #{project_rank} не найден в рекомендациях."

        result = await deps.db.execute(
            select(Project).where(Project.id == rec.project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return f"Проект #{project_rank} не найден."

        return _format_project_card(project, rec)

    @agent.tool
    async def show_profile(ctx: RunContext[AgentDeps]) -> str:
        """Показать текущий профиль (теги, интересы, цели)."""
        deps = ctx.deps
        if not deps.profile:
            return "Профиль не создан. Используйте /rebuild для персонализации."

        from src.agent.agent import _format_profile

        return _format_profile(deps.profile)

    @agent.tool
    async def compare_projects(
        ctx: RunContext[AgentDeps], project_ranks: list[int]
    ) -> str:
        """Сравнить 2-5 проектов. Матрица сравнения по критериям."""
        deps = ctx.deps
        if len(project_ranks) < 2:
            return "Для сравнения нужно минимум 2 проекта."

        ranks = project_ranks[:5]  # cap at 5

        projects: list[Project] = []
        for rank in ranks:
            rec = _find_recommendation(deps.recommendations, rank)
            if not rec:
                return f"Проект #{rank} не найден в рекомендациях."
            result = await deps.db.execute(
                select(Project).where(Project.id == rec.project_id)
            )
            project = result.scalar_one_or_none()
            if project:
                projects.append(project)

        if len(projects) < 2:
            return "Недостаточно проектов для сравнения."

        from src.prompts.qa import build_comparison_matrix_prompt

        is_business = deps.user.role_code == "business"
        criteria = _get_default_criteria(is_business)
        projects_text = "\n".join(
            f"- {p.title}: {p.description[:200]}. Стек: {', '.join(p.tech_stack or [])}"
            for p in projects
        )

        system_prompt, user_prompt = build_comparison_matrix_prompt(
            projects_text, criteria
        )

        try:
            resp = await asyncio.wait_for(
                deps.platform.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                ),
                timeout=25.0,
            )
            content = resp["choices"][0]["message"]["content"]
            matrix_data = json.loads(content)
            return _format_matrix(matrix_data.get("matrix", {}), criteria)
        except (asyncio.TimeoutError, json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("Compare projects failed: %s", e)
            return "Не удалось сгенерировать сравнение. Попробуйте позже."

    @agent.tool
    async def generate_questions(
        ctx: RunContext[AgentDeps], project_rank: int
    ) -> str:
        """Подготовить 3-5 вопросов для Q&A к проекту."""
        deps = ctx.deps
        rec = _find_recommendation(deps.recommendations, project_rank)
        if not rec:
            return f"Проект #{project_rank} не найден в рекомендациях."

        result = await deps.db.execute(
            select(Project).where(Project.id == rec.project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return "Проект не найден."

        from src.prompts.qa import build_business_qa_prompt, build_guest_qa_prompt

        if deps.user.role_code == "business":
            system_prompt, user_prompt = build_business_qa_prompt(
                objective=(
                    deps.profile.objective if deps.profile else "technology"
                ),
                industries=(
                    ", ".join(deps.profile.business_objectives or [])
                    if deps.profile
                    else ""
                ),
                tech_stack=", ".join(project.tech_stack or []),
                project_title=project.title,
                project_description=project.description[:500],
                project_tech_stack=", ".join(project.tech_stack or []),
            )
        else:
            system_prompt, user_prompt = build_guest_qa_prompt(
                subtype=deps.user.subrole or "other",
                interests=(
                    ", ".join(deps.profile.selected_tags or [])
                    if deps.profile
                    else ""
                ),
                project_title=project.title,
                project_description=project.description[:500],
                project_tech_stack=", ".join(project.tech_stack or []),
            )

        try:
            resp = await asyncio.wait_for(
                deps.platform.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                ),
                timeout=20.0,
            )
            content = resp["choices"][0]["message"]["content"]
            data = json.loads(content)
            questions = data.get("questions", [])

            lines = [f"Вопросы для проекта #{project_rank} ({project.title}):\n"]
            for i, q in enumerate(questions, 1):
                lines.append(f"{i}. {q}")
            return "\n".join(lines)
        except (asyncio.TimeoutError, json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("Generate questions failed: %s", e)
            return "Не удалось сгенерировать вопросы. Попробуйте позже."

    @agent.tool
    async def get_summary(ctx: RunContext[AgentDeps]) -> str:
        """Итоги. Гости: follow-up (контакты + шаблон). Бизнес: pipeline (статусы)."""
        deps = ctx.deps
        if deps.user.role_code == "business":
            return await _get_pipeline(deps)
        return await _get_followup(deps)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_recommendation(
    recs: list[Recommendation], rank: int
) -> Recommendation | None:
    """Find recommendation by rank number."""
    for r in recs:
        if r.rank == rank:
            return r
    return None


def _get_default_criteria(is_business: bool) -> list[str]:
    """Return default comparison criteria based on user role."""
    if is_business:
        return [
            "Стадия проекта",
            "Размер команды",
            "Технический стек",
            "Бизнес-модель",
            "Готовность к пилоту",
        ]
    return [
        "Тематика",
        "Технологии",
        "Практическая применимость",
        "Инновационность",
        "Зрелость проекта",
    ]


def _format_project_card(project: Project, rec: Recommendation) -> str:
    """Format a single project into a readable card."""
    lines = [
        f"#{rec.rank} {project.title} ({rec.relevance_score:.0f}%)\n",
        project.description[:300],
    ]
    if project.tags:
        lines.append(f"\nТеги: {', '.join(project.tags)}")
    if project.tech_stack:
        lines.append(f"Стек: {', '.join(project.tech_stack)}")

    if project.parsed_content and isinstance(project.parsed_content, dict):
        pc = project.parsed_content
        if pc.get("problem"):
            lines.append(f"\nПроблема: {pc['problem']}")
        if pc.get("solution"):
            lines.append(f"Решение: {pc['solution']}")
        if pc.get("novelty"):
            lines.append(f"Новизна: {pc['novelty']}")

    if project.author:
        lines.append(f"\nАвтор: {project.author}")
    return "\n".join(lines)


def _format_matrix(matrix: dict, criteria: list[str]) -> str:
    """Format comparison matrix dict into readable text."""
    if not matrix:
        return "Не удалось сгенерировать матрицу."

    lines = ["Матрица сравнения:\n"]
    for criterion in criteria:
        lines.append(f"*{criterion}:*")
        for project_name, scores in matrix.items():
            value = scores.get(criterion, "-")
            lines.append(f"  {project_name}: {value}")
        lines.append("")
    return "\n".join(lines)


async def _get_followup(deps: AgentDeps) -> str:
    """Build follow-up package for guest users."""
    if not deps.recommendations:
        return "Нет рекомендаций. Используйте /rebuild."

    lines = ["Follow-up пакет:\n"]
    for rec in deps.recommendations[:10]:
        result = await deps.db.execute(
            select(Project).where(Project.id == rec.project_id)
        )
        project = result.scalar_one_or_none()
        if project:
            contact = (
                f" | @{project.telegram_contact}" if project.telegram_contact else ""
            )
            lines.append(f"#{rec.rank} {project.title}{contact}")

    lines.append("\nШаблон для связи:")
    lines.append("Здравствуйте! Видел(а) ваш проект на Demo Day.")
    lines.append("Интересует возможность сотрудничества.")
    return "\n".join(lines)


async def _get_pipeline(deps: AgentDeps) -> str:
    """Build business pipeline summary."""
    result = await deps.db.execute(
        select(BusinessFollowup).where(
            BusinessFollowup.user_id == deps.user.id,
            BusinessFollowup.event_id == deps.event.id,
        )
    )
    followups = result.scalars().all()

    if not followups:
        return "Пайплайн пуст. Сначала получите рекомендации."

    stats: dict[str, int] = {}
    for f in followups:
        stats[f.status] = stats.get(f.status, 0) + 1

    lines = ["Business Pipeline:\n"]
    for status, count in stats.items():
        lines.append(f"  {status}: {count}")
    lines.append("")

    for f in followups[:10]:
        result = await deps.db.execute(
            select(Project).where(Project.id == f.project_id)
        )
        project = result.scalar_one_or_none()
        if project:
            lines.append(f"[{f.status}] {project.title}")
            if f.notes:
                lines.append(f"  {f.notes[:50]}")

    return "\n".join(lines)
