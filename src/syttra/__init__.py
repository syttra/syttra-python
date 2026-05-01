"""Syttra — the official Python SDK for `syttra.com <https://syttra.com>`_.

The minimal usage::

    from syttra import Syttra

    client = Syttra(api_key="sk_live_...")
    job = client.create_job(url="https://example.com")
    finished = client.wait_for_job(job.job_id)
    result = client.get_job_result(finished.job_id)
    print(result.body)

See `the docs <https://syttra.com/docs/sdk/python>`_ for the full
reference, including crawl modes, sitemap previews, and quota
handling.
"""

from __future__ import annotations

__version__ = "0.1.0"

from ._client import DEFAULT_BASE_URL, Syttra
from ._http import RetryPolicy
from .errors import (
    ApiError,
    Conflict,
    Forbidden,
    InvalidRequest,
    NotFound,
    PayloadTooLarge,
    QuotaExceeded,
    RateLimited,
    ServerError,
    SyttraError,
    TransportError,
    Unauthorized,
)
from .models import (
    CrawlMode,
    ExportFormat,
    Job,
    JobCreated,
    JobLinks,
    JobList,
    JobListItem,
    JobProgress,
    JobResult,
    JobStatus,
    Plan,
    SitemapPreview,
    Usage,
    UsagePlan,
)

__all__ = [
    # client
    "Syttra",
    "RetryPolicy",
    "DEFAULT_BASE_URL",
    # errors
    "ApiError",
    "Conflict",
    "Forbidden",
    "InvalidRequest",
    "NotFound",
    "PayloadTooLarge",
    "QuotaExceeded",
    "RateLimited",
    "ServerError",
    "SyttraError",
    "TransportError",
    "Unauthorized",
    # models
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
    "SitemapPreview",
    "Usage",
    "UsagePlan",
    # version
    "__version__",
]
