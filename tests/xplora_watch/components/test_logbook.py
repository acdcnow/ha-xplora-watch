"""Tests for the notification-event logbook lines (async_describe_events, ADR 0016)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xplora_watch.const import DOMAIN, EVENT_CALL, EVENT_LOW_POWER, EVENT_POWER, EVENT_SOS
from custom_components.xplora_watch.logbook import async_describe_events


def _describers(hass: HomeAssistant) -> dict[str, Callable[[Any], dict[str, str]]]:
    captured: dict[str, Callable[[Any], dict[str, str]]] = {}

    def _async_describe_event(domain: str, event_type: str, describe: Callable[[Any], dict[str, str]]) -> None:
        assert domain == DOMAIN
        captured[event_type] = describe

    async_describe_events(hass, _async_describe_event)
    return captured


def _describe(hass: HomeAssistant, event_type: str, **data: Any) -> dict[str, str]:
    return _describers(hass)[event_type](SimpleNamespace(data=data))


def test_all_four_event_types_registered(hass: HomeAssistant) -> None:
    assert set(_describers(hass)) == {EVENT_CALL, EVENT_SOS, EVENT_POWER, EVENT_LOW_POWER}


def test_missed_incoming_call_line(hass: HomeAssistant) -> None:
    entry = _describe(hass, EVENT_CALL, direction="incoming", missed=True, call_name="Mum", call_number="+49123", duration=0)
    msg = entry[LOGBOOK_ENTRY_MESSAGE]
    assert "missed" in msg and "incoming" in msg and "Mum" in msg
    assert entry[LOGBOOK_ENTRY_NAME]


def test_answered_outgoing_call_line_has_duration_and_number(hass: HomeAssistant) -> None:
    entry = _describe(hass, EVENT_CALL, direction="outgoing", missed=False, call_number="+49123", duration=42)
    msg = entry[LOGBOOK_ENTRY_MESSAGE]
    assert "outgoing" in msg and "+49123" in msg and "42" in msg
    assert "missed" not in msg


def test_sos_line_carries_coordinates(hass: HomeAssistant) -> None:
    msg = _describe(hass, EVENT_SOS, lat=52.5, lng=13.4, battery=15)[LOGBOOK_ENTRY_MESSAGE]
    assert "SOS" in msg and "52.5" in msg and "13.4" in msg


def test_sos_line_without_coordinates_omits_none(hass: HomeAssistant) -> None:
    msg = _describe(hass, EVENT_SOS)[LOGBOOK_ENTRY_MESSAGE]
    assert "SOS" in msg and "None" not in msg


def test_sos_line_with_partial_coordinates_omits_location(hass: HomeAssistant) -> None:
    # Needs BOTH coords; a lone lat must not render "at 52.5, None".
    msg = _describe(hass, EVENT_SOS, lat=52.5)[LOGBOOK_ENTRY_MESSAGE]
    assert "None" not in msg and "52.5" not in msg


def test_power_line_reflects_state(hass: HomeAssistant) -> None:
    on = _describe(hass, EVENT_POWER, state="on", battery=90)[LOGBOOK_ENTRY_MESSAGE]
    off = _describe(hass, EVENT_POWER, state="off", battery=88)[LOGBOOK_ENTRY_MESSAGE]
    assert "on" in on.lower()
    assert "off" in off.lower()


def test_low_power_line_has_battery(hass: HomeAssistant) -> None:
    msg = _describe(hass, EVENT_LOW_POWER, battery=5)[LOGBOOK_ENTRY_MESSAGE]
    assert "5" in msg


def test_missing_direction_does_not_double_the_word_call(hass: HomeAssistant) -> None:
    # `_direction` returns None for an unmapped call_type (ref:XW-020) -- the line must not read
    # "missed call call from ...".
    msg = _describe(hass, EVENT_CALL, missed=True, call_name="Mum")[LOGBOOK_ENTRY_MESSAGE]
    assert msg == "missed call from Mum"


def test_low_power_without_battery_omits_none(hass: HomeAssistant) -> None:
    msg = _describe(hass, EVENT_LOW_POWER)[LOGBOOK_ENTRY_MESSAGE]
    assert "None" not in msg


def test_line_name_resolves_to_the_watch_device(hass: HomeAssistant) -> None:
    """With a device_id in the payload, the line's name is that device's name (anchoring, ADR 0014)."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="+491700000001")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "d1")}, name="Kid One Watch")
    line = _describe(hass, EVENT_SOS, lat=52.5, lng=13.4, device_id=device.id)
    assert line[LOGBOOK_ENTRY_NAME] == "Kid One Watch"


def test_line_name_falls_back_when_device_unknown(hass: HomeAssistant) -> None:
    line = _describe(hass, EVENT_SOS, lat=52.5, lng=13.4, device_id="does-not-exist")
    assert line[LOGBOOK_ENTRY_NAME]  # non-empty fallback, no crash
