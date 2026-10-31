"""Pure-stdlib log helpers (easy to unit test, no third-party deps).

Pipeline: clean_log -> redact_secrets -> extract_failure_context -> fingerprint
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

# ---------------------------------------------------------------- cleaning
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
TIMESTAMP_RE = re.compile(r"^\ufeff?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ?", re.MULTILINE)


def clean_log(raw: str) -> str:
    """Strip ANSI colours, GitHub per-line timestamps and progress-bar frames."""
    text = ANSI_RE.sub("", raw).replace("\r\n", "\n")
    text = TIMESTAMP_RE.sub("", text)
    lines = [ln.split("\r")[-1].rstrip() for ln in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# --------------------------------------------------------------- redaction
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
     "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"), "Bearer [REDACTED]"),
    (re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+@"), "[REDACTED]@"),
    (re.compile(
        r"(?i)(\b[\w-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)[\w-]*)"
        r"(\s*[=:]\s*)(\S{8,})"), r"\1\2[REDACTED]"),
]


def redact_secrets(text: str) -> str:
    """Defence in depth: GitHub masks registered secrets, but not everything printed."""
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ------------------------------------------------------ failure extraction
ERROR_RE = re.compile(
    r"##\[error\]|error|exception|traceback|fatal|fail|panic|npm err!|exit code [1-9]|"
    r"cannot find|no such file|not found|permission denied|denied|timed? ?out|out of memory|oomkilled",
    re.IGNORECASE,
)
GENERIC_RE = re.compile(r"process completed with exit code", re.IGNORECASE)


@dataclass
class FailureContext:
    text: str                 # trimmed excerpt that goes to the LLM
    error_lines: list[str]    # distinctive error lines, used for the fingerprint


def extract_failure_context(log: str, before: int = 12, after: int = 6, max_chars: int = 12_000) -> FailureContext:
    """Keep only windows around error lines instead of sending the whole log to the LLM."""
    lines = log.split("\n")
    hits = [i for i, ln in enumerate(lines) if ERROR_RE.search(ln)]
    if not hits:  # nothing recognisable: fall back to the tail of the log
        tail = lines[-60:]
        return FailureContext("\n".join(tail)[-max_chars:], [ln.strip() for ln in tail if ln.strip()][-8:])

    ranges: list[list[int]] = []
    for i in hits:
        start, end = max(0, i - before), min(len(lines), i + after + 1)
        if ranges and start <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    text = "\n...\n".join("\n".join(lines[s:e]) for s, e in ranges)

    if len(text) > max_chars:  # first error is usually the root cause, last is the summary: keep both
        head = max_chars // 3
        text = text[:head] + "\n...[truncated]...\n" + text[-(max_chars - head):]

    seen: set[str] = set()
    error_lines: list[str] = []
    for i in hits:
        ln = lines[i].strip()
        if GENERIC_RE.search(ln) or ln in seen:
            continue
        seen.add(ln)
        error_lines.append(ln)
    error_lines = error_lines[:6] or [ln.strip() for ln in lines if ln.strip()][-8:]
    return FailureContext(text, error_lines)


# ------------------------------------------------------------- fingerprint
_NORMALIZERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "<uuid>"),
    (re.compile(r"0x[0-9a-f]+"), "<hex>"),
    (re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s|sec|secs|seconds|min|minutes)\b"), "<dur>"),
    (re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,64}\b"), "<hash>"),
    (re.compile(r"/home/runner/work/[^/\s]+/[^/\s]+/"), ""),
    (re.compile(r"/tmp/[\w.\-]+"), "/tmp/<tmp>"),
    (re.compile(r"\bline \d+\b"), "line <n>"),
    (re.compile(r":\d+(?::\d+)?\b"), ":<n>"),
    (re.compile(r"\b\d{4,}\b"), "<n>"),
]


def fingerprint(error_lines: list[str]) -> str:
    """Hash of the *normalised* error lines: same bug => same fingerprint across runs.

    Small numbers (exit codes, HTTP statuses) are deliberately kept so that
    "HTTP 401" and "HTTP 500" do not share a cached diagnosis.
    """
    normalised = []
    for ln in error_lines:
        s = ln.lower()
        for pattern, repl in _NORMALIZERS:
            s = pattern.sub(repl, s)
        normalised.append(re.sub(r"\s+", " ", s).strip())
    return hashlib.sha256("\n".join(normalised).encode()).hexdigest()[:16]


# ---------------------------------------------------- LLM-output hygiene
def extract_json_object(text: str) -> dict:
    """Pull the first {...} object out of an LLM reply (tolerates ```json fences)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in LLM output")
    return json.loads(text[start:end + 1])


def sanitize_markdown(text: str) -> str:
    """LLM text ends up in a PR comment: stop it from breaking fences or pinging people."""
    text = text.replace("```", "\x27\x27\x27")
    return re.sub(r"@(?=[A-Za-z0-9_\-])", "@\u200b", text)


# ------------------------------------------------ keyword baseline (eval)
_HEURISTICS: list[tuple[str, re.Pattern[str]]] = [
    ("secrets_permissions", re.compile(
        r"permission denied|unauthorized|forbidden|\b40[13]\b|bad credentials|authentication failed|"
        r"access denied|resource not accessible", re.I)),
    ("dependency", re.compile(
        r"cannot find module|modulenotfounderror|no module named|no matching distribution|"
        r"could not find a version|could not resolve dependenc|npm err! 404", re.I)),
    ("lint", re.compile(r"eslint|flake8|ruff|pylint|prettier|\blint", re.I)),
    ("build_config", re.compile(
        r"failed to solve|dockerfile|invalid workflow|yaml syntax|unable to prepare context|copy failed", re.I)),
    ("infra", re.compile(
        r"timed? ?out|connection refused|econnrefused|econnreset|rate limit|no space left|"
        r"out of memory|oomkilled|could not resolve host|temporary failure", re.I)),
    ("test_failure", re.compile(r"assertionerror|\d+ failed|tests? failed|assert ", re.I)),
]


def heuristic_category(text: str) -> str:
    """Dumb keyword classifier: the baseline your LLM analyzer has to beat."""
    for category, pattern in _HEURISTICS:
        if pattern.search(text):
            return category
    return "unknown"
