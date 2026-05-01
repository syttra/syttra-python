"""Error types raised by the Syttra SDK.

The hierarchy mirrors the API's error envelope (status + code +
message + details) and adds a few subclasses that map to common
HTTP status codes so callers can do ``except Unauthorized`` rather
than ``if e.status == 401``.

The ``request_id`` (when present) makes a support-ticket exchange
trivial: copy that one string and we can find your call in the
logs in seconds.
"""

from __future__ import annotations

from typing import Any


class SyttraError(Exception):
    """Base for everything raised by this SDK.

    Use ``except SyttraError`` if you want a single catch-all that
    covers HTTP errors, transport failures, and SDK-internal bugs.
    """


class ApiError(SyttraError):
    """A non-2xx response from the API.

    Always carries the HTTP status. ``code`` and ``message`` come
    from the API's error envelope when present, falling back to
    ``"unknown_error"`` and the raw status line. ``details`` is
    whatever the server included as structured context.

    For most callers the right pattern is::

        try:
            client.create_job(url="https://example.com")
        except QuotaExceeded as exc:
            ...  # show "you're over your monthly cap"
        except Unauthorized:
            ...  # API key revoked / wrong env
        except ApiError as exc:
            ...  # everything else
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.request_id = request_id

    def __repr__(self) -> str:
        rid = f" request_id={self.request_id}" if self.request_id else ""
        return f"<{type(self).__name__} {self.status} {self.code}{rid}: {self.message}>"


# ---- HTTP-status-keyed subclasses ------------------------------------------
# Catching by class is friendlier than checking ``status`` codes.


class InvalidRequest(ApiError):
    """400 — request body or parameters are malformed."""


class Unauthorized(ApiError):
    """401 — no key / invalid key / expired session."""


class Forbidden(ApiError):
    """403 — authenticated but the key isn't allowed to do this."""


class NotFound(ApiError):
    """404 — the resource doesn't exist (or the route is gated and
    you're not on the allow-list — Syttra returns 404, not 403, on
    admin routes for non-owners)."""


class Conflict(ApiError):
    """409 — duplicate, constraint violation, or stateful clash."""


class PayloadTooLarge(ApiError):
    """413 — body bigger than the API's content-length limit."""


class RateLimited(ApiError):
    """429 — slow down. The SDK auto-retries this with backoff
    by default; this is what you see when retries are exhausted."""


class QuotaExceeded(ApiError):
    """402 — you're over your monthly page allowance.

    ``details`` typically includes ``used``, ``quota``, ``requested``,
    ``remaining``, ``period_end`` so the calling app can show a useful
    "comes back on YYYY-MM-01" message.
    """


class ServerError(ApiError):
    """5xx — something broke on the Syttra side. Worth retrying;
    the SDK auto-retries with backoff by default."""


# ---- Transport-level ------------------------------------------------------


class TransportError(SyttraError):
    """Network failure, DNS, TLS, timeout — the API never answered.

    Distinct from ``ApiError`` so callers can choose to retry the
    whole operation rather than just inspect a status code.
    """


# ---- Internal: status → class lookup --------------------------------------

_STATUS_TO_CLASS: dict[int, type[ApiError]] = {
    400: InvalidRequest,
    401: Unauthorized,
    402: QuotaExceeded,
    403: Forbidden,
    404: NotFound,
    409: Conflict,
    413: PayloadTooLarge,
    429: RateLimited,
}


def from_response(
    status: int,
    code: str,
    message: str,
    details: Any | None = None,
    request_id: str | None = None,
) -> ApiError:
    """Build the right subclass for an HTTP status.

    Falls back to :class:`ServerError` for 5xx and the generic
    :class:`ApiError` for any other code.
    """
    cls = _STATUS_TO_CLASS.get(status)
    if cls is None:
        cls = ServerError if status >= 500 else ApiError
    return cls(
        status=status,
        code=code,
        message=message,
        details=details,
        request_id=request_id,
    )
