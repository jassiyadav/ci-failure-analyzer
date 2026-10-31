"""Prometheus metrics, scraped from GET /metrics."""
from prometheus_client import Counter, Histogram

WEBHOOKS = Counter("ci_analyzer_webhooks_total", "Webhooks received", ["outcome"])
ANALYSES = Counter("ci_analyzer_analyses_total", "Analyses produced", ["category", "source"])
CACHE = Counter("ci_analyzer_cache_total", "Fingerprint cache lookups", ["result"])
LLM_LATENCY = Histogram("ci_analyzer_llm_latency_seconds", "LLM call latency",
                        buckets=(0.5, 1, 2, 4, 8, 16, 32))
LLM_TOKENS = Counter("ci_analyzer_llm_tokens_total", "LLM tokens used", ["direction"])
ERRORS = Counter("ci_analyzer_errors_total", "Errors by stage", ["stage"])
