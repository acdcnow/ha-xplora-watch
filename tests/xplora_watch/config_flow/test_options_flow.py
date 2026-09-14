"""Tests for XploraOptionsFlowHandler.async_step_init's schema construction (get_options)."""

from __future__ import annotations

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xplora_watch.const import CONF_ACCOUNT_ALIAS, CONF_WATCHES, DOMAIN
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from custom_components.xplora_watch.pyxplora_api.exception_classes import ConnectionError as XploraConnectionError
from tests.xplora_watch.fixtures.graphql_payloads import (
    DEFAULT_ACCOUNT_NAME,
    DEFAULT_WARD_NAME,
    DEFAULT_WUID,
    make_device_list_payload,
)

_NEW_WUID = "watch-id-002"


def _grow_account_to_two_watches(graphql_operations: dict) -> None:
    """Point the mocked ``deviceList`` at a 2-watch account (the original plus a newly added one)."""
    original = make_device_list_payload(wuid=DEFAULT_WUID)
    added = make_device_list_payload(wuid=_NEW_WUID, ward_name="Kid Two", ward_phone="+491700000999")
    graphql_operations["deviceList"] = {"data": {"deviceList": original["deviceList"] + added["deviceList"]}}


def _watch_option_values(result: dict) -> set[str]:
    """The set of watch ids offered by the options-flow watch picker."""
    schema = result["data_schema"].schema
    watches_selector = next(value for key, value in schema.items() if getattr(key, "schema", key) == CONF_WATCHES)
    return {opt["value"] for opt in watches_selector.config["options"]}


async def test_async_step_init_builds_schema_with_home_zone(
    hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone
) -> None:
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"] is not None


async def test_async_step_init_watches_show_child_name_label(
    hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone
) -> None:
    """The watches selector stores the watch id but shows the child's name as the label."""
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    schema = result["data_schema"].schema
    watches_selector = next(value for key, value in schema.items() if getattr(key, "schema", key) == CONF_WATCHES)
    options = watches_selector.config["options"]
    assert {"value": DEFAULT_WUID, "label": DEFAULT_WARD_NAME} in options


async def test_async_step_init_offers_editable_alias_prefilled_with_display_name(
    hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone
) -> None:
    """The options flow exposes an editable alias field, pre-filled for a pre-alias entry.

    When no alias has been set yet (neither options nor data), the field defaults to the Account
    display name from ``getUserName()`` so an existing entry can adopt or change it.
    """
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    schema = result["data_schema"].schema
    alias_key = next(key for key in schema if getattr(key, "schema", key) == CONF_ACCOUNT_ALIAS)
    default = alias_key.default() if callable(alias_key.default) else alias_key.default
    assert default == DEFAULT_ACCOUNT_NAME


async def test_async_step_init_raises_without_home_zone(hass, mock_config_entry_phone: MockConfigEntry, mock_graphql) -> None:
    with pytest.raises(HomeAssistantError):
        await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)


async def test_options_flow_lists_watch_added_after_setup(
    hass, coordinator: XploraDataUpdateCoordinator, graphql_operations, mock_home_zone
) -> None:
    """A watch added to the account after setup appears in the picker.

    Reproduces the real bug end to end: the options flow reuses the live coordinator's
    already-authenticated controller, whose ``_wuid`` is pinned to the saved (1-watch)
    ``CONF_WATCHES`` and whose ``self.watchs`` was loaded once at setup. Growing the account to
    two watches *after* the coordinator is built means the picker only lists the new watch if the
    flow both (a) force-reloads ``self.watchs`` (defeating the once-only load) and (b) enumerates
    the full account list rather than the pinned ``_wuid`` -- so a fix that addresses only one of
    the two staleness layers still fails this test.
    """
    entry = coordinator._entry
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    # The controller was built with self.watchs = [DEFAULT_WUID] and _wuid pinned to it; the
    # account only grows afterwards.
    assert [w["ward"]["id"] for w in coordinator.controller.watchs] == [DEFAULT_WUID]
    _grow_account_to_two_watches(graphql_operations)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    values = _watch_option_values(result)
    assert DEFAULT_WUID in values
    assert _NEW_WUID in values


async def test_options_flow_reload_preserves_entity_scoping(
    hass, coordinator: XploraDataUpdateCoordinator, graphql_operations, mock_home_zone
) -> None:
    """Opening the picker must not widen which watches get entities created.

    The force-reload repopulates ``self.watchs`` but must leave ``_wuid`` (the pinned
    ``CONF_WATCHES`` subset) untouched, since ``__init__.py`` scopes entity creation off
    ``getWatchUserIDs()`` -- which returns ``_wuid``. A regression that cleared ``_wuid`` would
    make the integration create entities for every account watch, not just the selected ones.
    """
    entry = coordinator._entry
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _grow_account_to_two_watches(graphql_operations)

    await hass.config_entries.options.async_init(entry.entry_id)

    assert coordinator.controller.getWatchUserIDs() == [DEFAULT_WUID]


async def test_options_flow_survives_watch_list_reload_failure(hass, coordinator: XploraDataUpdateCoordinator, mock_home_zone) -> None:
    """A transient deviceList failure must not block opening the options screen.

    Refreshing the account watch list is a best-effort convenience; if it fails, the flow should
    still open using the last-known list so the user can edit unrelated options (scan interval,
    alias, ...) rather than being locked out by a network blip.
    """
    entry = coordinator._entry
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    async def _boom() -> None:
        raise XploraConnectionError("deviceList unreachable")

    coordinator.controller.reload_watch_list = _boom  # type: ignore[method-assign]

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    # Falls back to the cached list, which still carries the configured watch.
    assert DEFAULT_WUID in _watch_option_values(result)


async def test_options_flow_sign_in_fallback_lists_full_account_without_extra_fetch(
    hass,
    mock_config_entry_phone: MockConfigEntry,
    graphql_operations,
    mock_graphql,
    mock_geocoding_openstreetmap,
    mock_home_zone,
) -> None:
    """With no loaded coordinator, the flow signs in fresh and lists the full account.

    ``sign_in`` runs ``init()``, which already loads the current account watch list into a
    controller with no pinned ``_wuid``; a force-reload there would be a redundant second
    ``deviceList`` fetch, so the flow must not call it on this path.
    """
    _grow_account_to_two_watches(graphql_operations)

    reload_calls = 0
    real_reload = None

    from custom_components.xplora_watch.pyxplora_api.pyxplora_api_async import PyXploraApi

    real_reload = PyXploraApi.reload_watch_list

    async def _counting_reload(self) -> None:  # type: ignore[no-untyped-def]
        nonlocal reload_calls
        reload_calls += 1
        await real_reload(self)

    PyXploraApi.reload_watch_list = _counting_reload  # type: ignore[method-assign]
    try:
        result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)
    finally:
        PyXploraApi.reload_watch_list = real_reload  # type: ignore[method-assign]

    values = _watch_option_values(result)
    assert DEFAULT_WUID in values
    assert _NEW_WUID in values
    assert reload_calls == 0
