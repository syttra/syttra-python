"""End-to-end tests of the public client surface, using respx.

We mount mocked transports on the ``Syttra`` instance's underlying
``httpx.Client`` and assert that:

- Each method targets the right endpoint with the right method/body.
- The response is parsed into the correct typed model.
- Auth header + user-agent flow through on every request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
import respx

from syttra import (
    ApiError,
    CrawlMode,
    NotFound,
    QuotaExceeded,
    Syttra,
    SyttraError,
    Unauthorized,
)


def _job_status_payload(status: str = "pending") -> dict:
    return {
        "job_id": str(uuid4()),
        "user_id": str(uuid4()),
        "status": status,
        "progress": {"pages_crawled": 0, "pages_total": None, "percent": 0.0},
        "config": {"mode": "single", "max_pages": 50},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "expires_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "links": {"self": "/v1/jobs/x", "result": "/v1/jobs/x/result"},
    }


# ---------------------------------------------------------------------------
# Auth + headers
# ---------------------------------------------------------------------------


@respx.mock
def test_attaches_bearer_and_user_agent(base_url: str, client: Syttra) -> None:
    route = respx.post(f"{base_url}/v1/jobs").mock(
        return_value=httpx.Response(
            202,
            json={
                "job_id": str(uuid4()),
                "user_id": str(uuid4()),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": datetime.now(timezone.utc).isoformat(),
                "links": {"self": "/v1/jobs/x", "result": "/v1/jobs/x/result"},
            },
        )
    )

    client.create_job(url="https://example.com")

    assert route.called
    headers = route.calls.last.request.headers
    assert headers["Authorization"] == "Bearer sk_test_unit"
    assert headers["User-Agent"].startswith("syttra-python/")


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYTTRA_API_KEY", raising=False)
    with pytest.raises(SyttraError, match="API key is required"):
        Syttra()


def test_picks_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYTTRA_API_KEY", "sk_test_from_env")
    # Just constructing should not raise; we don't make a network call.
    Syttra(base_url="http://localhost").close()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@respx.mock
def test_create_job_minimal(base_url: str, client: Syttra) -> None:
    expected_id = str(uuid4())
    route = respx.post(f"{base_url}/v1/jobs").mock(
        return_value=httpx.Response(
            202,
            json={
                "job_id": expected_id,
                "user_id": str(uuid4()),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": datetime.now(timezone.utc).isoformat(),
                "links": {"self": "/v1/jobs/x", "result": "/v1/jobs/x/result"},
            },
        )
    )

    created = client.create_job(url="https://example.com")
    assert str(created.job_id) == expected_id
    body = route.calls.last.request.read().decode()
    assert "single" in body
    assert "https://example.com" in body


@respx.mock
def test_create_job_select_mode_passes_urls(base_url: str, client: Syttra) -> None:
    respx.post(f"{base_url}/v1/jobs").mock(
        return_value=httpx.Response(
            202,
            json={
                "job_id": str(uuid4()),
                "user_id": str(uuid4()),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": datetime.now(timezone.utc).isoformat(),
                "links": {"self": "/v1/jobs/x", "result": "/v1/jobs/x/result"},
            },
        )
    )

    client.create_job(
        url="https://example.com",
        mode=CrawlMode.SELECT,
        urls=["https://example.com/a", "https://example.com/b"],
    )

    body = respx.calls.last.request.read().decode()
    assert "select" in body
    assert "/a" in body and "/b" in body


@respx.mock
def test_get_job_returns_typed_model(base_url: str, client: Syttra) -> None:
    payload = _job_status_payload(status="running")
    respx.get(f"{base_url}/v1/jobs/{payload['job_id']}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    job = client.get_job(payload["job_id"])
    assert job.status == "running"
    assert job.progress.percent == 0.0


@respx.mock
def test_list_jobs_passes_filters(base_url: str, client: Syttra) -> None:
    respx.get(f"{base_url}/v1/jobs").mock(
        return_value=httpx.Response(
            200,
            json={"items": [], "next_cursor": None, "has_more": False},
        )
    )

    client.list_jobs(limit=20, status="completed")

    request = respx.calls.last.request
    assert "limit=20" in str(request.url)
    assert "status=completed" in str(request.url)


@respx.mock
def test_get_job_result_extracts_filename_from_disposition(base_url: str, client: Syttra) -> None:
    job_id = uuid4()
    respx.get(f"{base_url}/v1/jobs/{job_id}/result").mock(
        return_value=httpx.Response(
            200,
            text="# Hello\n",
            headers={
                "Content-Type": "text/markdown",
                "Content-Disposition": 'attachment; filename="job-abc.md"',
            },
        )
    )

    result = client.get_job_result(job_id)
    assert result.body == "# Hello\n"
    assert result.filename == "job-abc.md"
    assert result.content_type == "text/markdown"


@respx.mock
def test_get_job_result_falls_back_when_no_filename(base_url: str, client: Syttra) -> None:
    job_id = uuid4()
    respx.get(f"{base_url}/v1/jobs/{job_id}/result").mock(
        return_value=httpx.Response(200, text="plain", headers={"Content-Type": "text/plain"})
    )
    result = client.get_job_result(job_id)
    assert result.filename == f"job-{job_id}.txt"


@respx.mock
def test_delete_job_targets_correct_path(base_url: str, client: Syttra) -> None:
    job_id = uuid4()
    route = respx.delete(f"{base_url}/v1/jobs/{job_id}").mock(return_value=httpx.Response(204))
    client.delete_job(job_id)
    assert route.called


# ---------------------------------------------------------------------------
# wait_for_job
# ---------------------------------------------------------------------------


@respx.mock
def test_wait_for_job_polls_until_terminal(base_url: str, client: Syttra) -> None:
    job_id = uuid4()
    states = iter(["running", "running", "completed"])

    def _resp(request: httpx.Request) -> httpx.Response:
        payload = _job_status_payload(status=next(states))
        payload["job_id"] = str(job_id)
        return httpx.Response(200, json=payload)

    respx.get(f"{base_url}/v1/jobs/{job_id}").mock(side_effect=_resp)

    final = client.wait_for_job(job_id, poll_interval_seconds=0.0, timeout_seconds=5.0)
    assert final.status == "completed"


@respx.mock
def test_wait_for_job_raises_timeout(base_url: str, client: Syttra) -> None:
    job_id = uuid4()
    payload = _job_status_payload(status="running")
    payload["job_id"] = str(job_id)
    respx.get(f"{base_url}/v1/jobs/{job_id}").mock(return_value=httpx.Response(200, json=payload))

    with pytest.raises(TimeoutError, match=str(job_id)):
        client.wait_for_job(job_id, poll_interval_seconds=0.0, timeout_seconds=0.0)


# ---------------------------------------------------------------------------
# Errors mapped to typed subclasses
# ---------------------------------------------------------------------------


@respx.mock
def test_401_maps_to_unauthorized(base_url: str, client: Syttra) -> None:
    respx.get(f"{base_url}/v1/usage").mock(
        return_value=httpx.Response(
            401,
            json={
                "error": {
                    "code": "invalid_api_key",
                    "message": "Bad token",
                    "request_id": "req_abc",
                }
            },
        )
    )

    with pytest.raises(Unauthorized) as exc:
        client.get_usage()
    assert exc.value.status == 401
    assert exc.value.code == "invalid_api_key"
    assert exc.value.request_id == "req_abc"


@respx.mock
def test_402_maps_to_quota_exceeded(base_url: str, client: Syttra) -> None:
    respx.post(f"{base_url}/v1/jobs").mock(
        return_value=httpx.Response(
            402,
            json={
                "error": {
                    "code": "quota_exceeded",
                    "message": "Out of pages this month",
                    "details": {"used": 100, "quota": 100},
                }
            },
        )
    )

    with pytest.raises(QuotaExceeded) as exc:
        client.create_job(url="https://example.com")
    assert exc.value.details == {"used": 100, "quota": 100}


@respx.mock
def test_404_maps_to_not_found(base_url: str, client: Syttra) -> None:
    respx.get(f"{base_url}/v1/jobs/missing").mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "not_found", "message": "no such job"}},
        )
    )
    with pytest.raises(NotFound):
        client.get_job("missing")


@respx.mock
def test_unparseable_error_body_falls_back_to_generic(base_url: str, client: Syttra) -> None:
    respx.get(f"{base_url}/v1/usage").mock(
        return_value=httpx.Response(503, text="<html>Bad Gateway</html>")
    )

    # 503 is in the default retryable set — exhaust retries first,
    # then assert we surface the (generic) ApiError. With max_attempts=3
    # and zero-backoff retry policy, the test still completes fast.
    with pytest.raises(ApiError) as exc:
        client.get_usage()
    assert exc.value.status == 503
    assert exc.value.code == "unknown_error"


# ---------------------------------------------------------------------------
# Usage / sitemap / plans
# ---------------------------------------------------------------------------


@respx.mock
def test_get_usage(base_url: str, client: Syttra) -> None:
    respx.get(f"{base_url}/v1/usage").mock(
        return_value=httpx.Response(
            200,
            json={
                "used": 50,
                "quota": 100,
                "remaining": 50,
                "period_start": datetime.now(timezone.utc).isoformat(),
                "period_end": datetime.now(timezone.utc).isoformat(),
                "plan": {"slug": "free", "name": "Free"},
            },
        )
    )

    usage = client.get_usage()
    assert usage.used == 50
    assert usage.plan is not None
    assert usage.plan.slug == "free"


@respx.mock
def test_preview_sitemap(base_url: str, client: Syttra) -> None:
    respx.get(f"{base_url}/v1/sitemap/preview").mock(
        return_value=httpx.Response(
            200,
            json={
                "urls": ["https://x.com/a"],
                "source": "sitemap",
                "count": 1,
                "capped": False,
                "assets_filtered": 4,
            },
        )
    )
    preview = client.preview_sitemap("https://x.com")
    assert preview.urls == ["https://x.com/a"]
    assert preview.assets_filtered == 4


@respx.mock
def test_list_plans_unwraps_items(base_url: str, client: Syttra) -> None:
    respx.get(f"{base_url}/v1/plans").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "slug": "free",
                        "name": "Free",
                        "tagline": "-",
                        "price_eur_monthly_cents": 0,
                        "monthly_page_quota": 100,
                        "max_concurrent_jobs": 1,
                        "features": [],
                        "sort_order": 10,
                    }
                ]
            },
        )
    )
    plans = client.list_plans()
    assert len(plans) == 1
    assert plans[0].slug == "free"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def test_can_be_used_as_context_manager() -> None:
    with Syttra(api_key="sk_test_x", base_url="http://localhost") as client:
        assert client is not None
    # No assertion — the test is "doesn't raise on close".
