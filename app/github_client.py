"""Thin async wrapper around the few GitHub REST endpoints we need."""
from __future__ import annotations

import httpx


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._http = httpx.AsyncClient(
            base_url="https://api.github.com",
            timeout=30,
            follow_redirects=True,  # job logs are served via a 302 to a signed URL
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def failed_jobs(self, repo: str, run_id: int) -> list[dict]:
        r = await self._http.get(f"/repos/{repo}/actions/runs/{run_id}/jobs",
                                 params={"filter": "latest", "per_page": 100})
        r.raise_for_status()
        return [j for j in r.json().get("jobs", []) if j.get("conclusion") == "failure"]

    async def job_log(self, repo: str, job_id: int, max_chars: int) -> str:
        r = await self._http.get(f"/repos/{repo}/actions/jobs/{job_id}/logs")
        r.raise_for_status()
        return r.text[-max_chars:]  # failures are near the end; cap memory use

    async def comment_on_pr(self, repo: str, number: int, body: str) -> None:
        r = await self._http.post(f"/repos/{repo}/issues/{number}/comments", json={"body": body})
        r.raise_for_status()

    async def comment_on_commit(self, repo: str, sha: str, body: str) -> None:
        r = await self._http.post(f"/repos/{repo}/commits/{sha}/comments", json={"body": body})
        r.raise_for_status()
