"""Explicitly labeled, deterministic examples. Never a fallback for live failures."""

import asyncio
import json
import time
from pathlib import Path

from decision_room.models import Memo, Opinion, Review
from decision_room.tools import compare_costs, weighted_scores

FIXTURES = Path(__file__).parent / "fixtures"


def scenario(name: str) -> dict:
    if name not in {"search", "hosting", "support"}:
        raise ValueError("Unknown scenario")
    return json.loads((FIXTURES / f"{name}.json").read_text())


async def replay(name, emit, delay=0.35):
    start = time.monotonic()
    d = scenario(name)
    tools = []
    for phase, source, schema, label in [
        ("opinion", "opinions", Opinion, "Independent perspectives"),
        ("review", "reviews", Review, "Challenge & refine"),
    ]:
        await emit({"type": "phase", "phase": phase, "label": label})
        for role, data in d[source].items():
            await emit(
                {"type": "agent_start", "role": role, "phase": phase, "model": "Curated demo"}
            )
            await asyncio.sleep(delay)
            schema.model_validate(data)
            await emit({"type": phase, "role": role, "model": "Curated demo", "data": data})
            if phase == "opinion" and role == "engineer" and d["cost"]:
                record = {
                    "role": role,
                    "name": "compare_costs",
                    "arguments": d["cost"],
                    "result": compare_costs(d["cost"]),
                }
                tools.append(record)
                await emit({"type": "tool", **record})
    await emit({"type": "phase", "phase": "memo", "label": "Decision memo"})
    await asyncio.sleep(delay)
    Memo.model_validate(d["memo"])
    ranking = weighted_scores(d["memo"]["matrix"])
    record = {
        "role": "editor",
        "name": "weighted_scores",
        "arguments": d["memo"]["matrix"],
        "result": ranking,
    }
    tools.append(record)
    await emit({"type": "tool", **record})
    await emit({"type": "memo", "data": d["memo"], "ranking": ranking})
    return {
        "mode": "demo",
        "question": d["question"],
        "context": d["context"],
        "models": d["models"],
        "opinions": d["opinions"],
        "reviews": d["reviews"],
        "memo": d["memo"],
        "ranking": ranking,
        "calls": [],
        "tools": tools,
        "failures": [],
        "duration_ms": round((time.monotonic() - start) * 1000),
    }
