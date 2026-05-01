"""Shared fixtures for the Syttra SDK test suite."""

from __future__ import annotations

import httpx
import pytest

from syttra import RetryPolicy, Syttra

BASE_URL = "https://test.syttra.com"


@pytest.fixture
def client() -> Syttra:
    """A Syttra client pointed at the dummy ``BASE_URL`` so respx can
    mount mocks without needing a real network."""
    return Syttra(
        api_key="sk_test_unit",
        base_url=BASE_URL,
        # Tight retry policy: the default 3 attempts x 0.5s backoff
        # would slow tests of retry behaviour to a crawl.
        retry=RetryPolicy(
            max_attempts=3,
            initial_backoff_seconds=0.0,
            backoff_multiplier=1.0,
            max_backoff_seconds=0.0,
        ),
    )


@pytest.fixture
def base_url() -> str:
    return BASE_URL


@pytest.fixture
def http_client() -> httpx.Client:
    """A bare ``httpx.Client`` for tests that build their own
    ``Syttra`` instance to assert constructor behaviour."""
    return httpx.Client(base_url=BASE_URL)
