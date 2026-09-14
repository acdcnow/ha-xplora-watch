"""Unit tests for `PyXploraApi.reload_watch_list` / `getAllWatchUserIDs`.

`self.watchs` (the account's watch list) is loaded once at first `init()` under a
`if not self.watchs` gate and then cached for the controller's lifetime, so a watch added to the
account later never shows up. `reload_watch_list` forces a fresh `deviceList` fetch past that gate;
`getAllWatchUserIDs` enumerates the full list independent of the pinned `_wuid` filter. These
tests exercise both directly against a stubbed transport (no network, no login).
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.xplora_watch.pyxplora_api.pyxplora_api_async import PyXploraApi
from tests.xplora_watch.fixtures.graphql_payloads import make_device_list_payload


def _ward(wuid: str, name: str, phone: str) -> dict[str, Any]:
    return {"ward": {"id": wuid, "name": name, "phoneNumber": phone, "file": {"id": ""}}}


def _controller_with_one_watch(monkeypatch: pytest.MonkeyPatch, device_list: dict[str, Any]) -> PyXploraApi:
    """A controller whose `self.watchs` is already populated (one watch), transport stubbed."""
    controller = PyXploraApi(countrycode="+49", phoneNumber="+491700000001", password="secret", userLang="en-GB", timeZone="UTC")
    controller.watchs = [_ward("watch-id-001", "Kid One", "+491700000001")]

    async def _fake_device_list() -> dict[str, Any]:
        return device_list

    monkeypatch.setattr(controller._gql_handler, "get_device_list_a", _fake_device_list)
    return controller


async def test_reload_watch_list_refetches_past_the_cache_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """`reload_watch_list` repopulates `self.watchs` even though it is already non-empty."""
    original = make_device_list_payload(wuid="watch-id-001")
    added = make_device_list_payload(wuid="watch-id-002", ward_name="Kid Two", ward_phone="+491700000999")
    controller = _controller_with_one_watch(monkeypatch, {"deviceList": original["deviceList"] + added["deviceList"]})

    # Precondition: the once-only gate would keep the stale single-watch list.
    assert [w["ward"]["id"] for w in controller.watchs] == ["watch-id-001"]

    await controller.reload_watch_list()

    assert [w["ward"]["id"] for w in controller.watchs] == ["watch-id-001", "watch-id-002"]


async def test_get_all_watch_user_ids_ignores_pinned_wuid(monkeypatch: pytest.MonkeyPatch) -> None:
    """`getAllWatchUserIDs` returns every account watch, even when `_wuid` pins a subset.

    `getWatchUserIDs` (the entity-scoping path) still honors the pinned subset; the new
    enumeration must not, or the picker could never offer an unselected watch.
    """
    original = make_device_list_payload(wuid="watch-id-001")
    added = make_device_list_payload(wuid="watch-id-002", ward_name="Kid Two", ward_phone="+491700000999")
    controller = _controller_with_one_watch(monkeypatch, {"deviceList": original["deviceList"] + added["deviceList"]})
    controller._wuid = ["watch-id-001"]  # the pinned CONF_WATCHES subset

    await controller.reload_watch_list()

    assert controller.getWatchUserIDs() == ["watch-id-001"]  # scoping filter unchanged
    assert controller.getAllWatchUserIDs() == ["watch-id-001", "watch-id-002"]  # full account list
