import asyncio
import json

import pytest
from litellm import ModelResponse

from decision_room.demo import scenario
from decision_room.engine import Deliberation, RunError
from decision_room.models import DecisionRequest


def response(content=None, tools=None):
    message = {"role": "assistant", "content": content}
    if tools:
        message["tool_calls"] = tools
    return ModelResponse(
        model="gpt-4.1-mini",
        choices=[{"message": message, "finish_reason": "tool_calls" if tools else "stop"}],
        usage={"prompt_tokens": 30, "completion_tokens": 40, "total_tokens": 70},
    )


def request():
    return DecisionRequest(
        question="Should we build or buy search?", mode="live", models=["openai"] * 3
    )


def content_for(kwargs):
    system = kwargs["messages"][0]["content"]
    fixture = scenario("search")
    if '"title": "Memo"' in system:
        return fixture["memo"]
    if '"title": "Review"' in system:
        return fixture["reviews"]["engineer"]
    return fixture["opinions"]["engineer"]


async def test_full_run_propagates_peer_context_and_usage():
    events, prompts = [], []

    async def complete(**kwargs):
        prompts.append(kwargs)
        return response(json.dumps(content_for(kwargs)))

    async def emit(event):
        events.append(event)

    result = await Deliberation(request(), emit, complete).run()
    assert len(result["opinions"]) == len(result["reviews"]) == 3
    assert len(result["calls"]) == 7
    assert sum(c["input_tokens"] for c in result["calls"]) == 210
    assert result["ranking"]["ranking"][0]["name"] == "Managed service"
    assert any("Initial positions" in x["messages"][1]["content"] for x in prompts)
    assert {e["type"] for e in events} >= {"opinion", "review", "memo", "usage"}


async def test_tool_results_are_returned_to_model():
    seen = []

    async def complete(**kwargs):
        seen.append(kwargs)
        if len(seen) == 1:
            return response(
                tools=[
                    {
                        "id": "cost1",
                        "type": "function",
                        "function": {
                            "name": "compare_costs",
                            "arguments": json.dumps(
                                {
                                    "upfront": 100,
                                    "monthly": 10,
                                    "months": 12,
                                    "alternative_monthly": 30,
                                }
                            ),
                        },
                    }
                ]
            )
        assert kwargs["messages"][-1]["role"] == "tool"
        assert json.loads(kwargs["messages"][-1]["content"])["total"] == 220
        return response(json.dumps(scenario("search")["opinions"]["engineer"]))

    async def emit(_):
        pass

    from decision_room.models import Opinion

    engine = Deliberation(request(), emit, complete)
    await engine.ask("engineer", "opinion", "Compare costs", Opinion, tools=True)
    assert len(engine.tool_calls) == 1
    assert len(engine.calls) == 2


async def test_malformed_json_is_repaired_once():
    count = 0

    async def complete(**kwargs):
        nonlocal count
        count += 1
        return response("not JSON")

    async def emit(_):
        pass

    from decision_room.models import Review

    with pytest.raises(RunError, match="valid structured"):
        await Deliberation(request(), emit, complete).ask("skeptic", "review", "Review", Review)
    assert count == 2


async def test_single_failure_is_disclosed_and_two_failures_abort():
    async def emit(_):
        pass

    async def one_failure(**kwargs):
        if "constructive skeptic" in kwargs["messages"][0]["content"]:
            raise RuntimeError("secret provider detail")
        return response(json.dumps(content_for(kwargs)))

    result = await Deliberation(request(), emit, one_failure).run()
    assert len(result["opinions"]) == 2
    assert result["failures"][0]["role"] == "skeptic"
    assert "secret" not in json.dumps(result)

    async def all_fail(**kwargs):
        raise RuntimeError("provider down")

    with pytest.raises(RunError, match="At least two"):
        await Deliberation(request(), emit, all_fail).run()


async def test_cancellation_reaches_all_pending_provider_calls():
    cancelled = []
    ready = asyncio.Event()
    started = 0

    async def complete(**kwargs):
        nonlocal started
        started += 1
        if started == 3:
            ready.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    async def emit(_):
        pass

    task = asyncio.create_task(Deliberation(request(), emit, complete).run())
    await asyncio.wait_for(ready.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(cancelled) == 3


async def test_rejected_tool_preserves_inputs_and_allows_recovery():
    from decision_room.models import Opinion

    calls = 0
    bad_args = {"upfront": -50, "monthly": 2, "months": 12, "alternative_monthly": 10}

    async def complete(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return response(
                tools=[
                    {
                        "id": "bad-cost",
                        "type": "function",
                        "function": {"name": "compare_costs", "arguments": json.dumps(bad_args)},
                    }
                ]
            )
        assert "error" in json.loads(kwargs["messages"][-1]["content"])
        return response(json.dumps(scenario("search")["opinions"]["engineer"]))

    async def emit(_):
        pass

    engine = Deliberation(request(), emit, complete)
    await engine.ask("engineer", "opinion", "Compare costs", Opinion, tools=True)
    assert engine.tool_calls[0]["arguments"] == bad_args
    assert "error" in engine.tool_calls[0]["result"]


async def test_tool_loop_has_a_hard_limit():
    from decision_room.models import Opinion

    calls = 0

    async def complete(**kwargs):
        nonlocal calls
        calls += 1
        return response(
            tools=[
                {
                    "id": f"repeat{calls}",
                    "type": "function",
                    "function": {"name": "unknown", "arguments": "{}"},
                }
            ]
        )

    async def emit(_):
        pass

    with pytest.raises(RunError, match="tool-call limit"):
        await Deliberation(request(), emit, complete).ask(
            "engineer", "opinion", "Compare", Opinion, tools=True
        )
    assert calls == 3
