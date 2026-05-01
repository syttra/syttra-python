"""Public synchronous client for the Syttra REST API."""

from __future__ import annotations

import os
import re
import time
from typing import Any
from uuid import UUID

import httpx

from . import errors
from ._http import RetryPolicy, SyncTransport
from .models import (
    CrawlMode,
    ExportFormat,
    Job,
    JobCreated,
    JobList,
    JobResult,
    JobStatus,
    Plan,
    SitemapPreview,
    Usage,
)

DEFAULT_BASE_URL = "https://api.syttra.com"
_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled", "expired"})
_FILENAME_RE = re.compile(r'filename="([^"]+)"')


class Syttra:
    """Synchronous client for the Syttra REST API.

    The minimal usage::

        from syttra import Syttra

        client = Syttra(api_key="sk_live_...")
        job = client.create_job(url="https://example.com")
        finished = client.wait_for_job(job.job_id)
        result = client.get_job_result(finished.job_id)
        print(result.body)

    Authentication
    --------------
    The ``api_key`` argument is a Bearer token created in the
    `Syttra dashboard <https://syttra.com/dashboard/keys>`_. If you
    leave it empty, the SDK reads ``SYTTRA_API_KEY`` from the
    environment so 12-factor apps can keep the key out of code.

    Configuration
    -------------
    ``base_url``
        Override the API root. Useful for staging / on-prem.
        Defaults to ``https://api.syttra.com``.
    ``timeout``
        Per-request timeout passed straight to ``httpx``. Default
        30 seconds — long enough for sitemap previews, short
        enough that a hung connection doesn't wedge a worker.
    ``retry``
        See :class:`syttra._http.RetryPolicy`. Tweak when you
        want fewer or more retries, or to opt into 5xx retry.
    ``http_client``
        Bring-your-own ``httpx.Client`` (proxies, mTLS, event hooks,
        etc.). The SDK will *not* close a client it didn't create.

    Lifecycle
    ---------
    :class:`Syttra` works as a context manager so the underlying
    HTTP connection pool is closed deterministically::

        with Syttra(api_key="sk_live_...") as client:
            ...
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = 30.0,
        retry: RetryPolicy | None = None,
        http_client: httpx.Client | None = None,
        user_agent: str | None = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("SYTTRA_API_KEY")
        if not resolved_key:
            raise errors.SyttraError(
                "An API key is required. Pass api_key=... or set "
                "SYTTRA_API_KEY in the environment. Create a key at "
                "https://syttra.com/dashboard/keys."
            )

        from . import __version__

        ua = user_agent or f"syttra-python/{__version__}"

        self._transport = SyncTransport(
            base_url=base_url.rstrip("/"),
            api_key=resolved_key,
            timeout=timeout,
            retry=retry or RetryPolicy(),
            user_agent=ua,
            client=http_client,
        )

    # ---- context-manager support ----------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._transport.close()

    def __enter__(self) -> Syttra:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ---- jobs ----------------------------------------------------------

    def create_job(
        self,
        url: str,
        *,
        mode: CrawlMode | str = CrawlMode.SINGLE,
        export_formats: list[ExportFormat | str] | None = None,
        max_depth: int = 3,
        max_pages: int = 50,
        concurrency: int = 5,
        respect_robots: bool = True,
        check_tos: bool = True,
        urls: list[str] | None = None,
    ) -> JobCreated:
        """Submit a new crawl job.

        See :class:`syttra.CrawlMode` for the three crawl shapes.
        ``urls`` is required when ``mode='select'`` and must be
        omitted otherwise — the API enforces this.
        """
        body: dict[str, Any] = {
            "url": url,
            "mode": _enum_value(mode),
            "max_depth": max_depth,
            "max_pages": max_pages,
            "concurrency": concurrency,
            "respect_robots": respect_robots,
            "check_tos": check_tos,
        }
        if export_formats:
            body["export_formats"] = [_enum_value(f) for f in export_formats]
        if urls is not None:
            body["urls"] = urls

        response = self._transport.request("POST", "/v1/jobs", json_body=body)
        return JobCreated.model_validate(response.json())

    def get_job(self, job_id: str | UUID) -> Job:
        """Fetch the current state of a job."""
        response = self._transport.request("GET", f"/v1/jobs/{job_id}")
        return Job.model_validate(response.json())

    def list_jobs(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        status: JobStatus | None = None,
    ) -> JobList:
        """Page through your jobs (newest first)."""
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if cursor is not None:
            params["cursor"] = cursor
        if status is not None:
            params["status"] = status
        response = self._transport.request("GET", "/v1/jobs", params=params or None)
        return JobList.model_validate(response.json())

    def delete_job(self, job_id: str | UUID) -> None:
        """Remove a job. Idempotent — deleting a missing job is a 404."""
        self._transport.request("DELETE", f"/v1/jobs/{job_id}")

    def get_job_result(
        self,
        job_id: str | UUID,
        *,
        format: ExportFormat | str | None = None,
    ) -> JobResult:
        """Download a finished job's result body.

        The result endpoint returns the raw export bytes (markdown
        or plain text) with a ``Content-Type`` header — not JSON.
        We parse out a sensible filename from the
        ``Content-Disposition`` header so callers can write the
        body straight to disk.
        """
        params = {"format": _enum_value(format)} if format else None
        response = self._transport.request("GET", f"/v1/jobs/{job_id}/result", params=params)
        disposition = response.headers.get("Content-Disposition") or ""
        match = _FILENAME_RE.search(disposition)
        filename = match.group(1) if match else f"job-{job_id}.txt"
        return JobResult(
            job_id=UUID(str(job_id)),
            body=response.text,
            content_type=response.headers.get("Content-Type", "text/plain"),
            filename=filename,
        )

    def wait_for_job(
        self,
        job_id: str | UUID,
        *,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float | None = 600.0,
    ) -> Job:
        """Block until the job reaches a terminal status, then return it.

        Polls every ``poll_interval_seconds`` (default 2s). Terminal
        statuses are completed / failed / cancelled / expired.

        Raises :class:`TimeoutError` if the job hasn't terminated by
        ``timeout_seconds`` (default 10 minutes — leaves room for
        a 1000-page full-site crawl). Pass ``timeout_seconds=None``
        to wait forever.

        The right pattern for most callers is::

            client.create_job(...)
            job = client.wait_for_job(job.job_id)
            if job.status == "completed":
                result = client.get_job_result(job.job_id)
        """
        deadline = (time.monotonic() + timeout_seconds) if timeout_seconds is not None else None
        while True:
            job = self.get_job(job_id)
            if job.status in _TERMINAL_STATUSES:
                return job
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(
                    f"Job {job_id} did not reach a terminal status within "
                    f"{timeout_seconds:.0f}s (last status: {job.status})"
                )
            time.sleep(poll_interval_seconds)

    # ---- usage ---------------------------------------------------------

    def get_usage(self) -> Usage:
        """Return the caller's monthly page-quota state."""
        response = self._transport.request("GET", "/v1/usage")
        return Usage.model_validate(response.json())

    # ---- sitemap -------------------------------------------------------

    def preview_sitemap(self, url: str, *, limit: int | None = None) -> SitemapPreview:
        """Discover URLs from a site's sitemap.

        Falls back server-side to a shallow link crawl when no
        ``sitemap.xml`` is found. Asset URLs (.jpg, .pdf, RSS feeds,
        etc.) are filtered out before the response — the count is
        returned in ``assets_filtered`` so you can decide whether
        to mention it in the UI.
        """
        params: dict[str, Any] = {"url": url}
        if limit is not None:
            params["limit"] = limit
        response = self._transport.request("GET", "/v1/sitemap/preview", params=params)
        return SitemapPreview.model_validate(response.json())

    # ---- plans (public) -----------------------------------------------

    def list_plans(self) -> list[Plan]:
        """Return the public list of pricing plans.

        Same data the marketing ``/pricing`` page renders. The
        endpoint is unauthenticated so this works even if the SDK
        was constructed with an invalid key — useful for "what
        plans does Syttra offer?" before signing up.
        """
        response = self._transport.request("GET", "/v1/plans")
        body = response.json()
        return [Plan.model_validate(p) for p in body.get("items", [])]


def _enum_value(value: Any) -> str:
    """Accept either an enum or a raw string for caller convenience."""
    if hasattr(value, "value"):
        return value.value  # type: ignore[no-any-return]
    return str(value)
