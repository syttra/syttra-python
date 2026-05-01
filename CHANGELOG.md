# Changelog

All notable changes to the `syttra` Python SDK. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

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
