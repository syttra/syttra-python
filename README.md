# syttra (Python)

Official Python SDK for [Syttra](https://syttra.com) — the API for clean, AI-ready web content.

```bash
pip install syttra
```

> Looking for the public REST docs? See [syttra.com/docs/rest](https://syttra.com/docs/rest). The full SDK reference lives at [syttra.com/docs/sdk/python](https://syttra.com/docs/sdk/python).

## Quickstart

Create an API key at [syttra.com/dashboard/keys](https://syttra.com/dashboard/keys), then:

```python
from syttra import Syttra

client = Syttra(api_key="sk_live_...")

# 1. Submit a job
job = client.create_job(url="https://en.wikipedia.org/wiki/White_House")

# 2. Wait for it to finish (polls in the background)
finished = client.wait_for_job(job.job_id)

# 3. Download the result
result = client.get_job_result(finished.job_id)
print(result.body)        # markdown by default
print(result.filename)    # "job-<id>.md" — ready to write to disk
```

The SDK reads `SYTTRA_API_KEY` from the environment when you don't pass `api_key`, so you can keep the key out of source. `Syttra` is a context manager — use `with Syttra(...) as client:` to close the connection pool deterministically.

## Crawl modes

| Mode | What it does |
| --- | --- |
| `single` (default) | Crawls just the given URL. |
| `full` | Starts at the URL, follows same-domain links breadth-first up to `max_depth` / `max_pages`. |
| `select` | Crawls exactly the URLs you list — typically picked from a sitemap preview. |

```python
from syttra import CrawlMode, Syttra

client = Syttra()

# Discover URLs first
preview = client.preview_sitemap("https://example.com")
chosen = [u for u in preview.urls if "/blog/" in u]

# Crawl just those
job = client.create_job(
    url="https://example.com",
    mode=CrawlMode.SELECT,
    urls=chosen,
)
```

## Errors

Every non-2xx response raises a typed exception. Catch by class instead of by status code:

```python
from syttra import Syttra, QuotaExceeded, Unauthorized, ApiError

try:
    job = client.create_job(url="https://example.com")
except QuotaExceeded as exc:
    print(f"Out of pages: {exc.details}")
except Unauthorized:
    print("API key revoked or wrong env (live vs test)")
except ApiError as exc:
    # Generic fallback. Carries .status, .code, .message, .details, .request_id.
    print(f"{exc.status} {exc.code}: {exc.message} (request_id={exc.request_id})")
```

`request_id` is what we'll ask for if you open a support ticket — copy it straight in.

## Retries

The SDK retries `429` and gateway errors (`502`, `503`, `504`) up to three times with exponential backoff. `Retry-After` headers are honoured. Plain `500` errors are *not* retried by default — they usually mean an actual bug rather than transient flakiness — but you can opt in:

```python
from syttra import RetryPolicy, Syttra

client = Syttra(
    retry=RetryPolicy(
        max_attempts=5,
        retry_on_5xx=True,
    ),
)
```

## Quota

```python
usage = client.get_usage()
print(f"{usage.used} / {usage.quota} pages this month")
print(f"On the {usage.plan.name} plan" if usage.plan else "No plan assigned")
```

`get_usage()` is also handy as a cheap "is my key valid?" check.

## What's in v0.1

- Sync client (`Syttra`) covering jobs, usage, sitemap preview, and the public plans list.
- Typed Pydantic v2 response models — same shapes the API itself uses.
- Structured exceptions per HTTP status (`Unauthorized`, `QuotaExceeded`, …).
- Automatic retries with exponential backoff and `Retry-After` support.
- `wait_for_job` helper for the polling pattern.

## What's coming

- **Async client** in v0.2 — same API, `AsyncSyttra` with `await`.
- **OpenAPI-generated models** so the SDK never lags the API.
- **Dashboard surface** (`/v1/account/api-keys`) once we open Clerk JWT auth to non-browser callers.

Track everything on the [docs site](https://syttra.com/docs/sdk/python).

## Development

```bash
git clone https://github.com/syttra/syttra-python && cd syttra-python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                  # runs the unit suite (no network, mocked via respx)
ruff check src/ tests/  # lint
ruff format src/ tests/ # format
mypy src/syttra         # type check
```

Releasing follows the runbook in [RUNBOOK.md](./RUNBOOK.md).

## License

MIT — see [LICENSE](./LICENSE).
