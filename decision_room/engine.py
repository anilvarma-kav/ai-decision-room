"""Bounded deliberation: independent analysis, peer review, structured synthesis."""

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from decision_room.config import providers
from decision_room.models import DecisionRequest, Memo, Opinion, Review
from decision_room.prompts import BASE, JUDGE, ROLES
from decision_room.tools import TOOL_SCHEMAS, execute_tool, weighted_scores

Emitter = Callable[[dict], Awaitable[None]]


class RunError(Exception):
    """A safe error message suitable for the event stream."""


async def model_completion(**kwargs):
    # Import lazily so the keyless demo never needs to initialize a provider client.
    import litellm

    litellm.suppress_debug_info = True
    return await litellm.acompletion(**kwargs)


def parse_output(content: str, schema: type[BaseModel]) -> dict:
    content = content.strip()
    if content.startswith("```") and content.endswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return schema.model_validate_json(content).model_dump()


class Deliberation:
    def __init__(self, request: DecisionRequest, emit: Emitter, completion=model_completion):
        self.request = request
        self.emit = emit
        self.completion = completion
        self.calls: list[dict] = []
        self.tool_calls: list[dict] = []
        self.failures: list[dict] = []
        self.started = time.monotonic()
        available = providers()
        self.models = {
            role: available[p].model for role, p in zip(ROLES, request.models, strict=True)
        }

    async def ask(
        self, role: str, phase: str, prompt: str, schema: type[BaseModel], tools: bool = False
    ) -> dict:
        model = self.models.get(role, self.models["strategist"])
        system = BASE + (JUDGE if role == "editor" else ROLES[role])
        messages: list[dict] = [
            {
                "role": "system",
                "content": system + "\nJSON schema:\n" + json.dumps(schema.model_json_schema()),
            },
            {"role": "user", "content": prompt},
        ]
        await self.emit({"type": "agent_start", "role": role, "phase": phase, "model": model})
        # Three requests for analysis (including tool responses / one JSON repair),
        # two for review or synthesis. Provider retries are explicitly disabled.
        repaired = False
        for attempt in range(3 if tools else 2):
            call_start = time.monotonic()
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": 1800,
                "timeout": 55,
                "num_retries": 0,
            }
            if model.startswith("ollama"):
                kwargs["api_base"] = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
            if tools and attempt < 2:
                kwargs["tools"] = TOOL_SCHEMAS
                kwargs["tool_choice"] = "auto"
            try:
                response = await asyncio.wait_for(self.completion(**kwargs), timeout=60)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise RunError(
                    "Provider request failed or timed out. Check the selected model and credentials."
                ) from exc
            usage = getattr(response, "usage", None)
            cost = None
            try:
                from litellm import completion_cost

                cost = completion_cost(completion_response=response)
            except Exception:
                pass  # Unknown price must remain unknown, not become zero.
            call = {
                "role": role,
                "phase": phase,
                "model": model,
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
                "cost_usd": cost,
                "latency_ms": round((time.monotonic() - call_start) * 1000),
            }
            self.calls.append(call)
            await self.emit({"type": "usage", **call})
            message = response.choices[0].message
            if message.tool_calls:
                if not tools or attempt >= 2:
                    raise RunError("Model exceeded the tool-call limit.")
                if len(message.tool_calls) > 4:
                    raise RunError("Model requested too many tools in one response.")
                messages.append(message.model_dump(exclude_none=True))
                for tool_call in message.tool_calls:
                    name = tool_call.function.name
                    arguments = {"unparsed": tool_call.function.arguments}
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        result = execute_tool(name, tool_call.function.arguments)
                    except (ValueError, TypeError, ValidationError):
                        result = {
                            "error": "Invalid arguments or unknown tool. Use the provided schema."
                        }
                    record = {"role": role, "name": name, "arguments": arguments, "result": result}
                    self.tool_calls.append(record)
                    await self.emit({"type": "tool", **record})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": name,
                            "content": json.dumps(result),
                        }
                    )
                continue
            try:
                result = parse_output(message.content or "", schema)
                if schema is Memo:
                    weighted_scores(result["matrix"])
                return result
            except (ValueError, ValidationError):
                if repaired:
                    break
                repaired = True
                messages.extend(
                    [
                        {"role": "assistant", "content": (message.content or "")[:14000]},
                        {
                            "role": "user",
                            "content": "The JSON failed validation. Return a complete valid object matching the schema. Match every matrix row to the number of criteria. No extra keys.",
                        },
                    ]
                )
        raise RunError("Model did not return a valid structured result within the request limit.")

    async def parallel(
        self, phase: str, prompt_by_role: dict[str, str], schema, tools=False
    ) -> dict:
        async def one(role, prompt):
            try:
                result = await self.ask(role, phase, prompt, schema, tools)
                await self.emit(
                    {"type": phase, "role": role, "model": self.models[role], "data": result}
                )
                return role, result
            except RunError as exc:
                failure = {"role": role, "phase": phase, "message": str(exc)}
                self.failures.append(failure)
                await self.emit({"type": "agent_error", **failure})
                return role, None

        tasks = [asyncio.create_task(one(r, p)) for r, p in prompt_by_role.items()]
        try:
            results = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return {r: result for r, result in results if result is not None}

    async def run(self) -> dict:
        brief = json.dumps({"question": self.request.question, "context": self.request.context})
        await self.emit({"type": "phase", "phase": "opinion", "label": "Independent perspectives"})
        opinions = await self.parallel("opinion", {r: brief for r in ROLES}, Opinion, tools=True)
        if len(opinions) < 2:
            raise RunError(
                "At least two perspectives must succeed. The decision was not synthesized."
            )
        await self.emit({"type": "phase", "phase": "review", "label": "Challenge & refine"})
        reviews = await self.parallel(
            "review",
            {
                r: brief
                + "\nInitial positions:\n"
                + json.dumps(opinions)
                + "\nChallenge another position, acknowledge a useful point, and state your revised position."
                for r in opinions
            },
            Review,
        )
        await self.emit({"type": "phase", "phase": "memo", "label": "Decision memo"})
        # Reuse a provider that produced a valid initial perspective.
        self.models["editor"] = self.models[next(iter(opinions))]
        memo = await self.ask(
            "editor",
            "memo",
            brief
            + "\nOpinions:\n"
            + json.dumps(opinions)
            + "\nReviews:\n"
            + json.dumps(reviews)
            + "\nMissing perspectives / failed reviews:\n"
            + json.dumps(self.failures),
            Memo,
        )
        ranking = weighted_scores(memo["matrix"])
        await self.emit({"type": "memo", "data": memo, "ranking": ranking})
        return {
            "mode": "live",
            "question": self.request.question,
            "context": self.request.context,
            "models": self.models,
            "opinions": opinions,
            "reviews": reviews,
            "memo": memo,
            "ranking": ranking,
            "calls": self.calls,
            "tools": self.tool_calls,
            "failures": self.failures,
            "duration_ms": round((time.monotonic() - self.started) * 1000),
        }
