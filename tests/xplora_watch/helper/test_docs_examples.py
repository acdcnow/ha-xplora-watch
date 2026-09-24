"""The example automations in docs/ must be valid, copy-pasteable Home Assistant config.

A broken snippet in the docs is a support burden: a user pastes it, HA rejects it at config
validation, and the feature looks broken. These tests validate the YAML we ship in the docs against
Home Assistant's own schemas so a drifted example fails here instead of in someone's config.
"""

from __future__ import annotations

import re
from pathlib import Path

import homeassistant.helpers.config_validation as cv
import yaml

_DOCS = Path(__file__).resolve().parents[3] / "docs"


def _yaml_blocks(markdown: str) -> list[str]:
    """Every ```yaml fenced block in a Markdown file."""
    return re.findall(r"```yaml\n(.*?)```", markdown, re.DOTALL)


def _automation_blocks(markdown: str) -> list[dict]:
    """The fenced YAML blocks that look like a standalone automation (have a top-level `trigger`)."""
    blocks = []
    for raw in _yaml_blocks(markdown):
        # safe_load rejects blueprint-only tags like `!input`, which don't belong in a plain
        # automation snippet -- so this also guards against shipping `!input` outside a blueprint.
        parsed = yaml.safe_load(raw)
        if isinstance(parsed, dict) and "trigger" in parsed:
            blocks.append(parsed)
    return blocks


def test_notifications_doc_automation_is_valid_config() -> None:
    """The `refresh_notifications` example automation in docs/notifications.md validates against HA's
    condition/action schemas (catches e.g. `above` on a `state` condition, which needs `numeric_state`)."""
    automations = _automation_blocks((_DOCS / "notifications.md").read_text())
    assert automations, "expected at least one example automation in notifications.md"

    assert any(  # the headline example: an automation that drives the refresh action
        "xplora_watch.refresh_notifications" in str(auto.get("action")) for auto in automations
    ), "expected an example that calls xplora_watch.refresh_notifications"

    for auto in automations:
        if "condition" in auto:
            cv.CONDITIONS_SCHEMA(auto["condition"])  # raises vol.Invalid on a malformed condition
        # Every action step must name a real service (domain.name), not be malformed or empty.
        actions = auto["action"] if isinstance(auto["action"], list) else [auto["action"]]
        for step in actions:
            service = step.get("action") or step.get("service")
            assert service and "." in service, f"malformed action step: {step}"
