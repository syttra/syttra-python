"""Internal HTTP transport for the Syttra SDK.

Wraps :class:`httpx.Client` with:

- The ``Authorization: Bearer <api-key>`` header on every request.
- A ``User-Agent: syttra-python/<version>`` so the API can attribute
  traffic.
- Bounded retries with exponential backoff for transient failures
  (transport errors, 429, 5xx) — see :class:`RetryPolicy`.
- Mapping of non-2xx responses to typed :mod:`syttra.errors`.

Kept private (leading underscore) because the public surface is the
:class:`syttra.Syttra` client; users shouldn't need to touch httpx
directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from . import errors

# Status codes the SDK retries automatically. Picked deliberately:
# - 429: server is asking us to slow down — backoff and retry.
# - 502/503/504: load balancer / gateway transient failures.
# - 500 is *not* in this list because it usually means an actual bug
#   that retrying won't fix; users can opt in via ``retry_on_5xx`` if
#   they're calling something they know is flaky.
_DEFAULT_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    """Knobs for retry behaviour.

    Defaults are conservative — three tries with exponential backoff
    starting at 0.5s and capped at 8s. Honours ``Retry-After`` when
    the server sends one.
    """

    max_attempts: int = 3
    initial_backoff_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 8.0
    retryable_statuses: frozenset[int] = _DEFAULT_RETRYABLE_STATUSES
    retry_on_5xx: bool = False  # opt-in: retry every 5xx, not just gateway errors

    def is_retryable_status(self, status: int) -> bool:
        if status in self.retryable_statuses:
            return True
        if self.retry_on_5xx and 500 <= status < 600:
            return True
        return False

    def backoff_for_attempt(self, attempt: int, retry_after: float | None) -> float:
        """Return how long to sleep before retry ``attempt`` (1-indexed).

        ``Retry-After`` from the server wins when present — that's
        explicit guidance and ignoring it would just trigger more 429s.
        """
        if retry_after is not None and retry_after > 0:
            return min(retry_after, self.max_backoff_seconds)
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value as seconds (we only support
    the integer form — the HTTP-date form is rare in practice and not
    worth the dependency on a date parser)."""
    if value is None:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _map_error_response(response: httpx.Response) -> errors.ApiError:
    """Build the right typed error from a non-2xx response.

    The API uses a consistent envelope::

        {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}

    Anything else (HTML error pages from a misconfigured proxy,
    truncated bodies) falls back to a generic envelope so we never
    raise a parsing error on top of an HTTP error.
    """
    request_id = response.headers.get("X-Request-ID")
    code = "unknown_error"
    message = f"Request failed ({response.status_code})"
    details: Any | None = None

    try:
        body = response.json()
    except Exception:
        body = None

    if isinstance(body, dict):
        envelope = body.get("error") if isinstance(body.get("error"), dict) else None
        if envelope is not None:
            code = str(envelope.get("code") or code)
            message = str(envelope.get("message") or message)
            details = envelope.get("details")
            request_id = envelope.get("request_id") or request_id

    return errors.from_response(
        status=response.status_code,
        code=code,
        message=message,
        details=details,
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Sync transport
# ---------------------------------------------------------------------------


class SyncTransport:
    """Synchronous HTTP transport backed by :class:`httpx.Client`."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float | httpx.Timeout,
        retry: RetryPolicy,
        user_agent: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._retry = retry
        # Caller-supplied client is taken as-is — useful for tests
        # (respx mounts a transport on a Client) and for advanced
        # users who need custom proxies / mTLS / event hooks.
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": user_agent,
                "Accept": "application/json",
            },
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SyncTransport:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ---- public ----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response:
        """Issue a request, retrying on transient failures.

        Returns the raw :class:`httpx.Response` so callers can choose
        between ``.json()`` (standard endpoints) and ``.text`` (the
        result-download endpoint, which returns markdown/text bytes).
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._retry.max_attempts + 1):
            try:
                response = self._client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                )
            except httpx.HTTPError as exc:
                # Transport-level failure (timeout, DNS, refused
                # connection, etc.). Retry until we run out of
                # attempts; surface the last one as TransportError.
                last_exc = exc
                if attempt >= self._retry.max_attempts:
                    raise errors.TransportError(str(exc)) from exc
                self._sleep_for_retry(attempt, retry_after=None)
                continue

            if response.is_success:
                return response

            # Non-2xx — decide whether to retry or raise.
            if self._retry.is_retryable_status(response.status_code) and (
                attempt < self._retry.max_attempts
            ):
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                self._sleep_for_retry(attempt, retry_after=retry_after)
                continue

            raise _map_error_response(response)

        # Unreachable in practice — the loop either returns or raises.
        # Keeps mypy happy and gives a sensible error if max_attempts=0.
        raise errors.TransportError(
            f"No attempts made (max_attempts={self._retry.max_attempts})"
            + (f": {last_exc}" if last_exc else "")
        )

    # ---- helpers ---------------------------------------------------------

    def _sleep_for_retry(self, attempt: int, retry_after: float | None) -> None:
        delay = self._retry.backoff_for_attempt(attempt, retry_after)
        if delay > 0:
            time.sleep(delay)
