"""Tests for XploraOptionsFlowHandler.async_step_init's user_input submission/validation."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_LANGUAGE, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xplora_watch.const import (
    CONF_ACCOUNT_ALIAS,
    CONF_AUTO_FETCH_HISTORY,
    CONF_AUTO_MARK_READ,
    CONF_HISTORY_RETENTION_DAYS,
    CONF_HOME_LATITUDE,
    CONF_HOME_LONGITUDE,
    CONF_HOME_RADIUS,
    CONF_HOME_SAFEZONE,
    CONF_MAPS,
    CONF_MESSAGE,
    CONF_NOTIFY_CALL,
    CONF_NOTIFY_LOW_POWER,
    CONF_NOTIFY_POWER,
    CONF_NOTIFY_SOS,
    CONF_OPENCAGE_APIKEY,
    CONF_REFRESH_ON_CARD_RENDER,
    CONF_REMOVE_MESSAGE,
    CONF_SCAN_INTERVAL_FUNCTIONS,
    CONF_SIGNIN_TYP,
    CONF_WATCHES,
    HISTORY_RETENTION_DAYS_MAX,
    MAPS,
    OPTIONS_SECTIONS,
    SECTION_CHAT,
    SECTION_GENERAL,
    SECTION_HISTORY,
    SECTION_LOCATION,
    SECTION_NOTIFICATIONS,
    SECTION_POLLING,
    SECTION_WATCHES,
)
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID

# Which section each option lives in, mirroring `XploraOptionsFlowHandler.get_options`. A sectioned
# form submits its values **nested** under the section key, so the tests have to build that shape --
# and the flow manager validates the payload against the schema before the step ever runs, so a flat
# payload would be rejected as "extra keys not allowed" instead of reaching the flow.
_FIELD_SECTIONS: dict[str, str] = {
    CONF_WATCHES: SECTION_WATCHES,
    CONF_ACCOUNT_ALIAS: SECTION_WATCHES,
    CONF_SCAN_INTERVAL: SECTION_POLLING,
    CONF_SCAN_INTERVAL_FUNCTIONS: SECTION_POLLING,
    CONF_REFRESH_ON_CARD_RENDER: SECTION_POLLING,
    CONF_HOME_SAFEZONE: SECTION_LOCATION,
    CONF_HOME_LATITUDE: SECTION_LOCATION,
    CONF_HOME_LONGITUDE: SECTION_LOCATION,
    CONF_HOME_RADIUS: SECTION_LOCATION,
    CONF_MAPS: SECTION_LOCATION,
    CONF_OPENCAGE_APIKEY: SECTION_LOCATION,
    CONF_MESSAGE: SECTION_CHAT,
    CONF_REMOVE_MESSAGE: SECTION_CHAT,
    CONF_AUTO_MARK_READ: SECTION_CHAT,
    CONF_NOTIFY_SOS: SECTION_NOTIFICATIONS,
    CONF_NOTIFY_CALL: SECTION_NOTIFICATIONS,
    CONF_NOTIFY_POWER: SECTION_NOTIFICATIONS,
    CONF_NOTIFY_LOW_POWER: SECTION_NOTIFICATIONS,
    CONF_AUTO_FETCH_HISTORY: SECTION_HISTORY,
    CONF_HISTORY_RETENTION_DAYS: SECTION_HISTORY,
    CONF_LANGUAGE: SECTION_GENERAL,
    CONF_SIGNIN_TYP: SECTION_GENERAL,
}


def _nest(flat: dict[str, Any]) -> dict[str, Any]:
    """Group a flat field->value mapping into the sectioned shape the form submits."""
    nested: dict[str, Any] = {name: {} for name in OPTIONS_SECTIONS}
    for key, value in flat.items():
        nested[_FIELD_SECTIONS[key]][key] = value
    return nested


def _base_submit_input(**overrides: Any) -> dict[str, Any]:
    flat: dict[str, Any] = {
        CONF_SIGNIN_TYP: "Signed up with a phone number",
        CONF_WATCHES: [DEFAULT_WUID],
        CONF_LANGUAGE: "en",
        CONF_MAPS: MAPS[0],
        CONF_OPENCAGE_APIKEY: "",
        # Scan interval is now a preset SelectSelector; the UI hands back the seconds as a string.
        CONF_SCAN_INTERVAL: "1800",
        CONF_SCAN_INTERVAL_FUNCTIONS: "0",
        CONF_REFRESH_ON_CARD_RENDER: False,
        CONF_HOME_SAFEZONE: "off",
        CONF_HOME_LATITUDE: 52.5200,
        CONF_HOME_LONGITUDE: 13.4050,
        CONF_HOME_RADIUS: 100,
        CONF_MESSAGE: 10,
        CONF_REMOVE_MESSAGE: False,
        CONF_AUTO_MARK_READ: False,
        # ADR 0016 defaults: SOS on, the remaining notification categories off.
        CONF_NOTIFY_SOS: True,
        CONF_NOTIFY_CALL: False,
        CONF_NOTIFY_POWER: False,
        CONF_NOTIFY_LOW_POWER: False,
        CONF_AUTO_FETCH_HISTORY: False,
        CONF_HISTORY_RETENTION_DAYS: 14,
    }
    flat.update(overrides)
    return _nest(flat)


async def test_submit_happy_path_creates_options_entry(
    hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone
) -> None:
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _base_submit_input(**{CONF_WATCHES: [DEFAULT_WUID], CONF_MAPS: MAPS[0]})
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_WATCHES] == [DEFAULT_WUID]
    assert result["data"][CONF_MAPS] == MAPS[0]
    # The string preset is coerced back to the canonical int before storage.
    assert result["data"][CONF_SCAN_INTERVAL] == 1800
    # The retention field is stored (default filled by the schema when omitted from the submit).
    assert isinstance(result["data"][CONF_HISTORY_RETENTION_DAYS], int)


async def test_submit_history_retention_is_stored(hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone) -> None:
    """An in-range retention value is normalized (kept) and stored as a canonical int."""
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], _base_submit_input(**{CONF_HISTORY_RETENTION_DAYS: 14}))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HISTORY_RETENTION_DAYS] == 14
    assert result["data"][CONF_HISTORY_RETENTION_DAYS] <= HISTORY_RETENTION_DAYS_MAX


async def test_submit_empty_watches_shows_no_watch_error(
    hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone
) -> None:
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    result = await hass.config_entries.options.async_configure(result["flow_id"], _base_submit_input(**{CONF_WATCHES: []}))

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {"base": "no_watch"}


async def test_submit_opencage_maps_without_apikey_shows_api_key_error(
    hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone
) -> None:
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _base_submit_input(**{CONF_MAPS: MAPS[1], CONF_OPENCAGE_APIKEY: ""}),
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {"base": "api_key_error"}


async def test_submit_auto_fetch_history_stored(hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone) -> None:
    """``CONF_AUTO_FETCH_HISTORY`` is accepted and stored when submitted."""
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _base_submit_input(**{CONF_AUTO_FETCH_HISTORY: True}),
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTO_FETCH_HISTORY] is True


async def test_submit_account_alias_stored(hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone) -> None:
    """The account alias submitted in the options flow is stored in the entry's options.

    Because ``resolve_account_alias`` reads options before data, this edited value wins over any
    alias captured at setup, so the device name reflects it on the next load (ref:XW-010).
    """
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _base_submit_input(**{CONF_ACCOUNT_ALIAS: "Mom"}),
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ACCOUNT_ALIAS] == "Mom"
