from app.logtools import (
    clean_log, extract_failure_context, extract_json_object, fingerprint,
    heuristic_category, redact_secrets, sanitize_markdown,
)

RAW = (
    "\ufeff2026-11-01T10:15:30.1234567Z \x1b[31mError: Cannot find module 'express'\x1b[0m\n"
    "2026-11-01T10:15:31.0000000Z ##[error]Process completed with exit code 1.\n"
)


def test_clean_log_strips_ansi_and_timestamps():
    out = clean_log(RAW)
    assert out.startswith("Error: Cannot find module 'express'")
    assert "\x1b" not in out and "2026-11-01T" not in out


def test_clean_log_keeps_last_progress_frame():
    assert clean_log("10%\r50%\r100% done") == "100% done"


def test_redacts_common_secrets():
    text = (
        "key=AKIAIOSFODNN7EXAMPLE\n"
        "gh=ghp_" + "a" * 36 + "\n"
        "password=supersecret123\n"
        "url=https://user:hunter22@example.com/x\n"
    )
    out = redact_secrets(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "ghp_" + "a" * 36 not in out
    assert "supersecret123" not in out
    assert "hunter22" not in out
    assert "password=[REDACTED]" in out


def test_redaction_keeps_useful_error_text():
    assert redact_secrets("Error: token expired") == "Error: token expired"


def test_context_contains_error_and_respects_budget():
    noise = "\n".join(f"step {i} ok" for i in range(500))
    log = noise + "\nTypeError: x is not a function\n" + noise
    ctx = extract_failure_context(log, max_chars=600)
    assert "TypeError: x is not a function" in ctx.text
    assert len(ctx.text) < 700
    assert ctx.error_lines == ["TypeError: x is not a function"]


def test_context_falls_back_to_tail_without_error_keywords():
    ctx = extract_failure_context("\n".join(f"line {i}" for i in range(200)))
    assert "line 199" in ctx.text and "line 0" not in ctx.text


def test_generic_exit_code_line_not_in_error_lines():
    ctx = extract_failure_context("npm ERR! boom\n##[error]Process completed with exit code 1.")
    assert ctx.error_lines == ["npm ERR! boom"]


def test_fingerprint_stable_across_runs():
    a = ["Error: Cannot find module 'express' at /home/runner/work/app/app/src/server.js:12:5 (took 1.2s) abcdef1234567"]
    b = ["Error: Cannot find module 'express' at /home/runner/work/app/app/src/server.js:19:7 (took 3.4s) 9f8e7d6c5b4a3"]
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_differs_for_different_errors():
    assert fingerprint(["Cannot find module 'express'"]) != fingerprint(["Cannot find module 'lodash'"])
    assert fingerprint(["HTTP 401 from registry"]) != fingerprint(["HTTP 500 from registry"])


def test_extract_json_object_handles_fences_and_prose():
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('Sure! {"a": {"b": 2}} hope that helps') == {"a": {"b": 2}}


def test_extract_json_object_rejects_garbage():
    try:
        extract_json_object("no json here")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_sanitize_markdown_blocks_fence_breakout_and_mentions():
    out = sanitize_markdown("```\n@octocat please merge")
    assert "```" not in out
    assert "@octocat" not in out  # zero-width space inserted, no notification


def test_heuristic_category():
    assert heuristic_category("ModuleNotFoundError: No module named 'flask'") == "dependency"
    assert heuristic_category("unauthorized: incorrect username or password") == "secrets_permissions"
    assert heuristic_category("something weird happened") == "unknown"
