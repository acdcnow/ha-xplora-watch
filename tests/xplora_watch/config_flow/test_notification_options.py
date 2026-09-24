"""Options-flow coverage for the per-category notification toggles (ADR 0016)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.xplora_watch as xplora_pkg
from custom_components.xplora_watch.config import resolve
from custom_components.xplora_watch.const import (
    CONF_NOTIFY_CALL,
    CONF_NOTIFY_LOW_POWER,
    CONF_NOTIFY_POWER,
    CONF_NOTIFY_SOS,
    SECTION_NOTIFICATIONS,
)
from tests.xplora_watch.config_flow.test_options_flow_submit import _base_submit_input

_NOTIFY_KEYS = (CONF_NOTIFY_SOS, CONF_NOTIFY_CALL, CONF_NOTIFY_POWER, CONF_NOTIFY_LOW_POWER)


def _submit_input(**overrides: Any) -> dict[str, Any]:
    """A complete sectioned submit payload with the given overrides applied.

    The options form is sectioned, so it submits its values nested under the section keys and the
    flow manager validates the payload against the schema before the step runs -- a flat payload
    would be rejected as "extra keys not allowed" instead of reaching the flow.
    """
    return _base_submit_input(**overrides)


def _schema_defaults(schema: Any) -> dict[str, Any]:
    """The notification toggles' defaults as the form builds them.

    The toggles live in the `notifications` section, so the section has to be unwrapped first.
    """
    defaults: dict[str, Any] = {}
    for key, value in schema.schema.items():
        if getattr(key, "schema", key) != SECTION_NOTIFICATIONS:
            continue
        for field_key in value.schema.schema:
            name = getattr(field_key, "schema", None)
            if name in _NOTIFY_KEYS:
                default = field_key.default
                defaults[name] = default() if callable(default) else default
    return defaults


async def test_toggle_defaults_sos_on_others_off(hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone) -> None:
    """Pin the ADR 0016 defaults: SOS on, calls/power/low-battery off."""
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)
    assert _schema_defaults(result["data_schema"]) == {
        CONF_NOTIFY_SOS: True,
        CONF_NOTIFY_CALL: False,
        CONF_NOTIFY_POWER: False,
        CONF_NOTIFY_LOW_POWER: False,
    }


async def test_enabling_calls_is_stored_and_resolves(hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone) -> None:
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], _submit_input(notify_call=True))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NOTIFY_CALL] is True
    assert resolve(result["data"]).notify_call is True
    # An untouched category keeps its default (SOS on).
    assert result["data"][CONF_NOTIFY_SOS] is True


async def test_disabling_sos_persists(hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone) -> None:
    """Turning the SOS default off round-trips (Required-with-default writes the value)."""
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], _submit_input(notify_sos=False))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NOTIFY_SOS] is False
    assert resolve(result["data"]).notify_sos is False


def test_options_strings_carry_the_pii_warning() -> None:
    """Both the source strings and the served English translation must warn, per category, that
    enabling calls/SOS writes that category's PII into the recorder (ADR 0016)."""
    base = Path(xplora_pkg.__file__).parent
    for filename in ("strings.json", "translations/en.json"):
        descriptions = json.loads((base / filename).read_text(encoding="utf-8"))["options"]["step"]["init"]["sections"][
            SECTION_NOTIFICATIONS
        ]["data_description"]
        call = descriptions[CONF_NOTIFY_CALL].lower()
        sos = descriptions[CONF_NOTIFY_SOS].lower()
        # The call warning names contact PII + the recorder; the SOS warning names the GPS location.
        assert "recorder" in call and ("phone number" in call or "contact" in call)
        assert "recorder" in sos and ("location" in sos or "latitude" in sos or "gps" in sos)
        # A load-bearing disclosure phrase, so a gutted-but-still-keyworded rewrite can't pass.
        assert "not a privacy guarantee" in call and "not a privacy guarantee" in sos


def test_feature_docs_disclose_recorder_pii() -> None:
    """ADR 0016 binds the PII disclosure to the feature docs too, not only the options strings."""
    repo_root = Path(xplora_pkg.__file__).parent.parent.parent
    doc = (repo_root / "docs" / "notifications.md").read_text(encoding="utf-8").lower()
    assert "recorder database" in doc
    assert "phone number" in doc
    assert "not" in doc and "privacy guarantee" in doc
