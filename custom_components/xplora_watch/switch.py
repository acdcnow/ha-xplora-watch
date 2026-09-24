"""Live-follow switch for Xplora® Watch Version 2.

One switch per watch, `on` while a *live-follow* session is running for that watch: the
integration then refreshes its location every `FOLLOW_INTERVAL_SECONDS` instead of the configured
cadence (which is OFF by default). Switching it on starts a session with the default duration
(15 minutes), switching it off ends a running session early, and a session ends by itself -- so the
switch can never be left on by accident and the integration always falls back to its configured,
ban-safe cadence. `remaining` / `ends_at` / `interval` ride along as attributes so a dashboard can
show a countdown without a template sensor.

The switch is created only for a watch the account is the *Guardian* of (`SWITCH_LIVE_FOLLOW` is in
`GUARDIAN_ONLY_KEYS`): a session drives `askWatchLocate`, which only a primary Guardian can trigger,
so a Contact-only watch would get a control that silently does nothing.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import ENTITY_ID_FORMAT, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ID, CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_FOLLOW_ENDS_AT,
    ATTR_FOLLOW_INTERVAL,
    ATTR_FOLLOW_REMAINING,
    ATTR_WATCH,
    CONF_WATCHES,
    DOMAIN,
    FOLLOW_INTERVAL_SECONDS,
    SWITCH_LIVE_FOLLOW,
)
from .coordinator import XploraDataUpdateCoordinator
from .entity import XploraBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the per-watch live-follow switches from a config entry."""
    coordinator: XploraDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities: list[XploraFollowSwitch] = []
    for watch in coordinator.controller.watchs:
        options = config_entry.options
        if not options or not isinstance(watch, dict):
            _LOGGER.debug("%s %s - no config options", watch, config_entry.entry_id)
            continue

        ward = watch.get("ward", None)
        if not isinstance(ward, dict):
            continue

        wuid = ward.get(ATTR_ID)
        if wuid is None:
            continue

        conf_watches = options.get(CONF_WATCHES, None)
        if conf_watches is None or wuid not in conf_watches:
            continue

        # Guardian-only (see GUARDIAN_ONLY_KEYS): a Contact cannot trigger a fresh fix, so the
        # switch would have nothing to do. `is_confirmed_contact` fails open -- an unknown role is
        # treated as a Guardian, so incomplete data never hides the control.
        if coordinator.is_confirmed_contact(wuid):
            _LOGGER.debug("Skipping live-follow switch for watch ...%s: account is only a contact", wuid[25:])
            continue

        entities.append(XploraFollowSwitch(config_entry, coordinator, ward, wuid))

    async_add_entities(entities)


class XploraFollowSwitch(XploraBaseEntity, SwitchEntity):
    """Toggle that starts/stops a bounded live-follow session for one watch."""

    # A control, like the update/refresh buttons, so it groups with them in the UI instead of
    # sitting next to the diagnostic sensors.
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon: str | None = "mdi:radar"
    # Created enabled: switching it on is an explicit user action, it costs nothing while off, and
    # the whole point of the feature is to be reachable from a dashboard/automation without setup.
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: XploraDataUpdateCoordinator,
        ward: dict[str, Any],
        wuid: str,
    ) -> None:
        """Initialize a live-follow switch for an Xplora® Watch."""
        super().__init__(config_entry, None, coordinator, wuid)
        if self.watch_uid not in self.coordinator.data:
            return

        # has_entity_name: name only the role; the device supplies the "Kid One Watch" prefix.
        # Translated name (`entity.switch.live_follow.name`); the entity_id below is unchanged.
        self._attr_translation_key = SWITCH_LIVE_FOLLOW
        self.entity_id = ENTITY_ID_FORMAT.format(self.branded_object_id(SWITCH_LIVE_FOLLOW))

        # unique_id mirrors the other platforms so history/customizations stay stable across upgrades.
        self._attr_unique_id = (
            f"{ward.get(CONF_NAME)}_{ATTR_WATCH}_{SWITCH_LIVE_FOLLOW}_{wuid}_{coordinator.user_id}".replace(" ", "_")
            .replace("-", "_")
            .lower()
        )
        _LOGGER.debug("Updating switch: %s | Watch_ID ...%s", SWITCH_LIVE_FOLLOW, wuid[25:])

    @property
    def is_on(self) -> bool:
        """Whether a live-follow session is running for this watch right now."""
        return self.coordinator.follow_deadline(self.watch_uid) is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start a live-follow session with the default duration."""
        self._log.debug("Live follow switch turned on for watch ...%s", self.watch_uid[25:])
        await self.coordinator.async_start_follow([self.watch_uid])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """End this watch's live-follow session early."""
        self._log.debug("Live follow switch turned off for watch ...%s", self.watch_uid[25:])
        await self.coordinator.async_stop_follow([self.watch_uid])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Add the session countdown so a card can show it without a template sensor.

        The attributes are omitted entirely while the session is off, so an idle switch carries no
        stale `ends_at`.
        """
        attrs = dict(super().extra_state_attributes or {})
        attrs[ATTR_FOLLOW_INTERVAL] = FOLLOW_INTERVAL_SECONDS
        deadline = self.coordinator.follow_deadline(self.watch_uid)
        if deadline is not None:
            attrs[ATTR_FOLLOW_ENDS_AT] = deadline.isoformat()
            attrs[ATTR_FOLLOW_REMAINING] = self.coordinator.follow_remaining(self.watch_uid)
        return attrs
