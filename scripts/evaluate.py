"""Offline contract checks, not a claim about real-world decision quality."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decision_room.demo import replay  # noqa: E402
from decision_room.models import Memo, Opinion, Review  # noqa: E402
from decision_room.tools import weighted_scores  # noqa: E402


def evaluate(report: dict) -> dict:
    memo = Memo.model_validate(report["memo"])
    for opinion in report["opinions"].values():
        Opinion.model_validate(opinion)
    for review in report["reviews"].values():
        Review.model_validate(review)
    checks = {
        "multiple_perspectives": len(report["opinions"]) >= 2,
        "each_successful_role_reviewed": set(report["reviews"]) == set(report["opinions"]),
        "dissent_preserved": bool(memo.disagreements),
        "actionable_structure": len(memo.next_steps) >= 2 and bool(memo.revisit_when),
        "scores_recompute": weighted_scores(memo.matrix.model_dump()) == report["ranking"],
        "usage_provenance": (report["mode"] == "demo" and not report["calls"])
        or (report["mode"] == "live" and bool(report["calls"])),
    }
    return {"mode": report["mode"], "checks": checks, "passed": all(checks.values())}


async def main():
    async def emit(_):
        pass

    results = {
        name: evaluate(await replay(name, emit, delay=0))
        for name in ("search", "hosting", "support")
    }
    live = Path(__file__).resolve().parents[1] / "examples/live-search.json"
    if live.exists():
        results["recorded_live_search"] = evaluate(json.loads(live.read_text()))
    print(json.dumps(results, indent=2))
    if not all(result["passed"] for result in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
