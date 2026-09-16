"""Coordinator wiring for the notification feed (ADR 0014/0015/0016).

Exercises the account-wide fetch folded into the poll: baseline-silent bootstrap, high-water
persistence, per-category gating, per-watch device routing via sender.id, the most-recent-call
stash, overflow warning, and fetch-error tolerance.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.xplora_watch.config import resolve
from custom_components.xplora_watch.const import DOMAIN, EVENT_CALL, EVENT_SOS
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from custom_components.xplora_watch.notifications import HighWater
from custom_components.xplora_watch.pyxplora_api.model import SimpleChat
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID


def _entry(id: str, type: str, create: int, sender: str = DEFAULT_WUID, **data: Any) -> SimpleChat:
    return SimpleChat.from_dict({"id": id, "type": type, "create": create, "sender": {"id": sender}, "data": data})


def _register_device(hass: HomeAssistant, coordinator: XploraDataUpdateCoordinator, wuid: str = DEFAULT_WUID) -> str:
    registry = dr.async_get(hass)
    return registry.async_get_or_create(
        config_entry_id=coordinator._entry.entry_id,
        identifiers={(DOMAIN, f"{coordinator._entry.unique_id}_{wuid}")},
    ).id


def _enable(coordinator: XploraDataUpdateCoordinator, **flags: bool) -> None:
    coordinator._resolved = resolve({"notify_call": False, "notify_sos": False, "notify_power": False, "notify_low_power": False, **flags})


def _feed(coordinator: XploraDataUpdateCoordinator, entries: list[SimpleChat]) -> None:
    async def _fake(*_a: Any, **_k: Any) -> list[SimpleChat]:
        return entries

    coordinator.controller.getNotifications = _fake  # type: ignore[method-assign]


async def test_first_fetch_is_baseline_silent(coordinator: XploraDataUpdateCoordinator) -> None:
    _enable(coordinator, notify_sos=True)
    _register_device(coordinator.hass, coordinator)
    events = async_capture_events(coordinator.hass, EVENT_SOS)
    _feed(coordinator, [_entry("a", "SOS", 100), _entry("b", "SOS", 200)])

    await coordinator._process_notifications()

    assert events == []
    assert coordinator._notifications_mark == HighWater(create=200, ids=frozenset({"b"}))


async def test_second_poll_fires_call_event_routed_to_device(coordinator: XploraDataUpdateCoordinator) -> None:
    _enable(coordinator, notify_call=True)
    device_id = _register_device(coordinator.hass, coordinator)
    coordinator.data = {DEFAULT_WUID: {}}
    coordinator._notifications_mark = HighWater(create=100, ids=frozenset({"old"}))
    events = async_capture_events(coordinator.hass, EVENT_CALL)
    _feed(coordinator, [_entry("c", "CALL_LOG", 300, call_type=2, duration=0, call_number="+49123", call_mode_detail=50)])

    await coordinator._process_notifications()
    await coordinator.hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data["device_id"] == device_id
    assert data["wuid"] == DEFAULT_WUID
    assert data["direction"] == "incoming"
    assert data["missed"] is True
    # Most-recent-call sensor stash -- held outside coordinator.data so the poll rebuild can't wipe it.
    assert coordinator._last_call[DEFAULT_WUID]["call_number"] == "+49123"
    assert coordinator._notifications_mark == HighWater(create=300, ids=frozenset({"c"}))


async def test_unmatched_sender_is_skipped_but_mark_advances(coordinator: XploraDataUpdateCoordinator) -> None:
    _enable(coordinator, notify_sos=True)
    # No device registered for "ghost-watch".
    coordinator._notifications_mark = HighWater(create=100, ids=frozenset({"old"}))
    events = async_capture_events(coordinator.hass, EVENT_SOS)
    _feed(coordinator, [_entry("s", "SOS", 300, sender="ghost-watch")])

    await coordinator._process_notifications()
    await coordinator.hass.async_block_till_done()

    assert events == []
    assert coordinator._notifications_mark == HighWater(create=300, ids=frozenset({"s"}))


async def test_no_enabled_categories_skips_fetch(coordinator: XploraDataUpdateCoordinator) -> None:
    _enable(coordinator)  # everything off

    async def _boom(*_a: Any, **_k: Any) -> list[SimpleChat]:
        raise AssertionError("feed must not be fetched when no category is enabled")

    coordinator.controller.getNotifications = _boom  # type: ignore[method-assign]
    await coordinator._process_notifications()  # must not raise


async def test_fetch_error_does_not_raise(coordinator: XploraDataUpdateCoordinator) -> None:
    _enable(coordinator, notify_sos=True)

    async def _boom(*_a: Any, **_k: Any) -> list[SimpleChat]:
        raise RuntimeError("network down")

    coordinator.controller.getNotifications = _boom  # type: ignore[method-assign]
    await coordinator._process_notifications()  # swallowed
    assert coordinator._notifications_mark is None


async def test_last_call_survives_a_poll_with_no_new_call(coordinator: XploraDataUpdateCoordinator) -> None:
    """The most-recent-call stash persists across polls where no new call fires (ADR 0014).

    Guards the regression where the stash lived in `coordinator.data[wuid]`, which the poll rebuilds
    from a fixed-key literal every cycle -- wiping it after one poll.
    """
    _enable(coordinator, notify_call=True)
    _register_device(coordinator.hass, coordinator)
    coordinator._notifications_mark = HighWater(create=100, ids=frozenset({"old"}))
    _feed(coordinator, [_entry("c", "CALL_LOG", 300, call_number="+49123")])
    await coordinator._process_notifications()
    assert coordinator._last_call[DEFAULT_WUID]["call_number"] == "+49123"

    # Simulate the poll's `get_data` rebuild that replaces `self.data[wuid]` wholesale, then poll
    # again with nothing new: the stash lives outside `self.data`, so it must survive both.
    coordinator.data = {DEFAULT_WUID: {}}
    _feed(coordinator, [])
    await coordinator._process_notifications()
    assert coordinator._last_call[DEFAULT_WUID]["call_number"] == "+49123"


async def test_all_off_then_reenable_is_baseline_silent(coordinator: XploraDataUpdateCoordinator) -> None:
    """Turning every category off drops the mark, so re-enabling one does not replay the backlog
    accumulated while off (ADR 0015/0016)."""
    _enable(coordinator, notify_sos=True)
    _register_device(coordinator.hass, coordinator)
    coordinator._notifications_mark = HighWater(create=100, ids=frozenset({"old"}))

    # All off: the mark is cleared.
    _enable(coordinator)
    _feed(coordinator, [])
    await coordinator._process_notifications()
    assert coordinator._notifications_mark is None

    # Re-enable with a backlog present: baseline-silent (fires nothing, just records the mark).
    _enable(coordinator, notify_sos=True)
    events = async_capture_events(coordinator.hass, EVENT_SOS)
    _feed(coordinator, [_entry("backlog", "SOS", 500)])
    await coordinator._process_notifications()
    assert events == []
    assert coordinator._notifications_mark == HighWater(create=500, ids=frozenset({"backlog"}))


async def test_mark_persists_and_restore_prevents_replay(coordinator: XploraDataUpdateCoordinator) -> None:
    """The mark is written to the Store and a restore-then-poll does not refire history (ADR 0015)."""
    _enable(coordinator, notify_sos=True)
    _register_device(coordinator.hass, coordinator)
    coordinator._notifications_mark = HighWater(create=100, ids=frozenset({"old"}))
    _feed(coordinator, [_entry("s", "SOS", 300)])
    await coordinator._process_notifications()

    blob = await coordinator._notifications_store.async_load()
    assert blob == {"create": 300, "ids": ["s"]}

    # Simulate a restart: a fresh in-memory mark restored from the store, then the same feed polled.
    coordinator._notifications_mark = None
    await coordinator._restore_notifications_mark()
    assert coordinator._notifications_mark == HighWater(create=300, ids=frozenset({"s"}))
    events = async_capture_events(coordinator.hass, EVENT_SOS)
    _feed(coordinator, [_entry("s", "SOS", 300)])
    await coordinator._process_notifications()
    assert events == []


async def test_same_second_new_sibling_still_fires(coordinator: XploraDataUpdateCoordinator) -> None:
    """A genuinely new entry sharing the mark's epoch second still fires exactly once, order-
    independently -- the mark tracks the ids already seen at that second (ADR 0015)."""
    _enable(coordinator, notify_sos=True)
    _register_device(coordinator.hass, coordinator)
    coordinator._notifications_mark = HighWater(create=1000, ids=frozenset({"a1"}))
    events = async_capture_events(coordinator.hass, EVENT_SOS)
    # a2 is new (not in the mark's boundary-id set); a1 is already seen and must not refire.
    _feed(coordinator, [_entry("a2", "SOS", 1000), _entry("a1", "SOS", 1000)])
    await coordinator._process_notifications()
    await coordinator.hass.async_block_till_done()
    assert [e.data["id"] for e in events] == ["a2"]
    assert coordinator._notifications_mark == HighWater(create=1000, ids=frozenset({"a1", "a2"}))


async def test_overflow_full_page_logs_warning(coordinator: XploraDataUpdateCoordinator, caplog: pytest.LogCaptureFixture) -> None:
    _enable(coordinator, notify_sos=True)
    _register_device(coordinator.hass, coordinator)
    coordinator._notifications_mark = HighWater(create=100, ids=frozenset({"old"}))
    # A full page (20) of entries all newer than the mark -> overflow beyond this page is dropped.
    _feed(coordinator, [_entry(f"n{i}", "SOS", 200 + i) for i in range(20)])

    with caplog.at_level(logging.WARNING):
        await coordinator._process_notifications()

    assert any("full page" in r.message for r in caplog.records)
