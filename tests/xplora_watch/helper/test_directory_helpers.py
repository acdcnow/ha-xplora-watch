"""Tests for helper.create_www_directory."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.xplora_watch.const import DOMAIN
from custom_components.xplora_watch.helper import async_copy_dashboard_templates, create_www_directory


async def test_create_www_directory_creates_all_expected_paths(hass: HomeAssistant) -> None:
    """All 6 expected www subdirectories are created."""
    await create_www_directory(hass)

    expected_paths = [
        hass.config.path("www"),
        hass.config.path("www/image"),
        hass.config.path("www/video"),
        hass.config.path("www/video/thumb"),
        hass.config.path("www/voice"),
        hass.config.path(f"www/{DOMAIN}"),
    ]
    for path in expected_paths:
        assert os.path.exists(path), f"expected {path} to exist"


async def test_create_www_directory_is_idempotent(hass: HomeAssistant) -> None:
    """Calling create_www_directory twice does not raise."""
    await create_www_directory(hass)
    await create_www_directory(hass)

    assert os.path.exists(hass.config.path(f"www/{DOMAIN}"))


async def test_create_www_directory_registers_local_media_paths(hass: HomeAssistant) -> None:
    """The media dirs are exposed under `/local/*` by the integration itself.

    Home Assistant only wires up `/local` at startup when `config/www` already exists, but these
    dirs are created here (post-startup) -- so on a fresh install the integration must register the
    media sub-paths or cached voice/image/video would 404 until a restart. Registration is one-time
    across entries.
    """
    fake_http = MagicMock()
    fake_http.async_register_static_paths = AsyncMock()

    with patch.object(hass, "http", fake_http, create=True):
        await create_www_directory(hass)
        await create_www_directory(hass)  # idempotent: must not register a second time

    fake_http.async_register_static_paths.assert_awaited_once()
    configs = fake_http.async_register_static_paths.await_args.args[0]
    assert {c.url_path for c in configs} == {"/local/image", "/local/video", "/local/voice"}


async def test_copy_dashboard_templates_copies_the_bundled_files(hass: HomeAssistant) -> None:
    """The dashboard templates ship inside the package and are copied into the user's config dir.

    HACS installs only `custom_components/<domain>`, so without this copy a HACS user would have to
    browse GitHub to copy a dashboard template.
    """
    await async_copy_dashboard_templates(hass)

    target = hass.config.path(f"www/{DOMAIN}/dashboards")
    assert os.path.exists(os.path.join(target, "xplora-watch-dashboard.yaml"))
    assert os.path.exists(os.path.join(target, "family-overview.yaml"))
    assert os.path.exists(os.path.join(target, "watch-controls.yaml"))


async def test_copy_dashboard_templates_never_overwrites_an_existing_file(hass: HomeAssistant) -> None:
    """A user's edited template survives an update -- existing files are left untouched."""
    target = hass.config.path(f"www/{DOMAIN}/dashboards")
    os.makedirs(target, exist_ok=True)
    edited = os.path.join(target, "family-overview.yaml")
    with open(edited, "w", encoding="utf-8") as handle:
        handle.write("my own dashboard\n")

    await async_copy_dashboard_templates(hass)

    with open(edited, encoding="utf-8") as handle:
        assert handle.read() == "my own dashboard\n"
