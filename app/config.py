"""Settings loaded from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    github_token: str = ""
    webhook_secret: str = ""
    llm_provider: str = "anthropic"          # "anthropic" or "mock" (keyword baseline, no API key)
    llm_model: str = "claude-sonnet-5-5"     # override with LLM_MODEL
    anthropic_api_key: str = ""
    redis_url: str = ""                      # empty -> in-memory cache
    allowed_repos: frozenset[str] = frozenset()  # empty -> allow every repo that signs correctly
    max_raw_log_chars: int = 2_000_000
    max_context_chars: int = 12_000
    max_jobs_per_run: int = 2
    cache_ttl_seconds: int = 7 * 24 * 3600
    dry_run: bool = False                    # log the comment instead of posting it

    def validate(self) -> None:
        missing = []
        if not self.webhook_secret:
            missing.append("WEBHOOK_SECRET")
        if not self.github_token:
            missing.append("GITHUB_TOKEN")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY (or set LLM_PROVIDER=mock)")
        if missing:
            raise RuntimeError("Missing required settings: " + ", ".join(missing))


@lru_cache
def get_settings() -> Settings:
    env = os.environ
    repos = {r.strip() for r in env.get("ALLOWED_REPOS", "").split(",") if r.strip()}
    return Settings(
        github_token=env.get("GITHUB_TOKEN", ""),
        webhook_secret=env.get("WEBHOOK_SECRET", ""),
        llm_provider=env.get("LLM_PROVIDER", "anthropic").lower(),
        llm_model=env.get("LLM_MODEL", "claude-sonnet-5-5"),
        anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
        redis_url=env.get("REDIS_URL", ""),
        allowed_repos=frozenset(repos),
        max_context_chars=int(env.get("MAX_CONTEXT_CHARS", "12000")),
        max_jobs_per_run=int(env.get("MAX_JOBS_PER_RUN", "2")),
        cache_ttl_seconds=int(env.get("CACHE_TTL_SECONDS", str(7 * 24 * 3600))),
        dry_run=_bool(env.get("DRY_RUN")),
    )
