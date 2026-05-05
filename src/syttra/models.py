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
    """Public pricing plan as exposed at ``GET /v1/plans``.

    Watcher limits are exposed alongside the page quota so SDK
    callers can render their own pricing UI without a second call.
    Older API versions may omit these — defaults reflect "no
    watchers" / "15 minutes minimum", same as the migration's
    fail-closed defaults.
    """

    slug: str
    name: str
    tagline: str
    price_eur_monthly_cents: int | None
    monthly_page_quota: int
    max_concurrent_jobs: int
    watchers_max_count: int = 0
    watchers_min_interval_seconds: int = 900
    features: list[str]
    sort_order: int


# ---------------------------------------------------------------------------
# Watchers
# ---------------------------------------------------------------------------


SelectorType = Literal["css", "xpath"]
TriggerType = Literal["changes", "below", "above", "contains", "not_contains"]


class Watcher(BaseModel):
    """A configured page-value watcher.

    The ``last_*`` fields are the worker's denormalised view of the
    most recent successful tick. Failed ticks don't update
    ``last_value`` (so a transient outage doesn't fire spurious
    change-events); they appear in :class:`WatcherHistory` with
    ``error`` populated.
    """

    id: UUID
    name: str
    url: str
    selector: str
    selector_type: SelectorType
    schedule_cron: str
    webhook_url: str | None
    trigger_type: TriggerType
    trigger_value: str | None
    notify_email_enabled: bool
    last_value: str | None
    last_checked_at: datetime | None
    last_changed_at: datetime | None
    created_at: datetime


class WatcherList(BaseModel):
    """Page of watchers from ``list_watchers``."""

    items: list[Watcher]
    next_cursor: str | None
    has_more: bool


class WatcherSnapshot(BaseModel):
    """One row in a watcher's history.

    Successful ticks have ``value`` populated and ``error=None``;
    failed ticks are the inverse — the dashboard timeline shows both
    so a "selector broke for 3 days then recovered" pattern is
    visible without inferring it from gaps.
    """

    id: UUID
    value: str | None
    content_hash: str | None
    fetched_at: datetime
    error: str | None


class WatcherHistory(BaseModel):
    """Page of snapshots from ``get_watcher_history`` (newest first)."""

    items: list[WatcherSnapshot]
    next_cursor: str | None
    has_more: bool


class TestSelectorResult(BaseModel):
    """One-shot dry-run result from ``test_watcher_selector``.

    ``value`` is ``None`` when the selector matched nothing.
    ``match_count`` surfaces "your selector returned 47 elements" so
    the user can tighten — only the first match's text becomes the
    watcher's tracked value once saved.
    """

    value: str | None
    match_count: int
    html_preview: str | None
    final_url: str
    content_type: str | None


class ScreenshotPickerElement(BaseModel):
    """One clickable zone on the screenshot picker.

    Coordinates are in screenshot pixel space (page-relative,
    multiplied by device pixel ratio), so a single CSS scale factor maps every
    overlay correctly regardless of how the image is sized in the
    consuming UI.
    """

    selector: str
    x: int
    y: int
    width: int
    height: int
    text: str
    tag: str


class ScreenshotPickerResult(BaseModel):
    """Result of ``pick_watcher_screenshot``.

    ``screenshot_base64`` is a PNG screenshot of the page, encoded
    as base64. Build a data URL like
    ``data:image/png;base64,{screenshot_base64}`` to render it in a
    browser, or :func:`base64.b64decode` to write to disk.
    """

    screenshot_base64: str
    screenshot_width: int
    screenshot_height: int
    final_url: str
    elements: list[ScreenshotPickerElement]


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
    "ScreenshotPickerElement",
    "ScreenshotPickerResult",
    "SelectorType",
    "SitemapPreview",
    "TestSelectorResult",
    "TriggerType",
    "Usage",
    "UsagePlan",
    "Watcher",
    "WatcherHistory",
    "WatcherList",
    "WatcherSnapshot",
]
