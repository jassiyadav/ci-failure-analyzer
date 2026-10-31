# CI Failure Analyzer

A small service that watches GitHub Actions. When a workflow run fails it downloads the failed job's log,
cleans and redacts it, asks an LLM for a structured diagnosis (category, root cause, fix) and posts it as a
PR or commit comment. Repeated errors are answered from a fingerprint cache instead of calling the LLM again.

```
GitHub Actions run fails
        |  webhook: workflow_run (completed, failure)
        v
FastAPI /webhook/github  --(HMAC verified, 200 immediately)-->  background task
        |
        |-- GitHub API: failed jobs + raw log
        |-- clean -> redact secrets -> keep windows around errors -> fingerprint
        |-- Redis lookup by fingerprint --hit--> reuse diagnosis
        |                              \--miss--> LLM (JSON, validated, 1 retry) --> cache (if confident)
        |-- grounding check: drop quoted log lines that are not really in the log
        '-- PR comment (or commit comment) + Prometheus metrics at /metrics
```

## Quick start (local, ~10 minutes)

```bash
cp .env.example .env              # fill WEBHOOK_SECRET and GITHUB_TOKEN; keep DRY_RUN=true at first
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                         # unit tests (no network needed)
LLM_PROVIDER=mock python -m evals.run_eval   # keyword baseline, no API key needed

docker compose up --build         # app on :8000 + redis
```

Expose it so GitHub can reach you (pick one): `cloudflared tunnel --url http://localhost:8000`,
`ngrok http 8000`, or smee.io.

**Webhook** (repo -> Settings -> Webhooks -> Add): Payload URL `https://<tunnel>/webhook/github`,
content type `application/json`, secret = your `WEBHOOK_SECRET`, event = *Workflow runs* only.

**Token**: a fine-grained personal access token limited to the repos you monitor. It needs Actions (read),
Pull requests (write) and Contents (write, for commit comments). If you get a 403, check these first.

Then copy `demo/broken-scenarios.yml` into the monitored repo, run it from the Actions tab, and watch the
logs of the analyzer. With `DRY_RUN=true` the comment is printed instead of posted; switch it off when happy.

## Design decisions worth explaining in an interview

| Decision | Why |
|---|---|
| Verify `X-Hub-Signature-256` over raw bytes with `hmac.compare_digest` | Only GitHub can trigger analyses; constant-time compare avoids timing leaks |
| Return 200 immediately, analyse in a background task | GitHub gives webhooks about 10 seconds; LLM calls are slower than that |
| Send only windows around error lines (head + tail if still too long) | Cost, latency and quality: the model sees signal, not 20,000 lines |
| Redact secrets *before* caching, logging or calling the LLM | Logs can contain credentials; GitHub's own masking is not complete |
| Treat the log as untrusted input (prompt-injection defence) | A PR author controls log content. The model has no tools, can only produce text, output is schema-validated, `</log>` is escaped |
| Pydantic-validated JSON, coerce unknown categories, 1 retry | LLMs return malformed output sometimes; the service must not crash |
| Grounding check on `relevant_log_lines` | Cheap hallucination guard: quoted evidence must exist in the excerpt |
| Fingerprint = hash of normalised error lines, cache only if confidence >= 0.5 | Saves cost on repeats without pinning a wrong guess for a week. Small numbers are kept so HTTP 401 and 500 differ |
| `PROMPT_VERSION` in the cache key | Changing the prompt must not serve stale answers |
| Sanitise LLM text before posting (fence breakout, @mentions) | The comment is rendered as markdown and can ping people |

## Evaluation (this is what makes the project stand out)

`evals/cases.py` has 7 starter cases. Grow it to 30-40 by breaking your own pipelines
(use `demo/broken-scenarios.yml`), label the correct category yourself, then run:

```bash
LLM_PROVIDER=mock      python -m evals.run_eval   # keyword baseline
LLM_PROVIDER=anthropic python -m evals.run_eval   # needs ANTHROPIC_API_KEY
```

Record both numbers, plus prompt v1 vs v2 or model A vs model B, in a table here. Starter baseline: 6/7 on the
easy cases, and it misses the hard one (`missing-env-var`) because no keyword matches. Real logs are noisier,
so expect the gap to be larger on your bigger set.

## Known limitations / next steps

- `pull_requests` is empty for fork PRs and manual runs, so those get a commit comment instead of a PR comment.
- No persistent history yet. Next: Postgres table (`run_id`, `fingerprint`, `category`, `confidence`, `source`, `latency_ms`).
- Metrics are exposed at `/metrics`; add Prometheus + Grafana to `docker-compose.yml` for dashboards
  (failure categories, cache hit rate, LLM latency, token usage).
- Flaky-test detection: same test failing then passing on re-run of the same commit.
- Slack notification, and a GitHub App instead of a personal token for real deployments.
- Pin exact versions: after installing, run `pip freeze > requirements.lock`.
