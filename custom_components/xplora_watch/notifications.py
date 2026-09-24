"""Turn the account notification feed into per-category HA events (ADR 0014/0015/0016).

Pure, Home-Assistant-free planning: given the fetched feed entries (newest-first `SimpleChat`), the
persisted per-account high-water mark, and which categories are currently enabled, decide which
entries are new and build each event's payload. The coordinator owns the network fetch, per-watch
device routing, event firing, and `Store` persistence of the mark.

"New" is derived read-only from the entry `create`/`id` -- never from the server `readFlag`, and the
`setReadAllNotifications` mutation is never called (ADR 0015).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import EVENT_CALL, EVENT_LOW_POWER, EVENT_POWER, EVENT_SOS
from .pyxplora_api.model import Data, SimpleChat
from .pyxplora_api.status import ChatType

# `call_mode_detail == 50` is the reliable declined/rejected signal on watches that send it
# (ref:XW-020); `call_mode == 2` is the older equivalent.
_MISSED_CALL_MODE_DETAIL = 50
_MISSED_CALL_MODE = 2

# ChatType value -> (ResolvedOptions option field, HA event type). POWER_ON/POWER_OFF share one
# event, distinguished by the payload `state` (ADR 0014).
_CATEGORIES: dict[str, tuple[str, str]] = {
    ChatType.CALL_LOG.value: ("notify_call", EVENT_CALL),
    ChatType.SOS.value: ("notify_sos", EVENT_SOS),
    ChatType.POWER_ON.value: ("notify_power", EVENT_POWER),
    ChatType.POWER_OFF.value: ("notify_power", EVENT_POWER),
    ChatType.LOW_POWER.value: ("notify_low_power", EVENT_LOW_POWER),
}


@dataclass(frozen=True)
class HighWater:
    """The per-account dedupe cursor (ADR 0015).

    `create` is the newest entry's epoch-second seen so far; `ids` is the set of entry ids already
    seen at *exactly* that second. Tracking the boundary second's ids (not just the newest id) makes
    dedupe order-independent: a genuinely-new entry sharing that second fires exactly once, and a
    feed that returns same-second entries in a different order across polls never re-fires one
    already emitted. The set only ever holds the ids at the single most-recent second (it resets when
    a newer second arrives), so it stays tiny -- this rests on `create` advancing across polls, which
    it always does for a real backend (a genuinely newer event carries a later second).
    """

    create: int
    ids: frozenset[str]


@dataclass(frozen=True)
class PlannedEvent:
    """One event to fire. `wuid` is the entry's `sender.id`; the coordinator routes it to that
    watch's device and adds `device_id` to `data` before firing on the bus."""

    wuid: str
    event_type: str
    data: dict[str, Any]


@dataclass(frozen=True)
class PlanResult:
    events: list[PlannedEvent]
    mark: HighWater | None
    # True when every fetched entry was newer than the mark -- the coordinator pairs this with a
    # full page to warn about an overflow it did not page deeper to catch (ADR 0015).
    saw_only_new: bool


def _direction(call_type: int | None) -> str | None:
    # Inferred mapping (ref:XW-020); carried as a value, never baked into an event type.
    return {1: "outgoing", 2: "incoming"}.get(call_type) if call_type is not None else None


def _missed(data: Data) -> bool:
    if data.call_mode_detail is not None or data.call_mode is not None:
        return data.call_mode_detail == _MISSED_CALL_MODE_DETAIL or data.call_mode == _MISSED_CALL_MODE
    # Older watch without the mode fields: duration 0 = not connected (weaker heuristic).
    return data.duration == 0


def _build_payload(entry: SimpleChat) -> dict[str, Any]:
    data = entry.data or Data()
    payload: dict[str, Any] = {"id": entry.id, "create": entry.create}
    entry_type = entry.type
    if entry_type == ChatType.CALL_LOG.value:
        payload.update(
            direction=_direction(data.call_type),
            duration=data.duration,
            missed=_missed(data),
            call_name=data.call_name,
            call_number=data.call_number,
            call_time=data.call_time,
        )
    elif entry_type == ChatType.SOS.value:
        payload.update(lat=data.lat, lng=data.lng, battery=data.battery)
    elif entry_type in (ChatType.POWER_ON.value, ChatType.POWER_OFF.value):
        payload.update(
            state="on" if entry_type == ChatType.POWER_ON.value else "off",
            lat=data.lat,
            lng=data.lng,
            battery=data.battery,
        )
    elif entry_type == ChatType.LOW_POWER.value:
        payload.update(battery=data.battery)
    return payload


def plan_events(entries: list[SimpleChat], mark: HighWater | None, enabled: set[str]) -> PlanResult:
    """Plan the events for one poll of the feed.

    `entries` is the fetched page (any order; sorted here). `mark` is the prior high-water mark, or
    ``None`` for a baseline-silent bootstrap (first fetch). `enabled` is the set of option fields
    whose category is on. Returns the events to fire (oldest-first), the advanced mark, and whether
    every fetched entry was new.
    """
    # Skip entries missing the fields we key on (bad/partial data), then order newest-first.
    usable = sorted((e for e in entries if e.create is not None and e.id), key=lambda e: e.create or 0, reverse=True)
    if not usable:
        return PlanResult(events=[], mark=mark, saw_only_new=False)

    # Advance the cursor: the newest second seen (never below the stored mark), plus every id at that
    # boundary second -- accumulated across polls while the second is unchanged, reset when it grows.
    top_create = usable[0].create or 0
    new_create = max(top_create, mark.create) if mark is not None else top_create
    boundary_ids = {e.id or "" for e in usable if (e.create or 0) == new_create}
    if mark is not None and mark.create == new_create:
        boundary_ids |= mark.ids
    new_mark = HighWater(create=new_create, ids=frozenset(boundary_ids))

    # Baseline-silent: record the mark, fire nothing.
    if mark is None:
        return PlanResult(events=[], mark=new_mark, saw_only_new=False)

    # "New" is order-independent: an entry newer than the mark second, or -- at the mark second --
    # one whose id has not been seen there yet. This never re-fires an already-seen entry even if the
    # feed returns same-second entries in a different order between polls (ADR 0015).
    def _is_new(entry: SimpleChat) -> bool:
        create = entry.create or 0
        if create > mark.create:
            return True
        return create == mark.create and (entry.id or "") not in mark.ids

    new_entries = [e for e in usable if _is_new(e)]
    saw_only_new = bool(new_entries) and len(new_entries) == len(usable)

    events: list[PlannedEvent] = []
    for entry in reversed(new_entries):  # oldest-first
        category = _CATEGORIES.get(entry.type or "")
        if category is None:
            continue
        option_field, event_type = category
        if option_field not in enabled:
            continue
        events.append(PlannedEvent(wuid=(entry.sender.id if entry.sender else "") or "", event_type=event_type, data=_build_payload(entry)))

    return PlanResult(events=events, mark=new_mark, saw_only_new=saw_only_new)
