# Update interval (polling)

Polling is the integration's only standing source of rate-limit/ban risk, so it is **off by
default** (no recurring cloud calls). The update interval is chosen from a small set of safe
presets: **Off / Every 30 minutes / Every hour / Every 2 hours** (in the integration's
_Options_).

With polling **Off**, data refreshes only when you call the `xplora_watch.see` service. For
faster or conditional updates, create your own automation that calls `xplora_watch.see` on
whatever schedule/trigger you want (and accept the corresponding ban risk):

```yaml
# Example: refresh every 10 minutes only while someone is home
automation:
  - alias: Xplora refresh
    trigger:
      - platform: time_pattern
        minutes: "/10"
    condition:
      - condition: state
        entity_id: zone.home
        state: "1"   # at least one person home
    action:
      - action: xplora_watch.see
        data:
          device_id: <your watch device>   # the "Watch(es)" field: pick one or more "Dana Watch (Mom)" devices
```

Existing installs are migrated automatically: a previously configured interval is snapped to
the nearest preset the next time you open _Options_ (anything faster than 30 minutes becomes
30 minutes).

## Live follow (temporary fast polling)

Sometimes "every 30 minutes" is simply not what you need — you want to watch a walk home. **Live
follow** is the one deliberate exception to the "never poll fast" rule, and it is bounded on
purpose:

- **Start** it from the watch's **Live follow** switch (enabled out of the box) or with the
  `xplora_watch.follow` service, which takes an optional `duration` in minutes.
- While a session runs, that watch is refreshed **every 30 seconds** — the same request the Life
  app sends while its map is open, so 15 minutes of following is 30 refreshes.
- It **always ends by itself**: the default is **15 minutes** and the maximum is **60**. Stop it
  early with the switch or with `xplora_watch.stop_follow`; the watch then returns to the interval
  from _Options_ (by default: no polling at all).
- If Xplora answers with a rate limit (HTTP 429) during a session, the session is **aborted
  immediately** — the integration never retries into a ban.
- Sessions are never stacked (starting one again just moves its end time) and nothing is persisted:
  a Home Assistant restart ends every session.

The switch carries the countdown (`remaining`, `ends_at`, `interval`), so a dashboard can show it:

```yaml
type: entities
title: Live follow
entities:
  - entity: switch.xplora_dana_watch_live_follow_mom
```

Only a **Guardian** can trigger a fresh location fix, so the switch and both services are
Guardian-only, like the other watch controls (see [Account types](account-types.md)).

## Alarms / silent times / safe zones interval

Alarms, silent-time windows and safe-zone definitions can't be bundled into the main status
fetch (Xplora serves each from its own per-watch request), but they rarely change — so they have
their **own** interval in _Options_, **"Alarms/silent/safe-zone refresh"**:
**Off (manual only) / Every 6 hours / Daily / With every poll**, defaulting to **Off**.

- With it **Off**, this data is fetched once and then reused, so normal polls stay lean. Refresh
  it on demand by calling the `xplora_watch.refresh_functions` service, or simply by **tapping the
  alarms/silent count on the overview card** (which opens the management list and refreshes it).
- The alarm/silent edit services (create/update/delete/enable) always refresh their own list
  immediately, so changes you make show up regardless of this setting.

## Auto-mark messages as read

A separate _Options_ toggle, **"Mark chat messages as read while polling"** (default **off**),
controls whether fetched chat messages are marked read on Xplora's servers. Leaving it off
preserves the unread-message count and avoids extra write traffic.
