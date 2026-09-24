"""Tests for the live-follow services (`follow` / `stop_follow`), via device targeting."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.xplora_watch.const import ATTR_SERVICE_FOLLOW, ATTR_SERVICE_STOP_FOLLOW, DOMAIN
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID

from ..conftest import setup_service_target


async def test_follow_starts_a_session_for_the_targeted_watch(hass: HomeAssistant, coordinator: XploraDataUpdateCoordinator) -> None:
    """A device target plus a duration starts a session for exactly that watch."""
    devices = await setup_service_target(hass, coordinator)

    with patch.object(coordinator, "async_start_follow", new=AsyncMock(return_value={})) as mock_follow:
        await hass.services.async_call(DOMAIN, ATTR_SERVICE_FOLLOW, {"device_id": [devices[DEFAULT_WUID]], "duration": 5}, blocking=True)

    mock_follow.assert_awaited_once_with([DEFAULT_WUID], 5.0)


async def test_follow_without_a_duration_uses_the_default(hass: HomeAssistant, coordinator: XploraDataUpdateCoordinator) -> None:
    """`duration` is optional: omitting it (a plain automation call) means "use the default"."""
    devices = await setup_service_target(hass, coordinator)

    with patch.object(coordinator, "async_start_follow", new=AsyncMock(return_value={})) as mock_follow:
        await hass.services.async_call(DOMAIN, ATTR_SERVICE_FOLLOW, {"device_id": [devices[DEFAULT_WUID]]}, blocking=True)

    mock_follow.assert_awaited_once_with([DEFAULT_WUID], None)


async def test_stop_follow_ends_the_session(hass: HomeAssistant, coordinator: XploraDataUpdateCoordinator) -> None:
    """`stop_follow` ends the session early; it needs no fields beyond the target."""
    devices = await setup_service_target(hass, coordinator)

    with patch.object(coordinator, "async_stop_follow", new=AsyncMock(return_value={})) as mock_stop:
        await hass.services.async_call(DOMAIN, ATTR_SERVICE_STOP_FOLLOW, {"device_id": [devices[DEFAULT_WUID]]}, blocking=True)

    mock_stop.assert_awaited_once_with([DEFAULT_WUID])


async def test_follow_skips_a_contact_watch_and_raises(hass: HomeAssistant, coordinator: XploraDataUpdateCoordinator) -> None:
    """A session drives `askWatchLocate`, which only a primary Guardian can trigger, so a
    Contact-only watch is skipped before any work happens -- and with nothing actioned the call
    raises rather than reporting a silent success."""
    coordinator.is_admin = {DEFAULT_WUID: False}
    devices = await setup_service_target(hass, coordinator)

    with patch.object(coordinator, "async_start_follow", new=AsyncMock(return_value={})) as mock_follow:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, ATTR_SERVICE_FOLLOW, {"device_id": [devices[DEFAULT_WUID]]}, blocking=True)

    mock_follow.assert_not_awaited()


async def test_follow_without_a_device_target_raises(hass: HomeAssistant, coordinator: XploraDataUpdateCoordinator) -> None:
    """An empty target is rejected before any session is started."""
    await setup_service_target(hass, coordinator)  # registers the services

    with patch.object(coordinator, "async_start_follow", new=AsyncMock(return_value={})) as mock_follow:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, ATTR_SERVICE_FOLLOW, {"device_id": []}, blocking=True)

    mock_follow.assert_not_awaited()
