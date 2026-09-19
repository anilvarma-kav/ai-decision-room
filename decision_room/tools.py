"""Small, deterministic tools. No eval, shell execution, or network access."""

import json

from pydantic import Field, model_validator

from decision_room.models import Matrix, StrictModel


class CostComparison(StrictModel):
    upfront: float = Field(ge=0, le=1e9)
    monthly: float = Field(ge=0, le=1e9)
    months: int = Field(ge=1, le=120)
    alternative_monthly: float = Field(ge=0, le=1e9)


class WeightedMatrix(Matrix):
    @model_validator(mode="after")
    def matching_columns(self):
        if any(len(o.scores) != len(self.criteria) for o in self.options):
            raise ValueError("Each option needs a score for every criterion.")
        if len({o.name for o in self.options}) != len(self.options):
            raise ValueError("Option names must be unique.")
        if len({c.name for c in self.criteria}) != len(self.criteria):
            raise ValueError("Criterion names must be unique.")
        return self


def weighted_scores(matrix: dict) -> dict:
    parsed = WeightedMatrix.model_validate(matrix)
    total = sum(c.weight for c in parsed.criteria)
    scores = [
        {
            "name": o.name,
            "score": round(
                sum(s * c.weight for s, c in zip(o.scores, parsed.criteria, strict=True)) / total, 2
            ),
        }
        for o in parsed.options
    ]
    return {"ranking": sorted(scores, key=lambda x: x["score"], reverse=True), "scale": 10}


def compare_costs(arguments: dict) -> dict:
    p = CostComparison.model_validate(arguments)
    return {
        "total": round(p.upfront + p.monthly * p.months, 2),
        "alternative_total": round(p.alternative_monthly * p.months, 2),
        "difference": round(p.upfront + (p.monthly - p.alternative_monthly) * p.months, 2),
        "months": p.months,
        "note": "Arithmetic using supplied assumptions; excludes unprovided costs.",
    }


REGISTRY = {
    "compare_costs": (
        CostComparison,
        compare_costs,
        "Compare total costs over a horizon. All amounts must use the same currency; label assumed inputs in your answer.",
    ),
    "weighted_scores": (
        WeightedMatrix,
        weighted_scores,
        "Calculate weighted option scores. Higher scores are better. Weights and scores are subjective assumptions, not measured evidence.",
    ),
}
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema.model_json_schema(),
        },
    }
    for name, (schema, _, description) in REGISTRY.items()
]


def execute_tool(name: str, raw_arguments: str) -> dict:
    if name not in REGISTRY:
        raise ValueError("Unknown tool")
    arguments = json.loads(raw_arguments)
    return REGISTRY[name][1](arguments)
