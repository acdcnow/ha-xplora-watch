"""Tests for the live-follow session in the coordinator.

A session is a bounded, user-triggered fast-poll window: refresh the chosen watches every
`FOLLOW_INTERVAL_SECONDS` until the requested duration has elapsed, then stop by itself. These tests
pin down the safety envelope that makes that acceptable in an integration whose whole point is to
stay off the rate-limit radar -- the session never outlives its deadline, never stacks a second
timer, ends on a reload/restart (teardown), and aborts immediately when Xplora reports a rate limit
instead of retrying into a ban.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.xplora_watch.const import (
    FOLLOW_DEFAULT_MINUTES,
    FOLLOW_INTERVAL_SECONDS,
    FOLLOW_MAX_MINUTES,
    FOLLOW_MIN_MINUTES,
    normalize_follow_minutes,
)
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, FOLLOW_DEFAULT_MINUTES),
        ("", FOLLOW_DEFAULT_MINUTES),
        ("abc", FOLLOW_DEFAULT_MINUTES),
        (0, FOLLOW_MIN_MINUTES),
        (-5, FOLLOW_MIN_MINUTES),
        (1, 1),
        (15, 15),
        ("7", 7),
        (5.6, 6),
        (FOLLOW_MAX_MINUTES, FOLLOW_MAX_MINUTES),
        (240, FOLLOW_MAX_MINUTES),
    ],
)
def test_normalize_follow_minutes_clamps_into_the_supported_window(raw: object, expected: int) -> None:
    """A requested duration is clamped into [1, 60] minutes, never rejected (an automation passing
    a silly value still gets a bounded session) and defaulting to 15 minutes when absent."""
    assert normalize_follow_minutes(raw) == expected


async def test_start_refreshes_immediately_and_arms_one_timer(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """Starting a session refreshes the watch right away -- waiting a full interval would feel broken
    -- and arms exactly one timer."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()) as mock_update:
        state = await coordinator.async_start_follow([DEFAULT_WUID])

    mock_update.assert_awaited_once_with(targets=[DEFAULT_WUID])
    assert coordinator.follow_deadline(DEFAULT_WUID) is not None
    assert coordinator._cancel_follow is not None
    assert state["wuids"] == [DEFAULT_WUID]
    assert state["interval"] == FOLLOW_INTERVAL_SECONDS
    coordinator.async_teardown()


async def test_default_duration_is_fifteen_minutes(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """Without a `duration` the session runs for the documented default (15 minutes)."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await coordinator.async_start_follow([DEFAULT_WUID])

    remaining = coordinator.follow_remaining(DEFAULT_WUID)
    assert remaining is not None
    assert FOLLOW_DEFAULT_MINUTES * 60 - 5 <= remaining <= FOLLOW_DEFAULT_MINUTES * 60
    coordinator.async_teardown()


async def test_duration_is_capped_at_sixty_minutes(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """An over-long request is clamped, so a follow session can never become an overnight poll."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await coordinator.async_start_follow([DEFAULT_WUID], 600)

    remaining = coordinator.follow_remaining(DEFAULT_WUID)
    assert remaining is not None
    assert FOLLOW_MAX_MINUTES * 60 - 5 <= remaining <= FOLLOW_MAX_MINUTES * 60
    coordinator.async_teardown()


async def test_a_second_start_extends_without_stacking_a_timer(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """Re-triggering the service (or the switch) moves the deadline and reuses the running timer."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await coordinator.async_start_follow([DEFAULT_WUID], 5)
        timer = coordinator._cancel_follow
        first_deadline = coordinator.follow_deadline(DEFAULT_WUID)
        await coordinator.async_start_follow([DEFAULT_WUID], 30)

    second_deadline = coordinator.follow_deadline(DEFAULT_WUID)
    assert timer is coordinator._cancel_follow  # same handle: nothing stacked
    assert first_deadline is not None and second_deadline is not None
    assert second_deadline > first_deadline + timedelta(minutes=20)
    coordinator.async_teardown()


async def test_tick_refreshes_only_while_the_session_is_alive(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """A tick inside the window refreshes the following watch; once the deadline has passed the
    session ends, the timer is released and no further request is made."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await coordinator.async_start_follow([DEFAULT_WUID])

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()) as mock_update:
        await coordinator._follow_tick(datetime.now())
    mock_update.assert_awaited_once_with(targets=[DEFAULT_WUID])

    # Simulate the deadline passing instead of waiting it out.
    coordinator._follow_deadlines[DEFAULT_WUID] = datetime.now() - timedelta(seconds=1)
    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()) as mock_update:
        await coordinator._follow_tick(datetime.now())

    mock_update.assert_not_awaited()
    assert coordinator.follow_deadline(DEFAULT_WUID) is None
    assert coordinator._cancel_follow is None


async def test_rate_limit_aborts_the_session_immediately(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """A 429 ends the session instead of being retried: `_fetch_and_store_xplora_data` turns it into
    an `UpdateFailed` (losing the type), so the recorded rate-limit stamp is what the follow loop
    checks -- retrying a rate limit every 30 s is exactly how an account gets banned."""
    coordinator = coordinator_with_data

    async def _rate_limited(**_kwargs: object) -> dict:
        coordinator._rate_limited_at = datetime.now()
        raise UpdateFailed("Xplora API rate limit exceeded")

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock(side_effect=_rate_limited)):
        await coordinator.async_start_follow([DEFAULT_WUID])

    assert coordinator.follow_deadline(DEFAULT_WUID) is None
    assert coordinator._cancel_follow is None
    assert coordinator._follow_deadlines == {}


async def test_a_transient_failure_keeps_the_session_running(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """An ordinary poll failure (watch out of reach, no rate limit) must NOT end a session the user
    started: the session is time-boxed, so the next tick simply tries again."""
    coordinator = coordinator_with_data

    async def _fails(**_kwargs: object) -> dict:
        raise UpdateFailed("Xplora connection error")

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock(side_effect=_fails)):
        await coordinator.async_start_follow([DEFAULT_WUID])

    assert coordinator.follow_deadline(DEFAULT_WUID) is not None
    assert coordinator._cancel_follow is not None
    coordinator.async_teardown()


async def test_stop_ends_the_session_and_releases_the_timer(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """Stopping clears the deadline and cancels the timer, so an idle integration runs no timer."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await coordinator.async_start_follow([DEFAULT_WUID])
    await coordinator.async_stop_follow([DEFAULT_WUID])

    assert coordinator.follow_deadline(DEFAULT_WUID) is None
    assert coordinator._cancel_follow is None
    assert coordinator.follow_state([DEFAULT_WUID])["wuids"] == []


async def test_start_without_targets_is_a_noop(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """An empty target list must not arm a timer that refreshes nothing."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()) as mock_update:
        await coordinator.async_start_follow([])

    mock_update.assert_not_awaited()
    assert coordinator._cancel_follow is None


async def test_teardown_ends_every_session(coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """A session is in-memory only: on unload/reload the timer is cancelled and the deadlines are
    dropped, so a restart never resumes a fast poll nobody is watching."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await coordinator.async_start_follow([DEFAULT_WUID])

    coordinator.async_teardown()

    assert coordinator._cancel_follow is None
    assert coordinator._follow_deadlines == {}
    assert coordinator.follow_deadline(DEFAULT_WUID) is None


async def test_follow_state_reports_the_countdown(hass: HomeAssistant, coordinator_with_data: XploraDataUpdateCoordinator) -> None:
    """`follow_state` (the switch attributes and the service response) carries the interval plus the
    session's end time and remaining seconds for the watches that are following."""
    coordinator = coordinator_with_data

    with patch.object(coordinator, "async_update_xplora_data", new=AsyncMock()):
        await coordinator.async_start_follow([DEFAULT_WUID], 5)

    state = coordinator.follow_state([DEFAULT_WUID])
    assert state["interval"] == FOLLOW_INTERVAL_SECONDS
    assert state["ends_at"] == coordinator.follow_deadline(DEFAULT_WUID).isoformat()
    assert state["remaining"] == coordinator.follow_remaining(DEFAULT_WUID)
    assert 0 < state["remaining"] <= 5 * 60
    coordinator.async_teardown()
