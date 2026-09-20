---
title: AI Decision Room
emoji: 🧭
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 5.49.1
python_version: 3.12
app_file: app.py
pinned: false
---

# AI Decision Room

Three perspectives analyze a technical tradeoff, challenge one another, and produce one decision memo. The browser interface is built with Gradio and can run locally or as a Hugging Face Space.

The app keeps the original deliberation engine: Pydantic validated model output, bounded tool use, parallel panel calls, peer critique, a final editor, SQLite history, and Markdown/JSON exports.

## Features

- Run three clearly labeled curated demos without API keys.
- Assign OpenAI, Anthropic, Gemini, or Ollama to the strategist, engineer, and skeptic roles.
- Watch each deliberation phase complete through Gradio streaming updates.
- Inspect the final memo, panel opinions, critiques, usage, tool records, and failures.
- Reload recent completed decisions from SQLite.
- Download a readable Markdown memo and full JSON audit record.

## Run locally

Requires Python 3.11 or newer.

```bash
git clone https://github.com/anilvarma-kav/ai-decision-room.git
cd ai-decision-room
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open [http://localhost:7860](http://localhost:7860). The curated demos require no keys.

You can also use the locked development environment:

```bash
uv sync --frozen
uv run python app.py
```

## Enable live models

Copy `.env.example` to `.env`, set `ENABLE_LIVE=1`, and add at least one provider key. Restart the app after changing environment variables.

```dotenv
ENABLE_LIVE=1
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

Model IDs can be changed with `MODEL_OPENAI`, `MODEL_ANTHROPIC`, `MODEL_GEMINI`, and `MODEL_OLLAMA`. For a local Ollama model, also set `ENABLE_OLLAMA=1` and ensure Ollama is running.

Live runs incur provider charges. Roles are prompted perspectives; using different models does not guarantee independent or correct conclusions.

## Deploy to Hugging Face Spaces

1. Create a new **Gradio** Space.
2. Push this repository to the Space repository.
3. Add provider API keys under **Settings → Variables and secrets**.
4. Add `ENABLE_LIVE=1` as a variable if live runs should be available.

`app.py`, the README metadata above, and `requirements.txt` provide the standard Spaces entry point and dependencies. The demo works without any Space secrets.

The free Space filesystem is not durable across rebuilds. Use a persistent storage upgrade and set `DATABASE_PATH` inside that mounted storage if decision history must survive restarts.

## Docker

```bash
docker build -t decision-room .
docker run --rm -p 7860:7860 --env-file .env decision-room
```

## Test

```bash
uv run ruff check .
uv run pytest -q
uv run python scripts/evaluate.py
```

## Architecture

The Gradio handler validates a `DecisionRequest`, then runs either a curated replay or the transport independent `Deliberation` engine. Live initial opinions and reviews run concurrently. The editor receives successful opinions, reviews, and disclosed failures. Completed reports are saved and exported; failed runs are not saved.

See [docs/architecture.md](docs/architecture.md) for the detailed contracts, limits, context flow, and tool behavior.

## Included real run

The repository includes an actual mixed provider result for “Should we build or buy AI search for our SaaS product?”

- [Readable memo](examples/live-search.md)
- [JSON audit record](examples/live-search.json)

The sample is one recorded run, not an accuracy, speed, or price benchmark.
