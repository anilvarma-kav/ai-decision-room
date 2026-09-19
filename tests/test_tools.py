import pytest
from pydantic import ValidationError

from decision_room.models import DecisionRequest
from decision_room.tools import compare_costs, execute_tool, weighted_scores


def test_cost_comparison():
    assert (
        compare_costs(
            {"upfront": 12000, "monthly": 200, "months": 12, "alternative_monthly": 1500}
        )["difference"]
        == -3600
    )


def test_weights_are_normalized():
    result = weighted_scores(
        {
            "criteria": [{"name": "Cost", "weight": 3}, {"name": "Speed", "weight": 1}],
            "options": [{"name": "A", "scores": [8, 4]}, {"name": "B", "scores": [5, 9]}],
        }
    )
    assert result["ranking"] == [{"name": "A", "score": 7}, {"name": "B", "score": 6}]


@pytest.mark.parametrize(
    "arguments",
    [
        {"upfront": -1, "monthly": 1, "months": 12, "alternative_monthly": 1},
        {"upfront": float("inf"), "monthly": 1, "months": 12, "alternative_monthly": 1},
        {"upfront": 1, "monthly": 1, "months": 0, "alternative_monthly": 1},
    ],
)
def test_invalid_costs_are_rejected(arguments):
    with pytest.raises(ValidationError):
        compare_costs(arguments)


def test_unknown_tool_is_never_executed():
    with pytest.raises(ValueError):
        execute_tool("__import__", "{}")


def test_mismatched_matrix_is_rejected():
    with pytest.raises(ValidationError):
        weighted_scores(
            {
                "criteria": [{"name": "Cost", "weight": 1}, {"name": "Speed", "weight": 1}],
                "options": [{"name": "A", "scores": [1, 2, 3]}, {"name": "B", "scores": [5, 9]}],
            }
        )


def test_blank_question_is_rejected():
    with pytest.raises(ValidationError):
        DecisionRequest(question=" " * 20)
