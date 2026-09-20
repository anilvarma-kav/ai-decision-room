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

[![Try on Hugging Face Spaces](https://img.shields.io/badge/🤗%20Hugging%20Face-Try%20the%20demo-yellow)](https://huggingface.co/spaces/anilvarmakav/ai-decision-room)

**A workspace for exploring technical decisions with three AI perspectives, peer critique, and an inspectable decision memo.**

[Open the hosted app](https://huggingface.co/spaces/anilvarmakav/ai-decision-room) · [Architecture](docs/architecture.md) · [Recorded live result](examples/live-search.md) · [Source on GitHub](https://github.com/anilvarma-kav/ai-decision-room)

Built with **Python, Gradio, LiteLLM, Pydantic, and SQLite**. The strategist, engineer, and skeptic analyze a brief, challenge one another, and pass their findings to an editor that produces a structured recommendation.

## Try the demo — no API keys needed

1. Open [AI Decision Room on Hugging Face](https://huggingface.co/spaces/anilvarmakav/ai-decision-room).
2. Keep **Curated demo** selected and choose an **Example brief**.
3. Click **Open the decision room**.
4. Explore **Decision memo**, **Panel and critique**, and **Audit record**, then download the Markdown memo or JSON record.

The three examples cover AI search, hosting, and customer support. They replay saved responses with local calculations and make no model API calls. For an actual recorded model run, see the [live memo](examples/live-search.md) and [audit record](examples/live-search.json). If the Space is sleeping, allow it to start before using the controls.

## Engineering highlights

| Area | Implementation |
| --- | --- |
| Orchestration | Concurrent initial opinions, concurrent peer critiques, and a final editor |
| Structured output | Pydantic contracts validate opinions, reviews, and the memo |
| Tool use | Bounded cost comparisons and weighted scoring; final rankings computed in Python |
| Failure handling | Request limits, deadlines, and disclosed partial failures; failed runs are not saved |
| Inspectability | Phase updates, model and usage metadata, tool records, SQLite history, and exports |
| Delivery | Gradio UI, automated tests, Docker support, and GitHub Actions deployment to Spaces |

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

For local runs, copy `.env.example` to `.env`, set `ENABLE_LIVE=1`, and add the keys for the providers you want to use. Restart the app after changing environment variables.

```bash
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env`.

```dotenv
ENABLE_LIVE=1
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

Model IDs can be changed with `MODEL_OPENAI`, `MODEL_ANTHROPIC`, `MODEL_GEMINI`, and `MODEL_OLLAMA`. For a local Ollama model, also set `ENABLE_OLLAMA=1` and ensure Ollama is running.

Choose **Live models**, enter a brief, and assign configured providers under **Panel models**. One configured provider can serve all three roles. Cloud API usage is billed by the provider separately from Hugging Face hosting.

## Deploy to Hugging Face Spaces

The public demo is deployed at **[anilvarmakav/ai-decision-room](https://huggingface.co/spaces/anilvarmakav/ai-decision-room)**. Its curated examples work without secrets.

To deploy your own copy, create a **Gradio** Space and upload the repository files, or configure the GitHub workflow described below with your Space ID. The README metadata, `app.py`, and `requirements.txt` provide the build configuration.

### Configure live models on a Space

In your Space's **Settings → Variables and secrets**, use **New secret** for provider credentials:

| Secret | Provider |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic |
| `GEMINI_API_KEY` | Google Gemini |

Add `ENABLE_LIVE=1` as a **variable**, then select only configured providers in the app after it restarts. Model overrides belong in variables. Do not upload a `.env` file or put API keys in public variables. `HF_TOKEN` is a deployment credential and does not replace model provider keys.

Ollama is intended for local use unless you configure a separately reachable Ollama service. A Space cannot connect to the Ollama server on your laptop through `localhost`.

The default Space filesystem is ephemeral. Download results you want to keep; configure durable storage and `DATABASE_PATH` if history must survive rebuilds. See the [Spaces configuration guide](https://huggingface.co/docs/hub/spaces-overview#managing-secrets-and-environment-variables) for secrets and variables.

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

## Design limits

- Roles are prompted perspectives; multiple models do not guarantee correct conclusions. The memo exposes disagreements and assumptions for human review.
- This is a personal workspace with shared decision history, not per-user private storage. Use example briefs on the public demo.
- The app binds to `0.0.0.0` for Spaces and containers. Use deployment access controls when handling private briefs or enabling paid model calls.
- Usage and cost reports depend on provider metadata. Request caps and timeouts do not guarantee a dollar spending limit.

## Automatic deployment from GitHub

The `Deploy to Hugging Face Spaces` workflow syncs `main` to [the hosted app](https://huggingface.co/spaces/anilvarmakav/ai-decision-room) on every push. Add a Hugging Face token with write permission for this Space as the GitHub repository Actions secret `HF_TOKEN`. You can also run the workflow manually from the Actions tab.

The workflow is defined in [`.github/workflows/deploy-space.yml`](https://github.com/anilvarma-kav/ai-decision-room/blob/main/.github/workflows/deploy-space.yml). For a fork, change `huggingface_repo_id` to your own Space. It syncs repository files; configure model provider keys separately in Space secrets. The hosted demo uses CPU Basic.

## Related project

[Model Roundtable](https://github.com/anilvarma-kav/model-roundtable) explores sequential conversations between cloud and local models. [Try its hosted demo](https://huggingface.co/spaces/anilvarmakav/model-roundtable).
