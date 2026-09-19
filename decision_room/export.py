"""Portable decision memos with provenance and the complete audit record."""

import html


def markdown(report: dict) -> str:
    # Escape user/model HTML before emitting Markdown that may be rendered elsewhere.
    def safe(value):
        return html.escape(str(value), quote=False)

    m = report["memo"]
    lines = [
        f"# {safe(m['title'])}",
        "",
        f"Mode: **{report['mode']}** · Created: {report['created_at']}",
        "",
        f"Decision: {safe(report['question'])}",
        "",
        "## Recommendation",
        "",
        safe(m["recommendation"]),
        "",
        safe(m["summary"]),
    ]
    if report["mode"] == "demo":
        lines.extend(
            [
                "",
                "> Curated demo fixture. No live model calls; scores illustrate a hypothetical decision.",
            ]
        )
    for title, field in [
        ("Where the panel agrees", "agreement"),
        ("Unresolved disagreements", "disagreements"),
        ("Next steps", "next_steps"),
    ]:
        lines.extend(["", f"## {title}", ""] + [f"- {safe(x)}" for x in m[field]])
    lines.extend(
        [
            "",
            "## Option scores",
            "",
            "Subjective model scores; weighted totals computed in Python. Higher is better.",
            "",
        ]
    )
    for row in report["ranking"]["ranking"]:
        lines.append(f"- {safe(row['name'])}: {row['score']}/10")
    lines.extend(
        ["", "## Revisit the decision when", "", safe(m["revisit_when"]), "", "## Panel", ""]
    )
    for role, opinion in report["opinions"].items():
        lines.extend(
            [
                f"### {role.title()} · {safe(report['models'][role])}",
                "",
                safe(opinion["recommendation"]),
                "",
                safe(opinion["rationale"]),
                "",
                "Assumptions:",
                "",
            ]
            + [f"- {safe(x)}" for x in opinion["assumptions"]]
        )
        lines.extend(["", "Risks:", ""] + [f"- {safe(x)}" for x in opinion["risks"]])
        if role in report["reviews"]:
            review = report["reviews"][role]
            lines.extend(
                [
                    "",
                    f"Challenge: {safe(review['challenge'])}",
                    "",
                    f"Concession: {safe(review['concession'])}",
                    "",
                    f"Revised position: {safe(review['revised_position'])}",
                    "",
                ]
            )
    if report["failures"]:
        lines.extend(
            ["## Incomplete stages", ""]
            + [f"- {safe(x['role'])}: {safe(x['message'])}" for x in report["failures"]]
        )
    lines.extend(
        [
            "",
            "## Usage",
            "",
            f"Provider calls: {len(report['calls'])}",
            f"Tool executions: {len(report['tools'])}",
            f"Elapsed time: {report['duration_ms'] / 1000:.1f}s",
            "",
            "See the JSON export for per-call tokens, latency, estimated costs, tool inputs, and tool outputs.",
            "",
        ]
    )
    return "\n".join(lines)
