"""Local-first HTTP API and SSE transport for the decision workspace."""

import asyncio
import contextlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from decision_room.config import live_enabled, providers
from decision_room.demo import replay, scenario
from decision_room.engine import Deliberation, RunError
from decision_room.export import markdown
from decision_room.models import DecisionRequest
from decision_room.storage import Store

STATIC = Path(__file__).parent / "static"


def create_app(database_path: str | None = None) -> FastAPI:
    app = FastAPI(title="AI Decision Room", version="0.1.0", docs_url="/api/docs", redoc_url=None)
    store = Store(database_path or os.getenv("DATABASE_PATH", "data/decisions.db"))
    app.state.store = store
    app.state.running = False

    async def authorize(request: Request):
        token = os.getenv("ROOM_API_TOKEN", "")
        if token and not hmac.compare_digest(
            request.headers.get("Authorization", ""), f"Bearer {token}"
        ):
            raise HTTPException(401, "Enter the workspace access token.")
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                raise HTTPException(403, "Cross-origin requests are not allowed.")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/config")
    async def config():
        return {
            "live_enabled": live_enabled(),
            "auth_required": bool(os.getenv("ROOM_API_TOKEN")),
            "providers": [
                {"id": p.id, "label": p.label, "model": p.model, "available": p.available}
                for p in providers().values()
            ],
            "scenarios": [
                {k: scenario(name)[k] for k in ("id", "label", "question", "context")}
                for name in ("search", "hosting", "support")
            ],
        }

    @app.get("/api/decisions", dependencies=[Depends(authorize)])
    async def decisions():
        return store.list()

    def get_report(identifier):
        report = store.get(identifier)
        if report is None:
            raise HTTPException(404, "Decision not found")
        return report

    @app.get("/api/decisions/{identifier}", dependencies=[Depends(authorize)])
    async def decision(identifier: str):
        return get_report(identifier)

    @app.get("/api/decisions/{identifier}/export", dependencies=[Depends(authorize)])
    async def export(identifier: str, format: str = "markdown"):
        report = get_report(identifier)
        if format == "json":
            return PlainTextResponse(
                json.dumps(report, indent=2),
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="decision-{report["id"]}.json"'
                },
            )
        if format != "markdown":
            raise HTTPException(400, "Choose markdown or json")
        return PlainTextResponse(
            markdown(report),
            headers={"Content-Disposition": f'attachment; filename="decision-{report["id"]}.md"'},
        )

    @app.post("/api/decisions/stream", dependencies=[Depends(authorize)])
    async def stream(body: DecisionRequest):
        if body.mode == "live":
            if not live_enabled():
                raise HTTPException(403, "Live mode is disabled. Set ENABLE_LIVE=1 on the server.")
            if any(not providers()[p].available for p in body.models):
                raise HTTPException(422, "A selected provider is not configured on the server.")
        elif (
            body.question != scenario(body.scenario)["question"]
            or body.context != scenario(body.scenario)["context"]
        ):
            raise HTTPException(
                422, "Demo mode replays the selected example. Choose Live to use your own brief."
            )
        if app.state.running:
            raise HTTPException(429, "A decision is already running. Wait for it to finish.")
        app.state.running = True
        identifier = uuid4().hex[:12]

        async def events():
            queue = asyncio.Queue()

            async def produce():
                try:
                    await queue.put({"type": "started", "id": identifier, "mode": body.mode})
                    async with asyncio.timeout(300):
                        report = (
                            await replay(body.scenario, queue.put)
                            if body.mode == "demo"
                            else await Deliberation(body, queue.put).run()
                        )
                    report.update(id=identifier, created_at=datetime.now(UTC).isoformat())
                    store.save(report)
                    await queue.put({"type": "done", "report": report})
                except (RunError, TimeoutError) as exc:
                    await queue.put(
                        {
                            "type": "error",
                            "message": str(exc) or "The five-minute run limit was reached.",
                        }
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await queue.put(
                        {
                            "type": "error",
                            "message": "The run could not be completed. No decision memo was saved.",
                        }
                    )
                finally:
                    await queue.put(None)

            task = asyncio.create_task(produce())
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=10)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    if event is None:
                        break
                    yield "data: " + json.dumps(event, allow_nan=False) + "\n\n"
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                app.state.running = False

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app()
