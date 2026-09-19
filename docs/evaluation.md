# Evaluation notes

The current evaluation separates software reliability from decision quality. Passing contract checks does not mean a recommendation is correct.

## Automated reliability checks

Run `uv run pytest -q` for the unit and API integration suite. It covers:

- Correct cost arithmetic and normalized weighted scores.
- Invalid numbers, incomplete matrices, unknown tools, and blank briefs.
- Peer-context propagation and reported token accounting.
- Tool result messages returned to the model.
- One bounded JSON repair and a hard tool-loop limit.
- Recovery from a rejected tool request, preserving its inputs.
- Continued synthesis with one missing role; aborting when fewer than two roles succeed.
- Cancellation reaching all pending provider tasks.
- SSE completion, SQLite persistence, and both export formats.
- Demo provenance, edited-demo rejection, live-mode gating, optional authentication, cross-origin rejection, and concurrent-run rejection.

The tests inject provider responses. They require no API keys and do not claim provider compatibility beyond the recorded live smoke test.

## Offline output contracts

Run `uv run python scripts/evaluate.py`. It checks the three curated scenarios and the committed real result against six invariants: multiple perspectives, reviews for successful roles, retained dissent, next actions plus a revisit condition, reproducible weighted totals, and usage provenance.

This is a small regression set. The checks assess structure, not semantic correctness. In particular, a non-empty disagreement is not necessarily a useful disagreement.

## Browser verification

`scripts/check_ui.py` launches Chromium against the running app and exercises the complete demo workflow. It verifies all three scenarios, tabs, tool output, Markdown and JSON downloads, saved history, stopping a run, the help dialog, and lack of horizontal overflow at 390 pixels. Uncaught page errors fail the run.

The screenshots in `docs/screenshots/01-*` through `05-*` come from this script. `06-live-decision.png` and `07-live-usage.png` display the committed real API result. No model output or usage numbers were substituted for those captures.

## Recorded live smoke test

The mixed OpenAI/Anthropic result in `examples/live-search.json` completed all stages. It includes 11 successful provider responses, 20,880 reported tokens, and six tool attempts. Five tool requests succeeded and one invalid scoring request was rejected. The model recovered after receiving the tool error. The estimated total cost was $0.0515742; wall-clock duration was 55.109 seconds.

This run validated the two configured cloud providers, actual tool continuations, JSON generation, critique context, synthesis, and cost accounting together. It is one example, not a statistical evaluation. The model output, latency, and price estimate may differ on another run. Gemini and Ollama were not exercised by this smoke test.

The original arguments for the rejected tool request were lost in that version’s error branch. The stored record retains that limitation. A subsequent fix and regression test preserve invalid inputs for future runs.

## The next decision-quality experiment

A useful next experiment would use a fixed, versioned set of realistic engineering decisions, each with explicit constraints and intentionally missing facts. Compare the room against a single-model response using the same brief and a comparable token budget.

Have reviewers score anonymized outputs on:

| Dimension            | What a reviewer checks                                                                    |
| -------------------- | ----------------------------------------------------------------------------------------- |
| Constraint adherence | Does the recommendation respect the stated team, timeline, budget, and data restrictions? |
| Grounding            | Are factual claims supported by the brief? Are estimates clearly marked?                  |
| Useful dissent       | Does the output preserve a material unresolved tradeoff?                                  |
| Arithmetic           | Are computed numbers consistent with supplied assumptions?                                |
| Actionability        | Can the proposed next steps resolve a stated uncertainty?                                 |
| Reversibility        | Does the memo explain when to reconsider the decision?                                    |

Repeat runs, record failures and total cost, and report both quality and resource use. No results from this proposed comparison are claimed here.
