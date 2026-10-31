"""Score the analyzer against evals/cases.py.

    LLM_PROVIDER=mock      python -m evals.run_eval    # keyword baseline, no API key
    LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... python -m evals.run_eval

Put both numbers in your README: "baseline X% -> LLM Y%".
"""
from __future__ import annotations

import asyncio

from app.analyzer import build_analyzer
from app.config import get_settings
from app.logtools import clean_log, extract_failure_context, redact_secrets
from evals.cases import CASES


async def main() -> None:
    settings = get_settings()
    analyzer = build_analyzer(settings)
    correct = 0
    print(f"provider={settings.llm_provider} model={settings.llm_model}\n")
    print(f"{'case':28} {'expected':20} {'got':20} ok")
    for case in CASES:
        ctx = extract_failure_context(redact_secrets(clean_log(case["log"])))
        result = await analyzer.analyze(workflow="eval", job=case["id"], step="eval", context=ctx.text)
        ok = result.category.value == case["expected_category"]
        correct += ok
        print(f"{case['id']:28} {case['expected_category']:20} {result.category.value:20} {'Y' if ok else 'N'}")
    print(f"\ncategory accuracy: {correct}/{len(CASES)} = {correct / len(CASES):.0%}")


if __name__ == "__main__":
    asyncio.run(main())
