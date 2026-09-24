"""Tests for XploraOptionsFlowHandler.async_step_init's schema construction (get_options)."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xplora_watch.config_flow import flatten_sections
from custom_components.xplora_watch.const import (
    CONF_ACCOUNT_ALIAS,
    CONF_HOME_LATITUDE,
    CONF_WATCHES,
    DOMAIN,
    OPTIONS_SECTIONS,
    SECTION_LOCATION,
    SECTION_WATCHES,
)
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from custom_components.xplora_watch.pyxplora_api.exception_classes import ConnectionError as XploraConnectionError
from tests.xplora_watch.fixtures.graphql_payloads import (
    DEFAULT_ACCOUNT_NAME,
    DEFAULT_WARD_NAME,
    DEFAULT_WUID,
    make_device_list_payload,
)


def _section(result, section_key: str) -> dict:
    """Return the inner field->selector mapping of one section of the options form.

    A section is `section(vol.Schema({...}))`, so it takes two unwraps to reach the field mapping:
    `section.schema` is the inner `vol.Schema`, and *its* `.schema` is the marker -> selector dict.
    """
    for key, value in result["data_schema"].schema.items():
        if getattr(key, "schema", key) == section_key:
            return value.schema.schema
    raise AssertionError(f"section {section_key!r} missing from {[getattr(k, 'schema', k) for k in result['data_schema'].schema]}")


def _field(section_schema: dict, field: str):
    """Return ``(marker, selector)`` for one field inside a section's schema."""
    for key, value in section_schema.items():
        if getattr(key, "schema", key) == field:
            return key, value
    raise AssertionError(f"field {field!r} missing from section")


_NEW_WUID = "watch-id-002"


def _grow_account_to_two_watches(graphql_operations: dict) -> None:
    """Point the mocked ``deviceList`` at a 2-watch account (the original plus a newly added one)."""
    original = make_device_list_payload(wuid=DEFAULT_WUID)
    added = make_device_list_payload(wuid=_NEW_WUID, ward_name="Kid Two", ward_phone="+491700000999")
    graphql_operations["deviceList"] = {"data": {"deviceList": original["deviceList"] + added["deviceList"]}}


def _watch_option_values(result: dict) -> set[str]:
    """The set of watch ids offered by the options-flow watch picker.

    The picker sits inside the `watches` section, so reaching it takes a section unwrap first.
    """
    _, watches_selector = _field(_section(result, SECTION_WATCHES), CONF_WATCHES)
    return {opt["value"] for opt in watches_selector.config["options"]}


async def test_async_step_init_builds_a_sectioned_schema(
    hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone
) -> None:
    """The options form is grouped into the expected collapsible sections.

    Sections are what keep a ~17-field dialog scannable; their keys double as the translation path
    (`options.step.init.sections.<key>`), so a drift here silently un-translates the whole form.
    """
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"] is not None
    assert [getattr(key, "schema", key) for key in result["data_schema"].schema] == list(OPTIONS_SECTIONS)


async def test_async_step_init_watches_show_child_name_label(
    hass, mock_config_entry_phone: MockConfigEntry, mock_graphql, mock_home_zone
) -> None:
    """The watches selector stores the watch id but shows the child's name as the label."""
    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    _, watches_selector = _field(_section(result, SECTION_WATCHES), CONF_WATCHES)
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

    alias_marker, _ = _field(_section(result, SECTION_WATCHES), CONF_ACCOUNT_ALIAS)
    default = alias_marker.default() if callable(alias_marker.default) else alias_marker.default
    assert default == DEFAULT_ACCOUNT_NAME


async def test_async_step_init_falls_back_when_home_zone_is_missing(hass, mock_config_entry_phone: MockConfigEntry, mock_graphql) -> None:
    """A missing/renamed `home` zone no longer blocks the whole options dialog.

    It used to raise `HomeAssistantError`, which locked the user out of *every* setting (polling,
    chat, alias) because of one geography field. The form now opens with Home Assistant's own
    configured location as the default instead.
    """
    assert hass.states.get("zone.home") is None

    result = await hass.config_entries.options.async_init(mock_config_entry_phone.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    home_latitude_marker, _ = _field(_section(result, SECTION_LOCATION), CONF_HOME_LATITUDE)
    default = home_latitude_marker.default() if callable(home_latitude_marker.default) else home_latitude_marker.default
    assert default == hass.config.latitude


def test_flatten_sections_merges_sections_and_passes_others_through() -> None:
    """A sectioned submission collapses to the flat options dict the rest of the code reads.

    The form submits `{"polling": {"scan_interval": "1800"}}`; the coordinator, the config registry
    and every entry written by an older version read a flat `{"scan_interval": 1800}`. Non-section
    keys are passed through so a future flat field keeps working.
    """
    assert flatten_sections({"polling": {"scan_interval": "1800"}, "legacy_key": 7}) == {
        "scan_interval": "1800",
        "legacy_key": 7,
    }
    # A section whose value is not a mapping is left alone (never silently dropped).
    assert flatten_sections({"chat": "not-a-dict"}) == {"chat": "not-a-dict"}


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
