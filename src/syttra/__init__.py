"""Syttra — placeholder.

This is a name-reservation release. The real Python SDK ships in
0.1.0, see https://syttra.com/docs/sdk/python for status. Importing
this version is intentionally near-empty so users who pip-installed
the wrong package learn quickly.
"""

__version__ = "0.0.1"

_PLACEHOLDER_NOTICE = (
    "syttra 0.0.x is a name-reservation placeholder. The real Python SDK "
    "lands in 0.1.0 — see https://syttra.com/docs/sdk/python for status. "
    "If you're hitting Syttra today, the REST API at https://api.syttra.com "
    "works directly with `httpx` or `requests`."
)


def _placeholder_warning() -> None:
    """Emit a one-line warning so users know they're on the placeholder."""
    import warnings

    warnings.warn(_PLACEHOLDER_NOTICE, FutureWarning, stacklevel=2)


# Fire the notice once on import so accidental users notice immediately.
_placeholder_warning()
