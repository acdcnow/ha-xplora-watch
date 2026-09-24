# Ready-made dashboards

Copy, paste, done. This page collects the ready-to-use Lovelace dashboards that ship **inside the
integration** at
[`custom_components/xplora_watch/dashboards/`](../custom_components/xplora_watch/dashboards). They
are built only from this integration's own entities and the cards it bundles — **no manual or
template sensors, no helper entities, and no Lovelace resource to add** (the bundled cards register
themselves).

On setup the integration also copies them into your own config folder, so you do not have to browse
GitHub to copy one:

```
/config/www/xplora_watch/dashboards/
```

Open that path with the File Editor, Samba or Studio Code Server add-on. Existing files are never
overwritten, so your own edits survive an update — the copy in the integration package (or on
GitHub) is always the latest.

| File | What you get |
| ---- | ------------ |
| [`xplora-watch-dashboard.yaml`](../custom_components/xplora_watch/dashboards/xplora-watch-dashboard.yaml) | A complete dashboard for one child: **Overview**, **Map**, **Alarms & silence**, **Chat**, **Controls**. |
| [`family-overview.yaml`](../custom_components/xplora_watch/dashboards/family-overview.yaml) | One view with a card per child, in a grid — for several watches. |
| [`watch-controls.yaml`](../custom_components/xplora_watch/dashboards/watch-controls.yaml) | One view with the action buttons and status entities. |

## Pasting one

1. **Settings → Dashboards → + Add dashboard**, open it.
2. **Edit dashboard** → **⋮** → **Raw configuration editor**.
3. Replace everything with the file's contents, fill in the placeholders, **Save**.

Single views work the same way: **Edit dashboard → + Add view**, then paste without the leading
`title:`/`views:` wrapper.

## What you have to fill in

Only one value is really needed per watch: the **device id**.

```
Settings → Devices & Services → Devices → the child's watch
→ the device id is the last part of the browser URL: /config/devices/device/<DEVICE_ID>
```

The **overview card** and the **map card** take `device:` and then look up every other entity of
that watch themselves: every entity this integration creates carries a role attribute, so the cards
find battery, charging/online state, position, steps, XCoins, unread messages, alarms, silent times,
safe-zone state and the location history **without you naming a single entity**.

The remaining cards (alarms, silent times, chat, action buttons) each render one specific data set,
so they take that entity's id instead — copy it from the watch's device page, or read it off the
naming scheme:

```
sensor.xplora_<child>_watch_alarms_<account>     # alarms
sensor.xplora_<child>_watch_silents_<account>    # silent times
sensor.xplora_<child>_watch_message_<account>    # chat
button.xplora_<child>_watch_update_<account>     # controls
```

`<child>` is the child's name and `<account>` the account alias you chose during setup (e.g. `mom`),
both slugified.

> [!TIP]
> You can leave the alarms/chat/controls cards out entirely. The **overview card opens all of them
> as pop-ups**: tap *Location* for the live map, *Location history* for the day-by-day track,
> *Alarms* / *Silent times* / *Unread* for the matching editor, and the ⚙ button for the controls.

## Customizing

Everything is ordinary Lovelace YAML, so customize freely. The cards' own options:

**Overview card** (`custom:xplora-watch-overview-card`)

| Option | Default | Meaning |
| ------ | ------- | ------- |
| `device` / `entity` | — | Watch device id, or any one of its entities (one is required) |
| `title` | the watch's name | Heading override |
| `show_history` | `true` | Show the *Location history* row |
| `history_max_points` | `500` | Cap on plotted points per history fetch |
| `history_zoom` | `15` | Max auto-fit zoom for a day's map track |

**Map card** (`custom:xplora-watch-map-card`)

| Option | Default | Meaning |
| ------ | ------- | ------- |
| `device` / `entity` | — | Watch device id, or any one of its entities |
| `title` | the watch's name | Heading override |
| `aspect_ratio` | `16:9` | Map aspect ratio |
| `show_header` | `true` | Set `false` for a bare map |

**Alarms / silent times card** (`custom:xplora-watch-card`): `entity` (the `*_alarms` or
`*_silents` sensor), `title`. Rows have enable toggles, edit/delete, an **Add** form and
copy-to-clipboard actions — see [Dashboard cards](dashboard-cards.md).

**Chat card** (`custom:xplora-watch-chat-card`): `entity` (the `*_message` sensor), `title`,
`debug`.

**Controls card** (`custom:xplora-watch-actions-card`): `entities` (a list of the watch's
`button.*` entities, or a single `entity`).

## Which entities exist out of the box

Every watch is created with its useful entities **already enabled**, so a fresh dashboard lights up
immediately:

| Entity | What it shows |
| ------ | ------------- |
| `sensor.…_battery` | Battery percentage |
| `sensor.…_step_day` | Steps today |
| `sensor.…_xcoin` | XCoins |
| `sensor.…_message` | Unread messages (the chat card's sensor) |
| `sensor.…_distance` | Distance from home, in metres |
| `sensor.…_current_safezone` | Name of the safe zone the watch is inside |
| `sensor.…_last_update` | `ok` / `no_response` / `error` for the last refresh |
| `sensor.…_alarms` / `…_silents` | Alarm and silent-time entries (state = count, list in attributes) |
| `sensor.…_location_history` | Points in the recent window (full archive in the pop-up) |
| `binary_sensor.…_charging` / `…_state` / `…_safezone` | Charging, online, outside-safe-zone |
| `button.…_update` / `…_refresh_functions` | Refresh location / re-read alarms & silent times |
| `button.…_reboot` / `…_shutdown` | Watch control — **disabled by default** so a stray tap can't power off the watch |
| `device_tracker.…_tracker` | The watch's live position |

Hide anything you don't want in **Settings → Devices & Services → Entities**; the dashboards simply
omit what is missing.
