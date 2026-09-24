"""Client-layer tests for the account notification feed (`notifications` query).

Covers issue #12 call activity (ref:XW-020): the query document's wire shape, the CALL_LOG
`data` fields on the `Data` model, and the read-only `notifications_a` handler. The sibling
`setReadAllNotifications` mutation must never be implemented (ADR 0015) -- it would clear the
guardian's account-wide unread state as a polling side effect.
"""

from __future__ import annotations

from typing import Any

import pytest

import custom_components.xplora_watch.pyxplora_api.gql_mutations as gql_mutations
import custom_components.xplora_watch.pyxplora_api.gql_queries as gql_queries
from custom_components.xplora_watch.pyxplora_api.const import GqlOperation
from custom_components.xplora_watch.pyxplora_api.gql_handler_async import GQLHandler
from custom_components.xplora_watch.pyxplora_api.gql_queries import WATCH_Q
from custom_components.xplora_watch.pyxplora_api.model import Data, Notifications

# The wire document, byte-identical to the reference client (ref:XW-020, ADR 0011). Nullable
# `$uid` (the account-wide fetch passes uid=""), argument order uid, msgId, offset, limit, a
# lean `SimpleChatFragment` (no per-field __typename; sender/receiver select only id).
_REFERENCE_WIRE = (
    "query notifications($uid: String, $msgId: String, $offset: Int, $limit: Int) "
    "{ notifications(uid: $uid, msgId: $msgId, offset: $offset, limit: $limit) "
    "{ msgId offset limit list { __typename ...SimpleChatFragment } } }\n"
    "fragment SimpleChatFragment on SimpleChat "
    "{ id msgId readFlag type sender { id } receiver { id } data create }"
)


def _handler() -> GQLHandler:
    return GQLHandler("49", "1234567", "pw", "en", "Europe/Berlin", email="a@b.c", signup=False)


def test_notifications_query_matches_reference_wire_shape() -> None:
    assert WATCH_Q["notificationsQ"] == _REFERENCE_WIRE


def test_notifications_operation_name_is_lowercase_initial() -> None:
    # Operation name goes on the wire; keep it lowercase-initial verbatim (ref:XW-020, ADR 0011).
    # Assert against the actual query document, not the enum literal, so a divergence is caught.
    assert GqlOperation.NOTIFICATIONS == "notifications"
    assert "query notifications(" in WATCH_Q["notificationsQ"]
    assert "query Notifications(" not in WATCH_Q["notificationsQ"]


def test_data_carries_call_log_fields() -> None:
    d = Data.from_dict(
        {
            "call_type": 2,
            "duration": 0,
            "call_name": "Mum",
            "call_number": "+491234567",
            "call_time": 1700000000,
            "call_mode": 2,
            "call_mode_detail": 50,
            "voip": 2,
        }
    )
    assert d.call_number == "+491234567"
    assert d.duration == 0
    assert d.call_mode == 2
    assert d.call_mode_detail == 50
    assert d.voip == 2


async def test_notifications_a_sends_read_only_account_wide_query(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _handler()
    captured: dict[str, Any] = {}

    async def _fake(query: str, variables: dict[str, Any] | None = None, operation_name: str | None = None) -> dict[str, Any]:
        captured["query"] = query
        captured["variables"] = variables
        captured["op"] = operation_name
        return {"data": {"notifications": {"list": []}}}

    monkeypatch.setattr(handler, "runAuthorizedGqlQuery_a", _fake)
    res = await handler.notifications_a(uid="", offset=0, limit=20)

    assert captured["op"] == "notifications"
    assert captured["variables"] == {"uid": "", "msgId": "", "offset": 0, "limit": 20}
    assert captured["query"] == WATCH_Q["notificationsQ"]
    assert res == {"notifications": {"list": []}}


async def test_notifications_a_asobject_parses_feed_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _handler()

    async def _fake(query: str, variables: dict[str, Any] | None = None, operation_name: str | None = None) -> dict[str, Any]:
        return {
            "data": {
                "notifications": {
                    "msgId": "",
                    "offset": 0,
                    "limit": 20,
                    "list": [
                        {
                            "id": "n1",
                            "type": "CALL_LOG",
                            "create": 1700000000,
                            "sender": {"id": "w-uid"},
                            "receiver": {"id": "guardian"},
                            "data": {"call_type": 2, "duration": 0, "call_number": "+491234567"},
                        }
                    ],
                }
            }
        }

    monkeypatch.setattr(handler, "runAuthorizedGqlQuery_a", _fake)
    parsed = await handler.notifications_a(uid="", asObject=True)

    assert isinstance(parsed, Notifications)
    assert parsed.notifications is not None
    entry = parsed.notifications.list[0]
    assert entry.id == "n1"
    assert entry.type == "CALL_LOG"
    assert entry.sender is not None and entry.sender.id == "w-uid"
    assert entry.data is not None
    assert entry.data.call_number == "+491234567"
    assert entry.data.duration == 0


def test_setreadallnotifications_is_never_implemented() -> None:
    # ADR 0015: read-only polling only -- the mark-all-read mutation must not exist in the client,
    # in any query/mutation dict document or as a handler method.
    docs: list[str] = []
    for module in (gql_queries, gql_mutations):
        for attr in vars(module).values():
            if isinstance(attr, dict):
                docs.extend(value for value in attr.values() if isinstance(value, str))
    assert "setReadAllNotifications" not in "".join(docs)
    assert not any(name.lower().startswith("setreadall") for name in dir(GQLHandler))
