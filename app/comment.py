"""Render the PR / commit comment."""
from __future__ import annotations

from dataclasses import dataclass

from .analyzer import Analysis
from .logtools import sanitize_markdown


@dataclass
class JobReport:
    job: str
    step: str
    analysis: Analysis
    fingerprint: str
    source: str  # "llm" or "cache"


def _code(value: str) -> str:
    return "`" + sanitize_markdown(value).replace("`", "\x27") + "`"


def build_comment(run: dict, reports: list[JobReport]) -> str:
    title = _code(run.get("name", "workflow"))
    parts = [f"### \U0001F916 CI failure analysis: {title}", ""]
    for r in reports:
        a = r.analysis
        parts += [
            f"**Job:** {_code(r.job)} · **Failed step:** {_code(r.step)}",
            f"**Category:** `{a.category.value}` · **Confidence:** {a.confidence:.0%}",
            "",
            f"**Root cause:** {sanitize_markdown(a.root_cause)}",
            "",
            f"**Suggested fix:** {sanitize_markdown(a.suggested_fix)}",
            "",
        ]
        if a.relevant_log_lines:
            lines = "\n".join(sanitize_markdown(ln)[:300] for ln in a.relevant_log_lines)
            parts += ["<details><summary>Relevant log lines</summary>", "", "```text", lines, "```", "</details>", ""]
        parts += [f"<sub>fingerprint `{r.fingerprint}` · source: {r.source}</sub>", ""]
    parts.append("_AI-generated analysis. Verify before applying any change._")
    return "\n".join(parts)
