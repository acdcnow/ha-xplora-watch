# Ready-made dashboards

Four dashboards you can copy and paste straight into Home Assistant. They use only the bundled
cards and this integration's own entities — **no manual/template sensors and no helper entities are
needed**, and you never have to add a Lovelace resource (the cards register themselves).

They ship inside the integration and are copied to `/config/www/xplora_watch/dashboards/` on setup,
so they are reachable from the File Editor, a Samba share or the Studio Code Server add-on. Full
instructions, placeholders and customization options: `docs/dashboards.md` in the repository.

| File | What it is |
| ---- | ---------- |
| [xplora-watch-dashboard.yaml](xplora-watch-dashboard.yaml) | A **complete dashboard** for one child: overview, map, alarms & silent times, chat. |
| [family-overview.yaml](family-overview.yaml) | **One view** with a card per child — for families with several watches. |
| [watch-controls.yaml](watch-controls.yaml) | **One view** of the action buttons and status sensors for a watch. |

## How to paste a dashboard

1. **Settings → Dashboards → + Add dashboard** (title it e.g. *Xplora*), open it, then
   **⋮ → Edit dashboard → ⋮ → Raw configuration editor**.
2. Replace everything with the contents of the YAML file.
3. Replace the placeholders (see below) and **Save**.

For a single *view* (the last two files) instead: open any dashboard, **Edit dashboard → + Add view
→ scroll to the bottom → paste the YAML**, and drop the leading `views:` wrapper if the file has
one — the files say so where it matters.

## The placeholders you have to replace

Everything you need is already in Home Assistant; you do not have to invent an entity.

### `DEVICE_ID` — the watch's device id

Two ways to get it:

* **My favourite:** open **Settings → Devices & Services → Devices**, click the child's watch
  (*“Dana Watch (Mom)”*), and copy the id from the browser address bar — it is the last part of
  `.../config/devices/device/<DEVICE_ID>`.
* **Developer Tools → Template**, paste this and read the output:

  ```jinja
  {% for e in states.sensor if e.entity_id.endswith('_last_update') %}
  {{ e.name }} -> {{ device_id(e.entity_id) }}
  {% endfor %}
  ```

Only the **overview card** and the **map card** need this. Because every entity of the watch carries
the integration's role attribute, those two cards find all the other entities (battery, steps,
online state, safe zone, unread messages, alarms, chat, history) **by themselves** — one id, whole
watch.

### Entity ids for the alarms, chat and controls cards

Those three cards render one specific data set, so they take the matching sensor/button. Find the
ids on the watch's device page (**Settings → Devices & Services → Devices → the watch**): each row
there is an entity, and the id is shown after the name. The ids are predictable, too:

```
sensor.xplora_<child>_watch_alarms_<account>      # alarms card
sensor.xplora_<child>_watch_silents_<account>     # silent-times card
sensor.xplora_<child>_watch_message_<account>     # chat card
button.xplora_<child>_watch_update_<account>      # controls card (add _reboot / _shutdown as wanted)
```

`<child>` is the child's name and `<account>` the account alias (e.g. `mom`) you chose during setup
— both slugified. Nothing here needs a service call or a helper entity.

> [!TIP]
> You can skip the alarms/chat/controls cards completely: the **overview card already opens all of
> them**. Tapping the *Location* row opens the live map, *Location history* opens the day-by-day
> track, *Alarms*/*Silent times*/*Unread* open the matching editor, and the ⚙ button opens the
> controls. The separate cards exist for people who want two of them side by side.

## Why the entities are already there

Every watch gets its useful entities **enabled out of the box** — battery, steps, XCoins, unread
messages, distance, safe zone, alarms, silent times, location history, charging/online state and the
two safe action buttons. Nothing has to be switched on first, and no sensor has to be created by
hand. If you want to hide something, disable or delete that entity in the normal Home Assistant way
(**Settings → Devices & Services → Entities**) — the dashboards simply omit what is missing.

The two destructive buttons (*Restart watch*, *Shut down watch*) stay **disabled** on purpose, so a
stray tap can't power off a child's watch. Enable them if you want them on the controls card.
