# Changelog

All notable changes to the `syttra` Python SDK. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [0.2.0] — 2026-05-05

Adds first-class support for the watcher feature (page-value monitors with cron schedules, trigger conditions, and email or webhook delivery). Backwards-compatible — existing job-related calls keep working unchanged.

### Added

- Watcher methods on `Syttra`:
  - `list_watchers(cursor=...)` — cursor-paginated, newest first.
  - `get_watcher(watcher_id)` — single watcher with the latest extracted value + last-checked / last-changed timestamps.
  - `create_watcher(...)` — create a watcher with name, URL, selector (CSS or XPath), cron schedule, trigger config, and notification channels (email + webhook).
  - `update_watcher(watcher_id, ...)` — partial PATCH; only fields you pass are touched. `clear_webhook=True` wipes the webhook URL.
  - `delete_watcher(watcher_id)` — hard delete; cascades to snapshot history.
  - `get_watcher_history(watcher_id, cursor=...)` — append-only timeline of every fetch (success + failure rows; failures carry `error`, `value=None`).
  - `test_watcher_selector(...)` — stateless dry-run that fetches a URL and applies a selector without persisting anything. Useful for "is my selector right?" before saving.
  - `pick_watcher_screenshot(...)` — render a URL in headless Chromium server-side; returns a base64 PNG + bounding boxes of every visible text-bearing element with a generated stable CSS selector. Powers the dashboard's visual selector picker.
- Typed models for the new endpoints:
  - `Watcher`, `WatcherList`, `WatcherSnapshot`, `WatcherHistory`
  - `TestSelectorResult`
  - `ScreenshotPickerResult`, `ScreenshotPickerElement`
  - `SelectorType` and `TriggerType` literals (`"css"`/`"xpath"` and `"changes"`/`"below"`/`"above"`/`"contains"`/`"not_contains"`).
- `Plan` model gains `watchers_max_count` + `watchers_min_interval_seconds` (default 0 / 900 — fail-closed for older API responses) so SDK callers can reason about plan tier limits programmatically.

### Notes

- The watcher API enforces tier limits at the route layer:
  - `403 feature_not_in_plan` (mapped to `Forbidden`) — Free tier doesn't include watchers.
  - `403 watcher_limit_reached` (mapped to `Forbidden`) — at or above the plan's count cap.
  - `400 schedule_too_fast` (mapped to `InvalidRequest`) — the cron's smallest gap is below the plan's minimum interval.
  - `503 picker_failed` (mapped to `ServerError`) — screenshot picker couldn't render the URL.
  All carry the typed `.code` field so caller code can branch on the specific reason without parsing messages.
- Trigger conditions fire **edge-only**: a `below 1.30` watcher fires once when the value crosses from `>=1.30` to `<1.30`, not on every check while the value stays low.

## [0.1.0] — 2026-05-01

First real release. The 0.0.x line was a name-reservation placeholder; importing it printed a `FutureWarning` and exposed nothing useful. That warning is gone in this release.

### Added

- `Syttra` synchronous client covering the public API:
  - `create_job` / `get_job` / `list_jobs` / `delete_job`
  - `get_job_result` (returns the raw markdown/text body with a sensible filename parsed from `Content-Disposition`)
  - `wait_for_job` — polls until terminal, with a configurable interval and timeout
  - `get_usage` — monthly page-quota state, including the user's plan
  - `preview_sitemap` — discover URLs from `sitemap.xml` (or a shallow crawl fallback)
  - `list_plans` — the public pricing-plans list, unauthenticated
- Typed response models (Pydantic v2): `Job`, `JobCreated`, `JobList`, `JobListItem`, `JobResult`, `Usage`, `UsagePlan`, `Plan`, `SitemapPreview`, `JobProgress`, `JobLinks`, plus the `CrawlMode` and `ExportFormat` enums.
- Structured exceptions per HTTP status:
  - `InvalidRequest` (400), `Unauthorized` (401), `QuotaExceeded` (402), `Forbidden` (403), `NotFound` (404), `Conflict` (409), `PayloadTooLarge` (413), `RateLimited` (429), `ServerError` (5xx)
  - All inherit from `ApiError`, which inherits from `SyttraError`. Carries `.status`, `.code`, `.message`, `.details`, `.request_id`.
  - `TransportError` for network-level failures (timeout, DNS, refused connection).
- Configurable retry policy (`RetryPolicy`):
  - Retries `429` / `502` / `503` / `504` by default with exponential backoff, capped at 8s.
  - Honours `Retry-After` headers.
  - `retry_on_5xx=True` opt-in for retrying every 5xx.
- `SYTTRA_API_KEY` environment-variable fallback when `api_key=` isn't passed.
- Context-manager support (`with Syttra(...) as client:`) for deterministic connection-pool cleanup.
- `User-Agent: syttra-python/<version>` on every request.
- PEP 561 `py.typed` marker — downstream type-checkers pick up the SDK's annotations.

### Changed

- Removed the placeholder `FutureWarning` from import.
- `pyproject.toml` development status: `1 - Planning` → `4 - Beta`.

## [0.0.1] — 2026-04-29

Name-reservation placeholder on PyPI. Importing emitted a `FutureWarning` directing users to the REST API.
