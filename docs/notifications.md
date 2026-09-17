# Call & notification activity

The watch's account keeps a **notification feed** — the same list the phone app shows: calls, SOS
alarms, the watch powering on/off, and low-battery warnings. Home Assistant can surface each of
these as an **event** you can automate on, plus a **most-recent-call sensor** and a full-detail
**logbook** line per event.

> [!NOTE]
> These are **opt-in per category** and only fire **while polling is on** (polling is off by
> default — see [Update interval](polling.md)). Turning a category on adds **no** extra requests of
> its own; the feed rides the normal poll. Enable the categories you want under the integration's
> **Configure** dialog.

## What you get

- **Events** on the watch's device, one type per category:
  - `xplora_watch_call` — a call happened (incoming, outgoing or missed)
  - `xplora_watch_sos` — the watch sent an SOS
  - `xplora_watch_power` — the watch powered on or off
  - `xplora_watch_low_power` — the watch reported low battery
- **A most-recent-call sensor** (`sensor.<watch>_last_call`, disabled by default) whose state is the
  **time of the last call**. Contact name/number, direction, duration and the missed flag are
  attributes.
- **Logbook lines** — each event writes a readable line on the watch's device
  (e.g. *"Kid One Watch — missed incoming call from Mum"*).

There is **no live "ringing" state**: the feed is an after-the-fact log, so an event appears once the
call is over, not while the phone is ringing.

## Triggering a check (with polling off)

The feed is checked on every normal poll — but polling is **off by default**. To check it on demand
(and to drive it from your own automations) without turning polling on, use either:

- the **`xplora_watch.refresh_notifications`** action (target a watch to pick the account), or
- the per-watch **"Check notifications"** button (disabled by default — enable it on the device page).

Both do a single account-wide fetch and fire an event for anything new. Example automation — check
every 15 minutes only while someone's home:

```yaml
alias: Poll Xplora notifications while home
trigger:
  - platform: time_pattern
    minutes: "/15"
condition:
  # zone.home holds the number of people home; > 0 means someone's in.
  - condition: numeric_state
    entity_id: zone.home
    above: 0
action:
  - action: xplora_watch.refresh_notifications
    target:
      device_id: <your watch device>   # the "Watch(es)" field: pick the watch's device
```

This stays off Xplora's rate-limit radar: it only runs when you (or your automation) ask, and each
run is one request.

## Categories and defaults

| Category | Default | Event | Notes |
|---|---|---|---|
| SOS | **On** | `xplora_watch_sos` | The one safety-critical alert; on so you get it without hunting for a setting. |
| Calls | Off | `xplora_watch_call` | Incoming / outgoing / missed. Carries contact PII — see [Privacy](#privacy). |
| Power on/off | Off | `xplora_watch_power` | Low-stakes; opt in if you want it. |
| Low battery | Off | `xplora_watch_low_power` | The battery **level** is already a sensor; this marks the crossing. |

Enabling a category is **baseline-silent**: it starts firing for activity *from then on*, and does
not replay the backlog that happened before you turned it on (or before Home Assistant restarted).

## Event payloads (for automations)

`xplora_watch_call` carries `direction` (`incoming`/`outgoing`), `duration` (seconds), `missed`
(true/false), `call_name`, `call_number`, and the timestamps. Example — notify on a missed call:

```yaml
alias: Notify on a missed call
trigger:
  - platform: event
    event_type: xplora_watch_call
    event_data:
      missed: true
action:
  - service: notify.notify
    data:
      message: "Missed {{ trigger.event.data.direction }} call from {{ trigger.event.data.call_name }}"
```

`xplora_watch_sos` carries `lat`/`lng`/`battery`; `xplora_watch_power` carries `state`
(`on`/`off`); `xplora_watch_low_power` carries `battery`. Every event also carries the watch's
`device_id`, so you can trigger on the device directly.

> [!NOTE]
> `direction` is a best-effort reading of the call type and may be refined later; automate on it as a
> value, but don't hard-code a whole automation around telling incoming from outgoing yet.

## The most-recent-call sensor

`sensor.<watch>_last_call` is **disabled by default** — enable it on the watch's device page. Its
state is the timestamp of the most recent call (nothing else), so long-term history keeps only *when*
calls happened, never who they were with. The contact details live in the sensor's **attributes**,
which are deliberately kept out of the recorder database.

## Privacy

Enabling **Calls** or **SOS** writes personal data into Home Assistant's **recorder database**,
because the logbook line for each event is recorded — and those lines contain, by design:

- for a **call**: the contact's **phone number and name**;
- for an **SOS**: the watch's **GPS coordinates** at the time.

This is a deliberate trade for in-logbook visibility; it is **not a privacy guarantee**. If you would
rather not store contact numbers in your database, leave **Calls** off.
The most-recent-call sensor's *state* is only a timestamp and never records contact details, so it is
safe to keep even if you want PII out of long-term history. The options dialog restates this next to
each toggle.
