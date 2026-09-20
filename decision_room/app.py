"""Gradio interface for the decision workspace."""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import gradio as gr

from decision_room.config import live_enabled, providers
from decision_room.demo import replay, scenario
from decision_room.engine import Deliberation, RunError
from decision_room.export import markdown
from decision_room.models import DecisionRequest
from decision_room.storage import Store

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

SCENARIOS = {
    "Build or buy AI search": "search",
    "Choose a hosting platform": "hosting",
    "Scale customer support": "support",
}
ROLE_LABELS = {"strategist": "Strategist", "engineer": "Engineer", "skeptic": "Skeptic"}
CSS = """
.gradio-container { max-width: 1180px !important; margin: auto; }
.provenance { padding: .8rem 1rem; border: 1px solid var(--border-color-primary); border-radius: 10px; }
"""


def _store(database_path: str | None = None) -> Store:
    return Store(database_path or os.getenv("DATABASE_PATH", "data/decisions.db"))


def _scenario_id(label: str) -> str:
    return SCENARIOS.get(label, label)


def scenario_fields(label: str):
    data = scenario(_scenario_id(label))
    return data["question"], data["context"]


def mode_controls(mode: str):
    live = mode == "Live models"
    return tuple(gr.update(interactive=live) for _ in range(5))


def _history_choices(store: Store):
    return [
        (f"{item['question'][:70]} · {item['created_at'][:10]}", item["id"])
        for item in store.list()
    ]


def _write_exports(report: dict) -> tuple[str, str]:
    directory = Path(tempfile.mkdtemp(prefix="decision-room-"))
    md_path = directory / f"decision-{report['id']}.md"
    json_path = directory / f"decision-{report['id']}.json"
    md_path.write_text(markdown(report))
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False))
    return str(md_path), str(json_path)


def _panel_markdown(report: dict) -> str:
    sections = []
    for role, opinion in report.get("opinions", {}).items():
        sections.extend(
            [
                f"### {ROLE_LABELS.get(role, role.title())} · `{report['models'][role]}`",
                f"**Recommendation:** {opinion['recommendation']}",
                opinion["rationale"],
                "**Assumptions**\n" + "\n".join(f"- {item}" for item in opinion["assumptions"]),
                "**Risks**\n" + "\n".join(f"- {item}" for item in opinion["risks"]),
            ]
        )
        review = report.get("reviews", {}).get(role)
        if review:
            sections.extend(
                [
                    f"**Challenge:** {review['challenge']}",
                    f"**Concession:** {review['concession']}",
                    f"**Revised position:** {review['revised_position']}",
                ]
            )
        sections.append("---")
    return "\n\n".join(sections)


def _memo_markdown(report: dict) -> str:
    memo = report["memo"]
    ranking = "\n".join(
        f"{index}. **{row['name']}** — {row['score']}/10"
        for index, row in enumerate(report["ranking"]["ranking"], 1)
    )
    return "\n\n".join(
        [
            f"# {memo['title']}",
            f"**Recommendation:** {memo['recommendation']}",
            memo["summary"],
            "## Where the panel agrees\n" + "\n".join(f"- {x}" for x in memo["agreement"]),
            "## Unresolved disagreements\n" + "\n".join(f"- {x}" for x in memo["disagreements"]),
            "## Option scores\n" + ranking,
            "## Next steps\n" + "\n".join(f"- {x}" for x in memo["next_steps"]),
            f"## Revisit when\n{memo['revisit_when']}",
        ]
    )


def _progress_markdown(events: list[dict]) -> str:
    completed = {"opinion": 0, "review": 0, "memo": 0}
    current = "Preparing the room"
    for event in events:
        if event["type"] == "phase":
            current = event["label"]
        elif event["type"] in completed:
            completed[event["type"]] += 1
    return (
        f"**Running: {current}**  \n"
        f"Perspectives: {completed['opinion']}/3 · Reviews: {completed['review']}/3 · Memo: {completed['memo']}/1"
    )


def load_history(identifier: str | None, store: Store):
    report = store.get(identifier) if identifier else None
    if report is None:
        return "Choose a saved decision.", "", "", {}, None, None
    md_path, json_path = _write_exports(report)
    return (
        f"Loaded `{report['id']}` · {report['created_at']}",
        _memo_markdown(report),
        _panel_markdown(report),
        report,
        md_path,
        json_path,
    )


async def stream_decision(
    question: str,
    context: str,
    mode: str,
    scenario_label: str,
    strategist: str,
    engineer: str,
    skeptic: str,
    store: Store,
):
    mode_id = "live" if mode == "Live models" else "demo"
    scenario_id = _scenario_id(scenario_label)
    request = DecisionRequest(
        question=question,
        context=context,
        mode=mode_id,
        scenario=scenario_id,
        models=[strategist, engineer, skeptic],
    )
    if mode_id == "demo":
        fixture = scenario(scenario_id)
        if request.question != fixture["question"] or request.context != fixture["context"]:
            raise gr.Error("Curated demos use the saved brief. Choose Live models to edit it.")
    elif not live_enabled():
        raise gr.Error(
            "Live mode is disabled. Set ENABLE_LIVE=1 in the Space secrets or local .env."
        )
    elif any(not providers()[provider].available for provider in request.models):
        raise gr.Error("A selected provider is missing its API key or configuration.")

    queue: asyncio.Queue = asyncio.Queue()
    identifier = uuid4().hex[:12]

    async def produce():
        try:
            async with asyncio.timeout(300):
                report = (
                    await replay(scenario_id, queue.put)
                    if mode_id == "demo"
                    else await Deliberation(request, queue.put).run()
                )
            report.update(id=identifier, created_at=datetime.now(UTC).isoformat())
            store.save(report)
            await queue.put({"type": "done", "report": report})
        except (RunError, TimeoutError) as exc:
            await queue.put({"type": "error", "message": str(exc) or "The run timed out."})
        except asyncio.CancelledError:
            raise
        except Exception:
            await queue.put(
                {"type": "error", "message": "The run could not be completed. No memo was saved."}
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(produce())
    events: list[dict] = []
    try:
        yield "Starting the decision room…", "", "", {}, None, None, gr.skip()
        while True:
            event = await queue.get()
            if event is None:
                break
            if event["type"] == "error":
                yield f"**Stopped:** {event['message']}", "", "", {}, None, None, gr.skip()
                continue
            if event["type"] == "done":
                report = event["report"]
                md_path, json_path = _write_exports(report)
                provenance = "curated demo; no API calls" if mode_id == "demo" else "live model run"
                yield (
                    f"**Complete.** `{identifier}` · {provenance} · {report['duration_ms'] / 1000:.1f}s",
                    _memo_markdown(report),
                    _panel_markdown(report),
                    report,
                    md_path,
                    json_path,
                    gr.Dropdown(choices=_history_choices(store), value=identifier),
                )
                continue
            events.append(event)
            yield _progress_markdown(events), "", "", {"events": events}, None, None, gr.skip()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def create_app(database_path: str | None = None) -> gr.Blocks:
    store = _store(database_path)
    configured = providers()
    provider_choices = [
        (
            f"{provider.label} · {provider.model}"
            + (" · configured" if provider.available else " · key required"),
            provider.id,
        )
        for provider in configured.values()
    ]
    first_label = next(iter(SCENARIOS))
    first_question, first_context = scenario_fields(first_label)

    with gr.Blocks(
        title="AI Decision Room", theme=gr.themes.Soft(primary_hue="indigo"), css=CSS
    ) as app:
        gr.Markdown(
            "# AI Decision Room\n"
            "Three perspectives analyze a technical tradeoff, challenge one another, and produce one decision memo."
        )
        with gr.Row():
            with gr.Column(scale=1):
                mode = gr.Radio(
                    ["Curated demo", "Live models"], value="Curated demo", label="Run mode"
                )
                scenario_name = gr.Dropdown(
                    list(SCENARIOS), value=first_label, label="Example brief"
                )
                question = gr.Textbox(
                    value=first_question, label="Decision question", lines=3, interactive=False
                )
                context = gr.Textbox(
                    value=first_context, label="Context and constraints", lines=7, interactive=False
                )
                with gr.Accordion("Panel models", open=False):
                    strategist = gr.Dropdown(
                        provider_choices, value="openai", label="Strategist", interactive=False
                    )
                    engineer = gr.Dropdown(
                        provider_choices, value="anthropic", label="Engineer", interactive=False
                    )
                    skeptic = gr.Dropdown(
                        provider_choices, value="openai", label="Skeptic", interactive=False
                    )
                run = gr.Button("Open the decision room", variant="primary")
                gr.Markdown(
                    "<div class='provenance'><b>Demo:</b> saved responses with local calculations and zero API cost. "
                    "<b>Live:</b> uses provider keys stored in your environment or Space secrets.</div>"
                )
            with gr.Column(scale=2):
                status = gr.Markdown("Choose a saved example, then open the decision room.")
                with gr.Tabs():
                    with gr.Tab("Decision memo"):
                        memo = gr.Markdown()
                    with gr.Tab("Panel and critique"):
                        panel = gr.Markdown()
                    with gr.Tab("Audit record"):
                        audit = gr.JSON()
                with gr.Row():
                    markdown_file = gr.File(label="Markdown memo", interactive=False)
                    json_file = gr.File(label="JSON audit record", interactive=False)

        with gr.Accordion("Saved decisions", open=False):
            history = gr.Dropdown(_history_choices(store), label="Recent completed decisions")
            load = gr.Button("Load decision")

        scenario_name.change(scenario_fields, scenario_name, [question, context])
        mode.change(mode_controls, mode, [question, context, strategist, engineer, skeptic])
        outputs = [status, memo, panel, audit, markdown_file, json_file, history]

        async def run_handler(*args):
            async for update in stream_decision(*args, store):
                yield update

        run.click(
            run_handler,
            [question, context, mode, scenario_name, strategist, engineer, skeptic],
            outputs,
            concurrency_limit=1,
            concurrency_id="decision-room",
        )
        load.click(
            lambda identifier: load_history(identifier, store),
            history,
            [status, memo, panel, audit, markdown_file, json_file],
        )
    return app


demo = create_app()
