from pydantic import BaseModel


class ComparisonMatrix(BaseModel):
    projects: list[str]
    criteria: list[str]
    matrix: dict[str, dict[str, str]]


class ProjectExtraction(BaseModel):
    problem: str
    solution: str
    audience: str
    stack: list[str]
    novelty: str
    risks: str | None = None
