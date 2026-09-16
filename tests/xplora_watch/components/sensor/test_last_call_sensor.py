"""Tests for the most-recent-call sensor (XploraLastCallSensor, ADR 0014)."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.xplora_watch.const import (
    ATTR_CALL_DIRECTION,
    ATTR_CALL_DURATION,
    ATTR_CALL_MISSED,
    ATTR_CALL_NAME,
    ATTR_CALL_NUMBER,
    ATTR_CALL_TIME,
)
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from custom_components.xplora_watch.sensor import LAST_CALL_SENSOR_TYPE, XploraLastCallSensor
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID

_CALL = {
    "id": "c1",
    "create": 1700000100,
    "direction": "incoming",
    "duration": 0,
    "missed": True,
    "call_name": "Mum",
    "call_number": "+491234567",
    "call_time": 1700000000,
}


def _make_sensor(hass: HomeAssistant, config_entry: ConfigEntry, coordinator: XploraDataUpdateCoordinator) -> XploraLastCallSensor:
    ward = coordinator.controller.watchs[0]["ward"]
    sensor = XploraLastCallSensor(config_entry, coordinator, ward, DEFAULT_WUID, LAST_CALL_SENSOR_TYPE)
    sensor.hass = hass
    return sensor


async def test_state_is_the_call_timestamp(
    hass: HomeAssistant, mock_config_entry_phone, coordinator_with_data: XploraDataUpdateCoordinator
) -> None:
    coordinator_with_data._last_call[DEFAULT_WUID] = _CALL
    sensor = _make_sensor(hass, mock_config_entry_phone, coordinator_with_data)
    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.native_value == datetime.fromtimestamp(1700000000, tz=timezone.utc)


async def test_attributes_carry_contact_detail(
    hass: HomeAssistant, mock_config_entry_phone, coordinator_with_data: XploraDataUpdateCoordinator
) -> None:
    coordinator_with_data._last_call[DEFAULT_WUID] = _CALL
    sensor = _make_sensor(hass, mock_config_entry_phone, coordinator_with_data)
    attrs = sensor.extra_state_attributes
    assert attrs[ATTR_CALL_DIRECTION] == "incoming"
    assert attrs[ATTR_CALL_DURATION] == 0
    assert attrs[ATTR_CALL_MISSED] is True
    assert attrs[ATTR_CALL_NAME] == "Mum"
    assert attrs[ATTR_CALL_NUMBER] == "+491234567"
    assert attrs[ATTR_CALL_TIME] == 1700000000


async def test_pii_attributes_kept_out_of_recorder(
    hass: HomeAssistant, mock_config_entry_phone, coordinator_with_data: XploraDataUpdateCoordinator
) -> None:
    # Contact number/name and the rest stay out of long-term state history (ADR 0014).
    sensor = _make_sensor(hass, mock_config_entry_phone, coordinator_with_data)
    for key in (ATTR_CALL_NUMBER, ATTR_CALL_NAME, ATTR_CALL_DIRECTION, ATTR_CALL_DURATION, ATTR_CALL_MISSED, ATTR_CALL_TIME):
        assert key in sensor._unrecorded_attributes


async def test_unknown_until_a_call_is_seen(
    hass: HomeAssistant, mock_config_entry_phone, coordinator_with_data: XploraDataUpdateCoordinator
) -> None:
    sensor = _make_sensor(hass, mock_config_entry_phone, coordinator_with_data)
    assert sensor.native_value is None


async def test_falls_back_to_create_when_call_time_missing(
    hass: HomeAssistant, mock_config_entry_phone, coordinator_with_data: XploraDataUpdateCoordinator
) -> None:
    # An older-watch entry can omit call_time; the notification `create` time is used instead.
    coordinator_with_data._last_call[DEFAULT_WUID] = {**_CALL, ATTR_CALL_TIME: None, "create": 1700000100}
    sensor = _make_sensor(hass, mock_config_entry_phone, coordinator_with_data)
    assert sensor.native_value == datetime.fromtimestamp(1700000100, tz=timezone.utc)


async def test_restores_timestamp_after_restart(
    hass: HomeAssistant, mock_config_entry_phone, coordinator_with_data: XploraDataUpdateCoordinator, monkeypatch
) -> None:
    """After a restart the in-memory stash is empty; the non-PII timestamp is restored from state."""
    from homeassistant.components.sensor import SensorExtraStoredData

    sensor = _make_sensor(hass, mock_config_entry_phone, coordinator_with_data)
    restored = datetime.fromtimestamp(1699999999, tz=timezone.utc)

    async def _fake_last() -> SensorExtraStoredData:
        return SensorExtraStoredData(native_value=restored, native_unit_of_measurement=None)

    monkeypatch.setattr(sensor, "async_get_last_sensor_data", _fake_last)
    await sensor.async_added_to_hass()

    # No live call yet -> the restored timestamp holds the state.
    assert sensor.native_value == restored
    # A fresh call takes precedence over the restored value.
    coordinator_with_data._last_call[DEFAULT_WUID] = _CALL
    assert sensor.native_value == datetime.fromtimestamp(1700000000, tz=timezone.utc)


async def test_naming_and_unique_id(
    hass: HomeAssistant, mock_config_entry_phone, coordinator_with_data: XploraDataUpdateCoordinator
) -> None:
    sensor = _make_sensor(hass, mock_config_entry_phone, coordinator_with_data)
    assert sensor._attr_has_entity_name is True
    assert sensor.entity_id.startswith("sensor.")
    assert sensor.entity_id.endswith("_last_call_parent_name")
    assert "_last_call_" in sensor._attr_unique_id
    assert sensor._attr_unique_id == sensor._attr_unique_id.lower()
