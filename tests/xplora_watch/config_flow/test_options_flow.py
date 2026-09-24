"""Tests for XploraOptionsFlowHandler.async_step_init's schema construction (get_options)."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xplora_watch.config_flow import flatten_sections
from custom_components.xplora_watch.const import (
    CONF_ACCOUNT_ALIAS,
    CONF_HOME_LATITUDE,
    CONF_WATCHES,
    OPTIONS_SECTIONS,
    SECTION_LOCATION,
    SECTION_WATCHES,
)
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_ACCOUNT_NAME, DEFAULT_WARD_NAME, DEFAULT_WUID


def _section(result, section_key: str) -> dict:
    """Return the inner field->selector mapping of one section of the options form."""
    for key, value in result["data_schema"].schema.items():
        if getattr(key, "schema", key) == section_key:
            return value.schema
    raise AssertionError(f"section {section_key!r} missing from {[getattr(k, 'schema', k) for k in result['data_schema'].schema]}")


def _field(section_schema: dict, field: str):
    """Return ``(marker, selector)`` for one field inside a section's schema."""
    for key, value in section_schema.items():
        if getattr(key, "schema", key) == field:
            return key, value
    raise AssertionError(f"field {field!r} missing from section")


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
