"""Tests for switch.py: the per-watch live-follow toggle.

The switch is the discoverable face of the bounded fast-poll session: on starts one with the default
duration, off ends it early, and it reads back `off` as soon as the session expires. It is created
enabled (switching it on costs nothing while off) and only for a Guardian's watch, since a session
drives `askWatchLocate`, which a Contact cannot trigger.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xplora_watch.const import (
    ATTR_FOLLOW_ENDS_AT,
    ATTR_FOLLOW_INTERVAL,
    ATTR_FOLLOW_REMAINING,
    DOMAIN,
    FOLLOW_INTERVAL_SECONDS,
    SWITCH_LIVE_FOLLOW,
)
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from custom_components.xplora_watch.switch import XploraFollowSwitch, async_setup_entry
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID


def _capture() -> tuple[list, object]:
    captured: list = []

    def capture_entities(new_entities, update_before_add=False) -> None:  # noqa: ARG001
        captured.extend(new_entities)

    return captured, capture_entities


def _make_switch(hass: HomeAssistant, config_entry: ConfigEntry, coordinator: XploraDataUpdateCoordinator) -> XploraFollowSwitch:
    ward = coordinator.controller.watchs[0]["ward"]
    entity = XploraFollowSwitch(config_entry, coordinator, ward, DEFAULT_WUID)
    entity.hass = hass
    return entity


async def test_setup_creates_one_enabled_switch_per_watch(
    hass: HomeAssistant,
    mock_config_entry_phone: MockConfigEntry,
    coordinator_with_data: XploraDataUpdateCoordinator,
) -> None:
    """One switch per configured watch, enabled out of the box and named by translation key."""
    hass.data.setdefault(DOMAIN, {})[mock_config_entry_phone.entry_id] = coordinator_with_data
    captured, capture_entities = _capture()

    await async_setup_entry(hass, mock_config_entry_phone, capture_entities)

    assert len(captured) == 1
    switch = captured[0]
    assert switch._attr_translation_key == SWITCH_LIVE_FOLLOW
    assert switch.entity_registry_enabled_default is True
    assert f"_watch_{SWITCH_LIVE_FOLLOW}_" in switch.unique_id


async def test_setup_skips_a_contact_watch(
    hass: HomeAssistant,
    mock_config_entry_phone: MockConfigEntry,
    coordinator_with_data: XploraDataUpdateCoordinator,
) -> None:
    """A Contact-only watch gets no follow switch: it could not trigger a fresh fix anyway."""
    coordinator_with_data.is_admin = {DEFAULT_WUID: False}
    hass.data.setdefault(DOMAIN, {})[mock_config_entry_phone.entry_id] = coordinator_with_data
    captured, capture_entities = _capture()

    await async_setup_entry(hass, mock_config_entry_phone, capture_entities)

    assert captured == []


async def test_turn_on_starts_a_session_and_exposes_the_countdown(
    hass: HomeAssistant,
    mock_config_entry_phone: MockConfigEntry,
    coordinator_with_data: XploraDataUpdateCoordinator,
) -> None:
    """Turning the switch on starts a session (and refreshes right away); the countdown rides along
    as attributes so a dashboard can show it without a template sensor."""
    coordinator = coordinator_with_data
    switch = _make_switch(hass, mock_config_entry_phone, coordinator)

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()) as mock_update:
        await switch.async_turn_on()

    mock_update.assert_awaited_once_with(targets=[DEFAULT_WUID])
    assert switch.is_on is True
    attrs = switch.extra_state_attributes
    assert attrs[ATTR_FOLLOW_INTERVAL] == FOLLOW_INTERVAL_SECONDS
    assert attrs[ATTR_FOLLOW_ENDS_AT] == coordinator.follow_deadline(DEFAULT_WUID).isoformat()
    assert attrs[ATTR_FOLLOW_REMAINING] > 0
    coordinator.async_teardown()


async def test_turn_off_ends_the_session_and_drops_the_countdown(
    hass: HomeAssistant,
    mock_config_entry_phone: MockConfigEntry,
    coordinator_with_data: XploraDataUpdateCoordinator,
) -> None:
    """Turning the switch off ends the session early and the switch stops advertising `ends_at`."""
    coordinator = coordinator_with_data
    switch = _make_switch(hass, mock_config_entry_phone, coordinator)

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await switch.async_turn_on()
    await switch.async_turn_off()

    assert switch.is_on is False
    assert ATTR_FOLLOW_ENDS_AT not in switch.extra_state_attributes
    assert coordinator._cancel_follow is None


async def test_switch_reads_off_once_the_session_has_expired(
    hass: HomeAssistant,
    mock_config_entry_phone: MockConfigEntry,
    coordinator_with_data: XploraDataUpdateCoordinator,
) -> None:
    """The session is what keeps the switch on: once the deadline passes (even before the next tick
    sweeps it) the switch reports `off`, so a dashboard can never show a stale `on`."""
    coordinator = coordinator_with_data
    switch = _make_switch(hass, mock_config_entry_phone, coordinator)

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await switch.async_turn_on()
    assert switch.is_on is True

    coordinator._follow_deadlines[DEFAULT_WUID] = datetime.now() - timedelta(seconds=1)

    assert switch.is_on is False
    coordinator.async_teardown()
