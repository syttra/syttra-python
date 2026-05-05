"""Tests for the watcher methods on the Syttra client.

Same respx-mock pattern as ``test_client.py`` — each test asserts
the right HTTP verb hits the right path, the body matches what the
backend's Pydantic schema expects, and the response is parsed into
the typed model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
import respx

from syttra import (
    Forbidden,
    InvalidRequest,
    Syttra,
    Watcher,
)


def _watcher_payload(**overrides) -> dict:
    """Build a Watcher response shape for stubbing.

    Defaults reflect a plain "fires on every change, email on,
    webhook empty" watcher — most overrides need only one or two
    keys to set up a specific test scenario.
    """
    base = {
        "id": str(uuid4()),
        "name": "Pro plan price",
        "url": "https://example.com/pricing",
        "selector": ".pro .price",
        "selector_type": "css",
        "schedule_cron": "*/15 * * * *",
        "webhook_url": None,
        "trigger_type": "changes",
        "trigger_value": None,
        "notify_email_enabled": True,
        "last_value": None,
        "last_checked_at": None,
        "last_changed_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@respx.mock
def test_create_watcher_minimal(base_url: str, client: Syttra) -> None:
    payload = _watcher_payload()
    route = respx.post(f"{base_url}/v1/watchers").mock(
        return_value=httpx.Response(201, json=payload),
    )

    w = client.create_watcher(
        name="Pro plan price",
        url="https://example.com/pricing",
        selector=".pro .price",
    )

    assert route.called
    body = route.calls.last.request.read()
    assert b'"selector_type":"css"' in body
    assert b'"trigger_type":"changes"' in body
    # Default schedule lands as */15 * * * * unless caller overrides.
    assert b'"*/15 * * * *"' in body

    assert isinstance(w, Watcher)
    assert w.name == "Pro plan price"
    assert w.selector_type == "css"
    assert w.trigger_type == "changes"


@respx.mock
def test_create_watcher_with_threshold(base_url: str, client: Syttra) -> None:
    payload = _watcher_payload(trigger_type="below", trigger_value="29")
    route = respx.post(f"{base_url}/v1/watchers").mock(
        return_value=httpx.Response(201, json=payload),
    )

    client.create_watcher(
        name="alert",
        url="https://example.com",
        selector=".price",
        trigger_type="below",
        trigger_value="29",
        notify_email_enabled=True,
        webhook_url="https://hooks.example.com/syttra",
    )

    assert route.called
    body = route.calls.last.request.read()
    assert b'"trigger_type":"below"' in body
    assert b'"trigger_value":"29"' in body
    assert b'"webhook_url":"https://hooks.example.com/syttra"' in body
    assert b'"notify_email_enabled":true' in body


@respx.mock
def test_create_watcher_403_feature_not_in_plan(base_url: str, client: Syttra) -> None:
    """Free-tier users get 403 with a specific code -- the SDK maps
    this to Forbidden so user code can branch on the error type."""
    respx.post(f"{base_url}/v1/watchers").mock(
        return_value=httpx.Response(
            403,
            json={
                "error": {
                    "code": "feature_not_in_plan",
                    "message": "Watchers aren't included in your plan.",
                }
            },
        ),
    )

    with pytest.raises(Forbidden) as exc:
        client.create_watcher(
            name="x",
            url="https://example.com",
            selector=".x",
        )
    assert exc.value.code == "feature_not_in_plan"


@respx.mock
def test_create_watcher_400_schedule_too_fast(base_url: str, client: Syttra) -> None:
    respx.post(f"{base_url}/v1/watchers").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "code": "schedule_too_fast",
                    "message": (
                        "Schedule fires every 60s but your plan allows no faster than every 900s."
                    ),
                }
            },
        ),
    )

    with pytest.raises(InvalidRequest) as exc:
        client.create_watcher(
            name="fast",
            url="https://example.com",
            selector=".x",
            schedule_cron="* * * * *",
        )
    assert exc.value.code == "schedule_too_fast"


@respx.mock
def test_get_watcher(base_url: str, client: Syttra) -> None:
    wid = uuid4()
    payload = _watcher_payload(id=str(wid), name="my watcher")
    respx.get(f"{base_url}/v1/watchers/{wid}").mock(
        return_value=httpx.Response(200, json=payload),
    )

    w = client.get_watcher(wid)
    assert w.name == "my watcher"
    assert w.id == wid


@respx.mock
def test_list_watchers_with_cursor(base_url: str, client: Syttra) -> None:
    route = respx.get(f"{base_url}/v1/watchers").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [_watcher_payload(name="A"), _watcher_payload(name="B")],
                "next_cursor": "next123",
                "has_more": True,
            },
        ),
    )

    page = client.list_watchers(cursor="prev999")

    assert route.called
    assert route.calls.last.request.url.params["cursor"] == "prev999"
    assert len(page.items) == 2
    assert page.next_cursor == "next123"
    assert page.has_more is True


@respx.mock
def test_update_watcher_name_only(base_url: str, client: Syttra) -> None:
    wid = uuid4()
    route = respx.patch(f"{base_url}/v1/watchers/{wid}").mock(
        return_value=httpx.Response(200, json=_watcher_payload(id=str(wid), name="renamed")),
    )

    w = client.update_watcher(wid, name="renamed")

    assert route.called
    body = route.calls.last.request.read()
    # Only the name field should travel; PATCH semantics depend on
    # absent vs null distinction.
    assert b'"name":"renamed"' in body
    assert b"selector" not in body
    assert b"schedule_cron" not in body
    assert w.name == "renamed"


@respx.mock
def test_update_watcher_clears_webhook_via_sentinel(base_url: str, client: Syttra) -> None:
    wid = uuid4()
    respx.patch(f"{base_url}/v1/watchers/{wid}").mock(
        return_value=httpx.Response(200, json=_watcher_payload(id=str(wid), webhook_url=None)),
    )

    client.update_watcher(wid, clear_webhook=True)

    body = respx.calls.last.request.read()
    assert b'"webhook_url_clear":true' in body


@respx.mock
def test_delete_watcher(base_url: str, client: Syttra) -> None:
    wid = uuid4()
    route = respx.delete(f"{base_url}/v1/watchers/{wid}").mock(
        return_value=httpx.Response(204),
    )

    client.delete_watcher(wid)
    assert route.called


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@respx.mock
def test_get_watcher_history_includes_failures(base_url: str, client: Syttra) -> None:
    wid = uuid4()
    success_id = uuid4()
    failure_id = uuid4()
    respx.get(f"{base_url}/v1/watchers/{wid}/history").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": str(success_id),
                        "value": "€29",
                        "content_hash": "f3a1" * 16,
                        "fetched_at": "2026-05-05T07:00:00Z",
                        "error": None,
                    },
                    {
                        "id": str(failure_id),
                        "value": None,
                        "content_hash": None,
                        "fetched_at": "2026-05-05T06:45:00Z",
                        "error": "selector matched nothing",
                    },
                ],
                "next_cursor": None,
                "has_more": False,
            },
        ),
    )

    history = client.get_watcher_history(wid)
    assert len(history.items) == 2
    assert history.items[0].error is None
    assert history.items[1].error == "selector matched nothing"
    assert history.items[1].value is None


# ---------------------------------------------------------------------------
# Preview helpers
# ---------------------------------------------------------------------------


@respx.mock
def test_test_watcher_selector(base_url: str, client: Syttra) -> None:
    route = respx.post(f"{base_url}/v1/watchers/test-selector").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": "€29 / month",
                "match_count": 1,
                "html_preview": '<span class="price">€29 / month</span>',
                "final_url": "https://example.com/pricing",
                "content_type": "text/html; charset=utf-8",
            },
        ),
    )

    result = client.test_watcher_selector(
        url="https://example.com/pricing",
        selector=".pro .price",
    )

    assert route.called
    body = route.calls.last.request.read()
    assert b'"selector":".pro .price"' in body
    assert b'"selector_type":"css"' in body

    assert result.value == "€29 / month"
    assert result.match_count == 1


@respx.mock
def test_pick_watcher_screenshot(base_url: str, client: Syttra) -> None:
    respx.post(f"{base_url}/v1/watchers/screenshot-picker").mock(
        return_value=httpx.Response(
            200,
            json={
                "screenshot_base64": "iVBORw0KGgo=",
                "screenshot_width": 1280,
                "screenshot_height": 2400,
                "final_url": "https://example.com/pricing",
                "elements": [
                    {
                        "selector": ".price",
                        "x": 100,
                        "y": 200,
                        "width": 80,
                        "height": 24,
                        "text": "€29 / month",
                        "tag": "span",
                    }
                ],
            },
        ),
    )

    result = client.pick_watcher_screenshot(url="https://example.com/pricing")
    assert result.screenshot_base64 == "iVBORw0KGgo="
    assert result.screenshot_width == 1280
    assert len(result.elements) == 1
    assert result.elements[0].selector == ".price"
    assert result.elements[0].text == "€29 / month"
