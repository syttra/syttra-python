"""Retry/backoff behaviour."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from syttra import RateLimited, RetryPolicy, ServerError, Syttra
from syttra._http import RetryPolicy as HttpRetryPolicy

# --- backoff math ----------------------------------------------------------


def test_backoff_grows_exponentially() -> None:
    p = HttpRetryPolicy(
        max_attempts=4,
        initial_backoff_seconds=1.0,
        backoff_multiplier=2.0,
        max_backoff_seconds=10.0,
    )
    assert p.backoff_for_attempt(1, None) == 1.0
    assert p.backoff_for_attempt(2, None) == 2.0
    assert p.backoff_for_attempt(3, None) == 4.0
    # Capped at max_backoff_seconds.
    assert p.backoff_for_attempt(10, None) == 10.0


def test_retry_after_header_wins_over_exponential() -> None:
    p = HttpRetryPolicy(initial_backoff_seconds=1.0, max_backoff_seconds=60.0)
    assert p.backoff_for_attempt(1, retry_after=5.0) == 5.0


def test_retry_after_capped_at_max() -> None:
    p = HttpRetryPolicy(max_backoff_seconds=10.0)
    # Server says wait 99s, but we won't sleep longer than the max.
    assert p.backoff_for_attempt(1, retry_after=99.0) == 10.0


def test_retry_on_5xx_off_by_default() -> None:
    p = HttpRetryPolicy()
    assert p.is_retryable_status(429) is True
    assert p.is_retryable_status(503) is True
    assert p.is_retryable_status(500) is False  # not retried by default


def test_retry_on_5xx_can_be_opted_in() -> None:
    p = HttpRetryPolicy(retry_on_5xx=True)
    assert p.is_retryable_status(500) is True
    assert p.is_retryable_status(599) is True


# --- end-to-end retry behaviour -------------------------------------------


@respx.mock
def test_429_retries_then_succeeds() -> None:
    base = "https://test.syttra.com"
    client = Syttra(
        api_key="sk_test",
        base_url=base,
        retry=RetryPolicy(
            max_attempts=3,
            initial_backoff_seconds=0.0,
            backoff_multiplier=1.0,
            max_backoff_seconds=0.0,
        ),
    )

    success_payload = {
        "used": 0,
        "quota": 100,
        "remaining": 100,
        "period_start": datetime.now(timezone.utc).isoformat(),
        "period_end": datetime.now(timezone.utc).isoformat(),
        "plan": None,
    }
    respx.get(f"{base}/v1/usage").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {}}),
            httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {}}),
            httpx.Response(200, json=success_payload),
        ]
    )

    usage = client.get_usage()
    assert usage.quota == 100


@respx.mock
def test_429_exhausted_raises_rate_limited() -> None:
    base = "https://test.syttra.com"
    client = Syttra(
        api_key="sk_test",
        base_url=base,
        retry=RetryPolicy(
            max_attempts=2,
            initial_backoff_seconds=0.0,
            backoff_multiplier=1.0,
            max_backoff_seconds=0.0,
        ),
    )
    respx.get(f"{base}/v1/usage").mock(
        return_value=httpx.Response(
            429,
            json={"error": {"code": "rate_limited", "message": "slow down"}},
        )
    )

    with pytest.raises(RateLimited):
        client.get_usage()


@respx.mock
def test_500_does_not_retry_by_default() -> None:
    base = "https://test.syttra.com"
    client = Syttra(api_key="sk_test", base_url=base)
    route = respx.get(f"{base}/v1/usage").mock(
        return_value=httpx.Response(
            500,
            json={"error": {"code": "internal_error", "message": "boom"}},
        )
    )

    with pytest.raises(ServerError):
        client.get_usage()
    # Single attempt, not retried.
    assert route.call_count == 1


@respx.mock
def test_500_retries_when_opted_in() -> None:
    base = "https://test.syttra.com"
    client = Syttra(
        api_key="sk_test",
        base_url=base,
        retry=RetryPolicy(
            max_attempts=3,
            initial_backoff_seconds=0.0,
            backoff_multiplier=1.0,
            max_backoff_seconds=0.0,
            retry_on_5xx=True,
        ),
    )
    success_payload = {
        "used": 0,
        "quota": 100,
        "remaining": 100,
        "period_start": datetime.now(timezone.utc).isoformat(),
        "period_end": datetime.now(timezone.utc).isoformat(),
        "plan": None,
    }
    respx.get(f"{base}/v1/usage").mock(
        side_effect=[
            httpx.Response(500, json={"error": {}}),
            httpx.Response(200, json=success_payload),
        ]
    )

    usage = client.get_usage()
    assert usage.used == 0
