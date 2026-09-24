"""Pure planner tests for the notification feed (ADR 0014/0015/0016).

Covers baseline-silent bootstrap, high-water dedupe, per-category enable gating, per-watch routing
via sender.id, and each category's event payload (call direction/missed, SOS, power, low battery).
No Home Assistant, no network -- just the pure planning logic over `SimpleChat` entries.
"""

from __future__ import annotations

from typing import Any

from custom_components.xplora_watch.const import EVENT_CALL, EVENT_LOW_POWER, EVENT_POWER, EVENT_SOS
from custom_components.xplora_watch.notifications import HighWater, plan_events
from custom_components.xplora_watch.pyxplora_api.model import SimpleChat

# Every category enabled -- individual tests narrow this to prove gating.
ALL = {"notify_call", "notify_sos", "notify_power", "notify_low_power"}


def _entry(id: str, type: str, create: int, sender: str = "w-uid", **data: Any) -> SimpleChat:
    return SimpleChat.from_dict(
        {"id": id, "type": type, "create": create, "sender": {"id": sender}, "receiver": {"id": "guardian"}, "data": data}
    )


def _feed(*entries: SimpleChat) -> list[SimpleChat]:
    # Feed is returned newest-first; sort so tests can list entries in any order.
    return sorted(entries, key=lambda e: e.create or 0, reverse=True)


def test_baseline_silent_first_fetch_fires_nothing_but_sets_mark() -> None:
    feed = _feed(_entry("a", "CALL_LOG", 100), _entry("b", "SOS", 200))
    result = plan_events(feed, mark=None, enabled=ALL)
    assert result.events == []
    assert result.mark == HighWater(create=200, ids=frozenset({"b"}))


def test_only_entries_newer_than_mark_fire() -> None:
    feed = _feed(_entry("old", "SOS", 100), _entry("new", "SOS", 300))
    result = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"old"})), enabled=ALL)
    assert [e.data["id"] for e in result.events] == ["new"]
    assert result.mark == HighWater(create=300, ids=frozenset({"new"}))


def test_events_are_ordered_oldest_first() -> None:
    feed = _feed(_entry("n1", "SOS", 210), _entry("n2", "SOS", 220), _entry("n3", "SOS", 230))
    result = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL)
    assert [e.data["id"] for e in result.events] == ["n1", "n2", "n3"]


def test_disabled_category_does_not_fire_but_still_advances_mark() -> None:
    # Baseline-silent-on-enable: the mark advances past a disabled category's entry, so enabling it
    # later does not replay the backlog (ADR 0015/0016).
    feed = _feed(_entry("call", "CALL_LOG", 300))
    result = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled={"notify_sos"})
    assert result.events == []
    assert result.mark == HighWater(create=300, ids=frozenset({"call"}))


def test_routing_carries_sender_id_as_wuid() -> None:
    feed = _feed(_entry("s", "SOS", 300, sender="watch-42"))
    result = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL)
    assert result.events[0].wuid == "watch-42"


def test_call_payload_incoming_missed_by_call_mode_detail() -> None:
    feed = _feed(
        _entry(
            "c",
            "CALL_LOG",
            300,
            call_type=2,
            duration=0,
            call_name="Mum",
            call_number="+491234567",
            call_time=299,
            call_mode_detail=50,
        )
    )
    ev = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL).events[0]
    assert ev.event_type == EVENT_CALL
    assert ev.data["direction"] == "incoming"
    assert ev.data["missed"] is True
    assert ev.data["duration"] == 0
    assert ev.data["call_name"] == "Mum"
    assert ev.data["call_number"] == "+491234567"
    assert ev.data["call_time"] == 299


def test_call_outgoing_answered_not_missed() -> None:
    feed = _feed(_entry("c", "CALL_LOG", 300, call_type=1, duration=42))
    ev = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL).events[0]
    assert ev.data["direction"] == "outgoing"
    assert ev.data["missed"] is False


def test_call_missed_falls_back_to_duration_on_older_watch() -> None:
    # Older watch: no call_mode/call_mode_detail; duration==0 is the weaker missed heuristic.
    feed = _feed(_entry("c", "CALL_LOG", 300, call_type=2, duration=0))
    ev = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL).events[0]
    assert ev.data["missed"] is True


def test_sos_payload() -> None:
    feed = _feed(_entry("s", "SOS", 300, lat=52.5, lng=13.4, battery=15))
    ev = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL).events[0]
    assert ev.event_type == EVENT_SOS
    assert ev.data["lat"] == 52.5
    assert ev.data["lng"] == 13.4
    assert ev.data["battery"] == 15


def test_power_on_off_share_one_event_type_distinguished_by_state() -> None:
    feed = _feed(_entry("on", "POWER_ON", 210, battery=90), _entry("off", "POWER_OFF", 220, battery=88))
    events = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL).events
    by_id = {e.data["id"]: e for e in events}
    assert by_id["on"].event_type == EVENT_POWER and by_id["on"].data["state"] == "on"
    assert by_id["off"].event_type == EVENT_POWER and by_id["off"].data["state"] == "off"


def test_low_power_payload() -> None:
    feed = _feed(_entry("lp", "LOW_POWER", 300, battery=5))
    ev = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL).events[0]
    assert ev.event_type == EVENT_LOW_POWER
    assert ev.data["battery"] == 5


def test_overflow_flag_when_every_fetched_entry_is_new() -> None:
    feed = _feed(_entry("n1", "SOS", 300), _entry("n2", "SOS", 400))
    result = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL)
    assert result.saw_only_new is True
    # A fetch that still saw an old entry is not overflow.
    feed2 = _feed(_entry("old", "SOS", 100), _entry("new", "SOS", 300))
    assert plan_events(feed2, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL).saw_only_new is False


def test_entries_without_create_or_id_are_skipped() -> None:
    # One entry with a missing id, one with a null create -- both dropped, only "ok" survives.
    null_create = SimpleChat.from_dict({"id": "nc", "type": "SOS", "create": None, "sender": {"id": "w-uid"}, "data": {}})
    feed = [_entry("", "SOS", 300), null_create, _entry("ok", "SOS", 310)]
    result = plan_events(feed, mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL)
    assert [e.data["id"] for e in result.events] == ["ok"]


def test_same_second_new_sibling_fires_exactly_once() -> None:
    # a2 shares the mark's second (1000) but is not in its boundary-id set -> new, fires once. a1 is
    # already seen -> no refire. The mark accumulates both ids at that second.
    feed = _feed(_entry("a2", "SOS", 1000), _entry("a1", "SOS", 1000))
    result = plan_events(feed, mark=HighWater(create=1000, ids=frozenset({"a1"})), enabled=ALL)
    assert [e.data["id"] for e in result.events] == ["a2"]
    assert result.mark == HighWater(create=1000, ids=frozenset({"a1", "a2"}))


def test_same_second_reordered_feed_does_not_refire() -> None:
    # Both entries already seen at second 1000; a feed that returns them in either order must fire
    # nothing (order-independent dedupe -- no false re-fire, ADR 0015).
    mark = HighWater(create=1000, ids=frozenset({"a1", "a2"}))
    for order in ([_entry("a1", "SOS", 1000), _entry("a2", "SOS", 1000)], [_entry("a2", "SOS", 1000), _entry("a1", "SOS", 1000)]):
        result = plan_events(order, mark=mark, enabled=ALL)
        assert result.events == []
        assert result.mark == mark


def test_entry_with_no_sender_routes_to_empty_wuid() -> None:
    entry = SimpleChat.from_dict({"id": "s", "type": "SOS", "create": 300, "data": {}})
    result = plan_events([entry], mark=HighWater(create=200, ids=frozenset({"x"})), enabled=ALL)
    assert result.events[0].wuid == ""
