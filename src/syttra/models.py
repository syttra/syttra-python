"""Typed models mirroring the Syttra REST API response shapes.

These are Pydantic v2 models — same library the API itself uses —
so callers get full IDE autocomplete + runtime validation. Keep
them in sync with ``services/api/src/api/schemas/*.py`` in the
backend monorepo.

Naming convention: ``Job`` not ``JobResponse`` because in the SDK
context there's no separate request shape on the read side. Where
the API does have a separate request shape, we expose it as a
keyword-only argument on the client method instead of a model so
users don't need to construct anything to make a call.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums (mirror src/core/models.py)
# ---------------------------------------------------------------------------


class CrawlMode(str, Enum):
    """How the crawler should expand from the seed URL."""

    SINGLE = "single"  # crawl just `url`
    FULL = "full"  # start at `url`, follow same-domain links (BFS)
    SELECT = "select"  # crawl exactly the URLs you list


class ExportFormat(str, Enum):
    """Output format for the result file."""

    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    WORD = "word"


JobStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "expired",
]


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class JobLinks(BaseModel):
    """HATEOAS-lite navigation links — useful when you want to keep
    a job ID around and not hardcode URL templates."""

    self_: str = Field(alias="self")
    result: str

    model_config = {"populate_by_name": True}


class JobProgress(BaseModel):
    """Crawl progress within a single job."""

    pages_crawled: int
    pages_total: int | None
    percent: float


class Job(BaseModel):
    """Full job state — what ``get_job`` returns."""

    job_id: UUID
    user_id: UUID
    status: JobStatus
    progress: JobProgress
    config: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime
    error: str | None
    links: JobLinks


class JobCreated(BaseModel):
    """Slim shape returned by ``create_job`` (HTTP 202).

    We intentionally don't return the full :class:`Job` here — the
    backend hasn't finished enqueueing when this comes back, so
    fields like ``progress`` would be misleading. Call
    :meth:`Syttra.get_job` (or :meth:`Syttra.wait_for_job`) for
    the full picture.
    """

    job_id: UUID
    user_id: UUID
    status: JobStatus
    created_at: datetime
    expires_at: datetime
    links: JobLinks


class JobListItem(BaseModel):
    """Slim job entry in a list response."""

    job_id: UUID
    status: JobStatus
    url: str
    created_at: datetime
    links: JobLinks


class JobList(BaseModel):
    """Page of jobs from ``list_jobs``."""

    items: list[JobListItem]
    next_cursor: str | None
    has_more: bool


class JobResult(BaseModel):
    """A completed job's result body, as returned by ``get_job_result``.

    ``body`` is the raw export — markdown or plain text depending on
    the ``format`` you asked for. ``content_type`` and ``filename``
    come from the response headers so you can save it to disk
    without guessing the extension.
    """

    job_id: UUID
    body: str
    content_type: str
    filename: str


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------


class UsagePlan(BaseModel):
    """The plan the calling user is on."""

    slug: str
    name: str


class Usage(BaseModel):
    """Monthly page-quota state — what ``get_usage`` returns."""

    used: int
    quota: int
    remaining: int
    period_start: datetime
    period_end: datetime
    plan: UsagePlan | None = None


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------


class SitemapPreview(BaseModel):
    """Discovered URLs from a site's sitemap (or a shallow crawl
    fallback when no sitemap is found)."""

    urls: list[str]
    source: Literal["sitemap", "shallow_crawl"]
    count: int
    capped: bool
    assets_filtered: int


# ---------------------------------------------------------------------------
# Plans (public)
# ---------------------------------------------------------------------------


class Plan(BaseModel):
    """Public pricing plan as exposed at ``GET /v1/plans``."""

    slug: str
    name: str
    tagline: str
    price_eur_monthly_cents: int | None
    monthly_page_quota: int
    max_concurrent_jobs: int
    features: list[str]
    sort_order: int


__all__ = [
    "CrawlMode",
    "ExportFormat",
    "Job",
    "JobCreated",
    "JobLinks",
    "JobList",
    "JobListItem",
    "JobProgress",
    "JobResult",
    "JobStatus",
    "Plan",
    "SitemapPreview",
    "Usage",
    "UsagePlan",
]
