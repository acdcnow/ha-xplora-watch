"""Logbook lines for the notification-feed events (ADR 0014/0016).

Each per-category event fired by the coordinator gets a full-detail, human-readable logbook line
(the event carries `device_id`, so HA anchors the line to the watch device). These lines persist to
the recorder DB and deliberately include contact numbers/names and SOS coordinates -- a documented
trade for in-UI visibility, not a privacy guarantee (ADR 0016).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME, LazyEventPartialState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_CALL_DIRECTION,
    ATTR_CALL_DURATION,
    ATTR_CALL_MISSED,
    ATTR_CALL_NAME,
    ATTR_CALL_NUMBER,
    DEVICE_NAME,
    DOMAIN,
    EVENT_CALL,
    EVENT_LOW_POWER,
    EVENT_POWER,
    EVENT_SOS,
)


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[LazyEventPartialState], dict[str, str]]], None],
) -> None:
    """Register human-readable descriptions for the notification-feed events."""

    def _watch_name(data: Mapping[str, Any]) -> str:
        device_id = data.get("device_id")
        if device_id:
            device = dr.async_get(hass).async_get(device_id)
            if device:
                return device.name_by_user or device.name or DEVICE_NAME
        return DEVICE_NAME

    def _battery_suffix(data: Mapping[str, Any]) -> str:
        battery = data.get("battery")
        return f" (battery {battery}%)" if battery is not None else ""

    @callback
    def describe_call(event: LazyEventPartialState) -> dict[str, str]:
        data = event.data
        contact = data.get(ATTR_CALL_NAME) or data.get(ATTR_CALL_NUMBER) or "an unknown contact"
        direction = data.get(ATTR_CALL_DIRECTION)
        kind = f"{direction} call" if direction else "call"
        if data.get(ATTR_CALL_MISSED):
            message = f"missed {kind} from {contact}"
        else:
            duration = data.get(ATTR_CALL_DURATION)
            message = f"{kind} with {contact}"
            if duration:
                message += f" for {duration}s"
        return {LOGBOOK_ENTRY_NAME: _watch_name(data), LOGBOOK_ENTRY_MESSAGE: message}

    @callback
    def describe_sos(event: LazyEventPartialState) -> dict[str, str]:
        data = event.data
        lat, lng = data.get("lat"), data.get("lng")
        where = f" at {lat}, {lng}" if lat is not None and lng is not None else ""
        message = f"triggered an SOS alert{where}{_battery_suffix(data)}"
        return {LOGBOOK_ENTRY_NAME: _watch_name(data), LOGBOOK_ENTRY_MESSAGE: message}

    @callback
    def describe_power(event: LazyEventPartialState) -> dict[str, str]:
        data = event.data
        message = ("powered on" if data.get("state") == "on" else "powered off") + _battery_suffix(data)
        return {LOGBOOK_ENTRY_NAME: _watch_name(data), LOGBOOK_ENTRY_MESSAGE: message}

    @callback
    def describe_low_power(event: LazyEventPartialState) -> dict[str, str]:
        data = event.data
        battery = data.get("battery")
        detail = f" ({battery}%)" if battery is not None else ""
        return {LOGBOOK_ENTRY_NAME: _watch_name(data), LOGBOOK_ENTRY_MESSAGE: f"reported low battery{detail}"}

    async_describe_event(DOMAIN, EVENT_CALL, describe_call)
    async_describe_event(DOMAIN, EVENT_SOS, describe_sos)
    async_describe_event(DOMAIN, EVENT_POWER, describe_power)
    async_describe_event(DOMAIN, EVENT_LOW_POWER, describe_low_power)
