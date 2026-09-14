# Installation & configuration

## HACS (recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed.
2. In Home Assistant, go to **HACS → Integrations**, click the **+** button, and search for
   "**HA Xplora® Watch**".
3. Install it, then restart Home Assistant when prompted.
4. Go to **Settings → Devices & Services → + Add Integration**, search for "**HA Xplora® Watch**",
   and follow the config flow (see [Setup](#setup) below).

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=distante&repository=ha-xplora-watch&category=integration)

## Manual installation

Copy the `xplora_watch` folder from the [latest release](https://github.com/distante/ha-xplora-watch/releases)
into your Home Assistant's `custom_components` folder (usually inside your `/config` folder — on
Hass.io, copy it over SAMBA; on Home Assistant Supervised it may be at
`/usr/share/hassio/homeassistant`). Create the `custom_components` folder first if it doesn't
exist yet. Then restart Home Assistant and continue with [Setup](#setup) below.

## Setup

Configuration is done entirely through the UI config flow — there is no YAML configuration.

1. Go to **Settings → Devices & Services → + Add Integration**.
2. Search for "**HA Xplora® Watch**" and follow the prompts to sign in.
3. Once set up, the integration appears as a card on the Integrations page, with a **Configure**
   option at the bottom for the options covered in [Update interval (polling)](polling.md) and
   elsewhere in this manual.

Don't have a watch handy? See [Try it without a watch (demo mode)](demo-mode.md).

## Adding a watch later

You choose which watches the integration tracks during setup, and that selection is stored with
the integration. A watch you add to your Xplora® account afterwards is **not** picked up
automatically — no new entities appear on their own.

To start tracking a newly added watch:

1. Go to **Settings → Devices & Services**, find the **HA Xplora® Watch** card, and click
   **Configure**.
2. In the **Watches** list, tick the new watch (your existing selections stay checked) and submit.

The list refreshes from your account each time you open **Configure**, so a watch added since setup
appears there without restarting Home Assistant. Its entities are created after you submit.
