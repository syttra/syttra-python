# syttra (Python)

> ⚠️ **0.0.x is a name-reservation placeholder.** The real SDK lands in 0.1.0 — see [syttra.com/docs/sdk/python](https://syttra.com/docs/sdk/python) for status.

The Python SDK for [Syttra](https://syttra.com) — the API for clean, AI-ready web content. Until 0.1.0 ships, the REST API at `https://api.syttra.com` is fully usable with any HTTP client.

## Install

```bash
pip install syttra
```

## Status today (0.0.1)

This release reserves the `syttra` name on PyPI so the official SDK can claim it. Importing it prints a one-time warning and exposes nothing useful:

```python
import syttra
# FutureWarning: syttra 0.0.x is a name-reservation placeholder. ...
```

## Hitting the API today

While the SDK isn't out, the public REST API works with any HTTP client. The minimal flow:

```python
import httpx, time

API = "https://api.syttra.com"
KEY = "sk_live_…"  # create one at https://syttra.com/dashboard/keys

# 1. Create a job
r = httpx.post(
    f"{API}/v1/jobs",
    headers={"Authorization": f"Bearer {KEY}"},
    json={"url": "https://en.wikipedia.org/wiki/White_House", "mode": "single"},
)
job_id = r.json()["id"]

# 2. Poll
while True:
    r = httpx.get(f"{API}/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {KEY}"})
    status = r.json()["status"]
    if status in ("completed", "failed"):
        break
    time.sleep(2)

# 3. Download
r = httpx.get(f"{API}/v1/jobs/{job_id}/result", headers={"Authorization": f"Bearer {KEY}"})
print(r.text)
```

Full docs: [syttra.com/docs/rest](https://syttra.com/docs/rest).

## What 0.1.0 will bring

Mirrors the public REST API with typed Pydantic-compatible response models, sync + async clients, retry/backoff, structured errors and a telemetry hook. Tracked in the [private monorepo backlog](https://syttra.com/) — public roadmap on the docs site.

## License

MIT — see [LICENSE](./LICENSE).
