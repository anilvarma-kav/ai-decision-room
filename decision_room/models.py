"""Validated contracts shared by the API, models, and storage layer."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Text = Annotated[str, Field(min_length=1, max_length=2500)]
Role = Literal["strategist", "engineer", "skeptic"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DecisionRequest(StrictModel):
    question: str = Field(min_length=15, max_length=2000)
    context: str = Field(default="", max_length=6000)
    mode: Literal["demo", "live"] = "demo"
    scenario: Literal["search", "hosting", "support"] = "search"
    models: list[Literal["openai", "anthropic", "gemini", "ollama"]] = Field(
        default_factory=lambda: ["openai", "anthropic", "openai"], min_length=3, max_length=3
    )

    @field_validator("question")
    @classmethod
    def meaningful_question(cls, value: str) -> str:
        if len(value.strip()) < 15:
            raise ValueError("Describe the decision in at least 15 characters.")
        return value.strip()


class Opinion(StrictModel):
    recommendation: Text
    rationale: Text
    assumptions: list[Text] = Field(min_length=1, max_length=5)
    risks: list[Text] = Field(min_length=1, max_length=5)


class Review(StrictModel):
    challenge: Text
    concession: Text
    revised_position: Text


class Criterion(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    weight: float = Field(gt=0, le=100)


class Option(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    scores: list[float] = Field(min_length=2, max_length=6)

    @field_validator("scores")
    @classmethod
    def valid_scores(cls, scores: list[float]) -> list[float]:
        import math

        if any(not math.isfinite(s) or not 0 <= s <= 10 for s in scores):
            raise ValueError("Every score must be between 0 and 10.")
        return scores


class Matrix(StrictModel):
    criteria: list[Criterion] = Field(min_length=2, max_length=6)
    options: list[Option] = Field(min_length=2, max_length=4)


class Memo(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    recommendation: Text
    summary: Text
    agreement: list[Text] = Field(min_length=1, max_length=5)
    disagreements: list[Text] = Field(min_length=1, max_length=5)
    next_steps: list[Text] = Field(min_length=2, max_length=5)
    revisit_when: Text
    matrix: Matrix
