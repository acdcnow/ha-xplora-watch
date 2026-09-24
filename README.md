# HA Xplora® Watch

A Home Assistant integration for Xplora® children's GPS watches — location, chat, alarms, safe
zones and more, built to keep your Xplora account **safe from rate-limit bans**.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=acdcnow&repository=ha-xplora-watch&category=integration)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge&logo=home-assistant)](https://hacs.xyz/docs/faq/custom_repositories/)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/acdcnow/ha-xplora-watch?style=for-the-badge&logo=github)](https://github.com/acdcnow/ha-xplora-watch/releases)
![GitHub Release Date](https://img.shields.io/github/release-date/acdcnow/ha-xplora-watch?style=for-the-badge&logo=github)
[![GitHub license](https://img.shields.io/github/license/acdcnow/ha-xplora-watch?style=for-the-badge&logo=github)](LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/acdcnow/ha-xplora-watch?style=for-the-badge&logo=github)](https://github.com/acdcnow/ha-xplora-watch/issues)\
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg?style=for-the-badge&logo=ruff)](https://github.com/astral-sh/ruff)\
[![Tests](https://github.com/acdcnow/ha-xplora-watch/actions/workflows/test.yml/badge.svg)](https://github.com/acdcnow/ha-xplora-watch/actions/workflows/test.yml)
[![Lint](https://github.com/acdcnow/ha-xplora-watch/actions/workflows/lint.yml/badge.svg)](https://github.com/acdcnow/ha-xplora-watch/actions/workflows/lint.yml)
[![Validate with hassfest and HACS](https://github.com/acdcnow/ha-xplora-watch/actions/workflows/validate.yml/badge.svg)](https://github.com/acdcnow/ha-xplora-watch/actions/workflows/validate.yml)
[![Coverage](https://raw.githubusercontent.com/acdcnow/ha-xplora-watch/main/.github/badges/coverage.svg)](https://github.com/acdcnow/ha-xplora-watch/actions/workflows/test.yml)

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-PayPal-blue.svg?style=for-the-badge&logo=paypal)](https://paypal.me/saninn)

> **Built to keep your account safe.** This is a fork of the excellent
> [Ludy87/xplora_watch](https://github.com/Ludy87/xplora_watch) — full credit to @Ludy87 for
> building the original and figuring out the Xplora API in the first place. This release line is
> itself a fork of [distante/ha-xplora-watch](https://github.com/distante/ha-xplora-watch), which
> carries that work forward — credit to @distante too. Over time Xplora
> tightened its rate-limits, and the talk-to-the-server-often patterns that used to be fine started
> getting accounts throttled and banned. This fork reworks how the integration talks to Xplora so
> that's no longer a risk: it **logs in once** and reuses that session for ~35 days,
> **consolidates** the per-refresh calls (and caches what doesn't change — locations, chat media),
> and ships with **polling off by default**, so out of the box it talks to Xplora's servers **only
> when you ask it to**. Safe by default, nothing to tune. Full details and numbers:
> [Why this fork exists](docs/ban-defense.md).

---

![HA Xplora® Watch](https://github.com/home-assistant/brands/blob/master/custom_integrations/xplora_watch/logo@2x.png?raw=true)

The bundled Lovelace overview card surfaces a watch's online/charging state, battery, last-known
location, steps, XCoins, unread messages, alarms, silent times and safe-zone status at a glance —
tap the location row for a live map, or the **Location history** row for a full day-by-day track:

<p>
  <img src="https://raw.githubusercontent.com/acdcnow/ha-xplora-watch/main/images/overview_card.png" alt="Overview card" height="420">
  <img src="https://raw.githubusercontent.com/acdcnow/ha-xplora-watch/main/images/full_map_location.png" alt="Map location popup" height="420">
</p>

More cards — chat, per-watch map, alarms & silent times — are covered in
[Dashboard cards](docs/dashboard-cards.md).

## What's new in 2.0.0

This release is about **not making you configure anything**: every useful entity is enabled out of
the box, the options dialog is grouped into seven described sections, and ready-made dashboards are
copied into your config for you.

- **Home Assistant 2026.9.3 is required** (which in turn needs Python 3.14). HACS enforces the
  minimum itself, so the update is simply not offered on an older core — update Home Assistant first.
- **Reconfigure instead of delete-and-re-add** when your password, e-mail or phone number changes:
  entities, recorded history and the stored location archive are all kept. A failed sign-in raises a
  **repair issue** pointing at the same dialog, and **Download diagnostics** gives you a redacted
  snapshot to attach to a bug report.
- [Call & notification activity](docs/notifications.md) — SOS, calls, power on/off and low-battery
  events from the account feed become Home Assistant events and logbook lines, plus a
  most-recent-call sensor. Opt-in per category (SOS on by default); the page explains the
  recorder/PII trade-off.
- [Ready-made dashboards](docs/dashboards.md) are copied to `/config/www/xplora_watch/dashboards` on
  setup — copy and paste, no template or manual sensors.
- **Fixed:** the Lovelace cards register as a real Lovelace resource now (a cold load used to lose
  them), a watch added to your account after setup shows up in the options picker, and a missing
  `home` zone no longer blocks the options dialog.

Breaking changes and upgrade steps are in the
[release notes](https://github.com/acdcnow/ha-xplora-watch/releases).

## Features

- Track your watch's live location and its [location history](docs/location-history.md)
- Chat with the watch and receive its messages, including voice/photo/video attachments
- Manage [alarms and silent times](docs/alarms-and-silent-times.md) from the UI, no phone needed
- [Safe-zone](docs/safe-zones.md) arrival/departure sensors
- [Call & notification activity](docs/notifications.md) — SOS, calls, power and low-battery events as
  Home Assistant events and logbook lines, plus a most-recent-call sensor
- Battery, charging, online state, steps, XCoins
- Reboot / shut down the watch remotely (Guardian accounts)
- A full [services API](docs/services.md) for automations, plus dependency-free
  [dashboard cards](docs/dashboard-cards.md) for everything above
- [Ready-made dashboards](docs/dashboards.md) to copy and paste — no manual/template sensors needed
- No real watch yet? Explore it risk-free in [demo mode](docs/demo-mode.md)

## Requirements

- Home Assistant **2026.9.3** or newer.
- Every watch comes out of the box with its useful entities already **enabled** — battery, steps,
  XCoins, unread messages, distance, safe zone, alarms, silent times, location history and the
  charging/online state. Nothing has to be switched on, and no sensor has to be built by hand.
- Two deliberate exceptions, both opt-in: the destructive **reboot/shutdown** buttons, and the two
  **notification-feed** extras (the most-recent-call sensor and the *Check notifications* button),
  which you switch on together with the notification categories in the options.

## Quickstart

1. Install via [HACS](https://hacs.xyz/): search for "**HA Xplora® Watch**" and add it.
2. Restart Home Assistant when prompted.
3. **Settings → Devices & Services → + Add Integration** → search "**HA Xplora® Watch**" → sign in.

That's it — polling is **off by default**, so nothing talks to Xplora's servers until you ask it
to (call `xplora_watch.see`, or turn on polling in the integration's **Configure** dialog). See
[Installation & configuration](docs/installation.md) for manual installs and every option, or
[Update interval (polling)](docs/polling.md) for how to drive refreshes safely.

Upgrading from the original `Ludy87/xplora_watch`? See
[Migrating from Ludy87/xplora_watch](docs/migrating-from-ludy87.md) — it installs in place, no
re-login needed.

Changed your Xplora® password, or moved the account to a new e-mail address or phone number? Use
**Settings → Devices & Services → HA Xplora® Watch → Reconfigure** — your entities, their recorded
history and the stored location archive are kept. If sign-in fails, the integration also raises a
**repair issue** pointing at that same shortcut, and **Download diagnostics** gives a redacted
snapshot to attach to a bug report.

## Documentation

The full manual lives in [`docs/`](docs/index.md):

| | |
| --- | --- |
| [Installation & configuration](docs/installation.md) | [Migrating from Ludy87/xplora_watch](docs/migrating-from-ludy87.md) |
| [Try it without a watch (demo mode)](docs/demo-mode.md) | [Account types: Guardian vs. Contact](docs/account-types.md) |
| [Update interval (polling)](docs/polling.md) | [Why this fork exists: the ban problem](docs/ban-defense.md) |
| [Alarms & silent times](docs/alarms-and-silent-times.md) | [Location history](docs/location-history.md) |
| [Safe zones](docs/safe-zones.md) | [Send a message](docs/send-message.md) |
| [Voice, video & image messages](docs/media.md) | [Dashboard cards](docs/dashboard-cards.md) |
| [Ready-made dashboards](docs/dashboards.md) | [Services reference](docs/services.md) |
| [Call & notification activity](docs/notifications.md) | [Troubleshooting](docs/troubleshooting.md) |
| [Diagnostics](docs/index.md#reference) |

## Getting help

Search [existing issues](https://github.com/acdcnow/ha-xplora-watch/issues) before opening a new
one, and use [Discussions](https://github.com/acdcnow/ha-xplora-watch/discussions) for questions
that aren't bug reports. See [Troubleshooting](docs/troubleshooting.md) for debug logging.

## License

[MIT](LICENSE). This project is a fork of [Ludy87/xplora_watch](https://github.com/Ludy87/xplora_watch);
see [Why this fork exists](docs/ban-defense.md) for what changed and why.
