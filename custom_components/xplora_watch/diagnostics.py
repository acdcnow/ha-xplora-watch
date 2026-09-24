"""Diagnostics support for HA Xplora® Watch.

Settings → Devices & Services → HA Xplora® Watch → *Download diagnostics* hands the user (or a bug
report) a snapshot of the config entry and the live coordinator state. Two rules shape what is
included:

* **Never leak a secret.** The account password, the Xplora® session/token blob and the OpenCage
  API key are redacted, as are the account's e-mail/phone number and every watch IMEI.
* **Summarize, don't dump.** Chat message bodies and raw location-history point lists are personal
  data and would make the file enormous, so only their *shape* (counts, retained days) is reported.
  The point-in-time status fields, the current position and the per-watch role are kept, because
  they are what a "why does my sensor say X" report actually needs.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .config import resolve
from .const import CONF_ACCOUNT_ALIAS, DOMAIN
from .coordinator import XploraDataUpdateCoordinator

# Keys stripped from the entry data/options *and* from any coordinator payload before it is handed
# out. `email`/`phonenumber`/`imei` are personal data, the rest are credentials.
TO_REDACT: set[str] = {
    "password",
    "email",
    "phonenumber",
    "imei",
    "opencage_apikey",
    "token",
    "access_token",
    "refresh_token",
    "issue_token",
    "device_key",
    "devicekey",
    "qr_code",
    "qrcode",
    "qrt",
    "qrc",
}


def _watch_diagnostics(coordinator: XploraDataUpdateCoordinator, wuid: str) -> dict[str, Any]:
    """A redacted, human-readable snapshot of one watch's coordinator data."""
    data = (coordinator.data or {}).get(wuid) or {}
    messages = data.get("message") or {}
    history = data.get("location_history") or {}
    return {
        # Live status (the values the sensors expose).
        "battery": data.get("battery"),
        "is_charging": data.get("isCharging"),
        "is_online": data.get("isOnline"),
        "is_safezone_alert": data.get("isSafezone"),
        "safezone_label": data.get("safeZoneLabel"),
        "steps_today": data.get("step_day"),
        "xcoins": data.get("xcoin"),
        "unread_messages": data.get("unreadMsg"),
        "locate_type": data.get("locateType"),
        "location_accuracy_m": data.get("location_accuracy"),
        "latitude": data.get("lat"),
        "longitude": data.get("lng"),
        "last_track_time": data.get("lastTrackTime"),
        "last_update_status": data.get("last_update_status"),
        "last_update_time": data.get("last_update_time"),
        # Device identity (no IMEI -- redacted as personal data).
        "model": data.get("model"),
        "os_version": data.get("os_version"),
        # Shape-only views of the bulky/personal payloads.
        "alarms": len(data.get("alarm") or []),
        "silent_times": len(data.get("silent") or []),
        "chat_messages_loaded": len(messages.get("list") or []) if isinstance(messages, dict) else 0,
        "history_points_retained": history.get("total") if isinstance(history, dict) else None,
        "history_points_in_window": len(history.get("points") or []) if isinstance(history, dict) else None,
        "cached_history_days": coordinator.cached_history_days(wuid),
        # Account role for this watch (drives which entities exist at all).
        "is_primary_guardian": coordinator.is_admin.get(wuid),
        "is_confirmed_contact": coordinator.is_confirmed_contact(wuid),
    }


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = str(integration.version)
    except Exception:  # noqa: BLE001 -- the version is a nice-to-have; never fail the download
        version = "unknown"

    coordinator: XploraDataUpdateCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    diagnostics: dict[str, Any] = {
        "integration_version": version,
        "entry": {
            "title": entry.title,
            "unique_id": async_redact_data({"id": entry.unique_id}, TO_REDACT)["id"],
            "state": str(entry.state),
            "source": entry.source,
            "version": entry.version,
            "account_alias": entry.options.get(CONF_ACCOUNT_ALIAS, entry.data.get(CONF_ACCOUNT_ALIAS)),
            "watches_selected": len(entry.options.get("watches") or []),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
    }

    if coordinator is None:
        # Entry exists but is not (currently) set up -- report that instead of crashing on a None
        # coordinator, which is exactly the state a user downloads diagnostics from.
        diagnostics["coordinator"] = "not loaded"
        return diagnostics

    resolved = resolve(entry.options)
    diagnostics["runtime"] = {
        "account_user_id": coordinator.user_id,
        "account_display_name": coordinator.username,
        "polling_interval_s": resolved.scan_interval,
        "functions_interval_s": resolved.scan_interval_functions,
        "refresh_on_card_render": resolved.refresh_on_card_render,
        "home_is_safezone": resolved.home_is_safezone,
        "maps": resolved.maps,
        "message_limit": resolved.message,
        "auto_mark_read": resolved.auto_mark_read,
        "remove_message": resolved.remove_message,
        "auto_fetch_history": resolved.auto_fetch_history,
        "history_retention_days": resolved.history_retention_days,
        "watch_ids": sorted((coordinator.data or {}).keys()),
        # When each watch last had its slow-changing "functions" data (alarms / silent times / safe
        # zone definitions) fetched -- the answer to "why is my alarms sensor empty?" when the
        # functions-poll interval is off.
        "last_functions_fetch": {wuid: stamp.isoformat() for wuid, stamp in sorted(coordinator.functions_fetch_times().items())},
    }
    diagnostics["watches"] = {wuid: _watch_diagnostics(coordinator, wuid) for wuid in sorted((coordinator.data or {}).keys())}
    # Phone numbers and the OpenCage key can also appear inside nested payloads; a final uniform
    # pass makes that impossible to forget as new fields are added above.
    return async_redact_data(diagnostics, TO_REDACT)
