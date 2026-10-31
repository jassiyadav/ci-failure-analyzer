"""FastAPI entrypoint: receives GitHub `workflow_run` webhooks and comments an AI diagnosis."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import metrics
from .analyzer import PROMPT_VERSION, Analysis, build_analyzer
from .cache import Cache
from .comment import JobReport, build_comment
from .config import get_settings
from .github_client import GitHubClient
from .logtools import clean_log, extract_failure_context, fingerprint, redact_secrets
from .security import verify_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ci-analyzer")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()  # fail fast with a clear message instead of a 500 at the first webhook
    app.state.gh = GitHubClient(settings.github_token)
    app.state.cache = Cache(settings.redis_url)
    app.state.analyzer = build_analyzer(settings)
    log.info("started (provider=%s, model=%s, dry_run=%s)", settings.llm_provider, settings.llm_model, settings.dry_run)
    yield
    await app.state.gh.aclose()


app = FastAPI(title="CI Failure Analyzer", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/webhook/github")
async def github_webhook(request: Request, background: BackgroundTasks) -> dict:
    body = await request.body()  # signature must be computed over the RAW bytes
    if not verify_signature(settings.webhook_secret, body, request.headers.get("X-Hub-Signature-256")):
        metrics.WEBHOOKS.labels("bad_signature").inc()
        raise HTTPException(status_code=401, detail="invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return {"status": "pong"}
    if event != "workflow_run":
        metrics.WEBHOOKS.labels("ignored").inc()
        return {"status": "ignored", "reason": f"event {event!r}"}

    payload = json.loads(body)
    run = payload.get("workflow_run", {})
    repo = payload.get("repository", {}).get("full_name", "")
    if payload.get("action") != "completed" or run.get("conclusion") != "failure":
        metrics.WEBHOOKS.labels("ignored").inc()
        return {"status": "ignored", "reason": "not a failed completed run"}
    if settings.allowed_repos and repo not in settings.allowed_repos:
        metrics.WEBHOOKS.labels("repo_not_allowed").inc()
        return {"status": "ignored", "reason": "repo not allowed"}

    # GitHub gives webhooks ~10s to answer: reply now, do the slow work in the background.
    background.add_task(handle_failed_run, request.app.state, payload)
    metrics.WEBHOOKS.labels("accepted").inc()
    return {"status": "accepted"}


async def handle_failed_run(state, payload: dict) -> None:
    repo = payload["repository"]["full_name"]
    run = payload["workflow_run"]
    try:
        jobs = (await state.gh.failed_jobs(repo, run["id"]))[: settings.max_jobs_per_run]
        if not jobs:
            log.info("run %s of %s has no failed jobs to analyse", run["id"], repo)
            return
        reports = [await analyze_job(state, repo, job, run) for job in jobs]
        body = build_comment(run, reports)
        if settings.dry_run:
            log.info("DRY_RUN comment for %s:\n%s", repo, body)
        else:
            await post_comment(state, repo, run, body)
        log.info("analysed run %s of %s (%d job(s))", run["id"], repo, len(reports))
    except Exception:
        metrics.ERRORS.labels("handler").inc()
        log.exception("failed to analyse run %s of %s", run.get("id"), repo)


async def analyze_job(state, repo: str, job: dict, run: dict) -> JobReport:
    step = next((s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"), "unknown")

    raw = await state.gh.job_log(repo, job["id"], settings.max_raw_log_chars)
    cleaned = redact_secrets(clean_log(raw))  # redact BEFORE anything is cached, logged or sent to an LLM
    ctx = extract_failure_context(cleaned, max_chars=settings.max_context_chars)
    fp = fingerprint(ctx.error_lines)
    cache_key = f"analysis:v{PROMPT_VERSION}:{fp}"

    cached = await state.cache.get(cache_key)
    if cached:
        metrics.CACHE.labels("hit").inc()
        analysis, source = Analysis.model_validate_json(cached), "cache"
    else:
        metrics.CACHE.labels("miss").inc()
        analysis = await state.analyzer.analyze(
            workflow=run.get("name", ""), job=job["name"], step=step, context=ctx.text)
        source = "llm"
        if analysis.confidence >= 0.5 and analysis.category.value != "unknown":
            # don't pin a shaky guess in the cache for a week
            await state.cache.set(cache_key, analysis.model_dump_json(), settings.cache_ttl_seconds)

    metrics.ANALYSES.labels(analysis.category.value, source).inc()
    return JobReport(job=job["name"], step=step, analysis=analysis, fingerprint=fp, source=source)


async def post_comment(state, repo: str, run: dict, body: str) -> None:
    prs = run.get("pull_requests") or []  # empty for pushes, manual runs and fork PRs
    if prs:
        for pr in prs:
            await state.gh.comment_on_pr(repo, pr["number"], body)
    else:
        await state.gh.comment_on_commit(repo, run["head_sha"], body)
