# FrameIT — Home Assistant Integration

Controls and monitors [FrameIT](https://github.com/your-repo/frameit) digital
photo-frame kiosks from Home Assistant.

## Server compatibility

This release targets the **hardened FrameIT server** — the one that protects
its admin API with CSRF tokens and throttles failed logins. Older servers are
still supported: entities that depend on fields those servers do not publish
are simply not created.

If you are running a FrameIT server from before that release, upgrade the
server first (see its `UPGRADING.md`). An integration older than 1.1.0 cannot
sign in to a hardened server at all.

## Features

Each registered FrameIT frame appears as a **device** in Home Assistant with
the following entities:

| Entity | Type | Description |
|--------|------|-------------|
| Display | Switch | Turn the monitor on/off via DPMS (requires agent) |
| Agent Service / UI Service | Switch | Restart a systemd unit on the Pi (requires agent) |
| Next | Button | Advance to the next poster or trailer |
| Refresh | Button | Reload the frame's browser |
| Reboot | Button | Reboot the Raspberry Pi (requires agent) |
| Content Mode | Select | Switch between `pool`, `pinned`, and `now-playing` |
| Rotation | Select | Display rotation in degrees |
| Display Interval | Number | Seconds each item is shown (10 – 86400) |
| Now Playing Source | Text | `media_player` entity to mirror artwork from |
| Agent | Update | Installed vs. available agent version (requires agent) |
| CPU / RAM / Disk | Sensor | Usage % (requires agent) |
| CPU Temperature | Sensor | CPU temp in °C (requires agent, Pi only) |
| IP Address | Sensor | The frame's address as the server sees it |
| Agent Credential | Sensor | `secret` or `legacy` — see below (requires agent) |

> **"Requires agent"** means the FrameIT agent must be installed and registered
> on the Raspberry Pi. Frames accessed only via the browser (no agent) still
> get Next, Refresh, and Content Mode.

A separate **FrameIT Server** device carries server-wide entities:

| Entity | Type | Description |
|--------|------|-------------|
| Frames / Online agents / Posters / Trailers | Sensor | Library and fleet counts |
| Trailers failed | Sensor | Downloads that exhausted their retries |
| Agents on legacy credentials | Sensor | Frames that would break under strict mode |
| Require agent authentication | Switch | Server's `strict_agent_auth` flag |
| Require frame tokens | Switch | Server's `strict_frame_auth` flag |
| Allow preview frames | Switch | Server's `allow_bypass_frames` flag |

## Now-playing mode

Mirrors a media player's artwork onto a frame — point it at an Apple TV and
the frame shows the poster of whatever is playing.

Two entities have to be set, and **both are required**:

1. **Now Playing Source** (text) — the entity ID of the player to follow,
   e.g. `media_player.living_room_apple_tv`.
2. **Content Mode** (select) — set to `now-playing`.

Setting only the content mode does nothing; the integration logs a warning
saying so. When it is working, each new title downloads that player's artwork,
uploads it to FrameIT as a poster, and pins it to the frame. The frame's
banner text becomes the media title and the app name. Switching Content Mode
back to `pool` or `pinned` removes the artwork and returns the frame to normal.

> **With more than one frame:** the artwork has to be marked active on the
> server to be displayable at all, and active posters are also pool
> candidates — so a *different* frame left in `pool` mode may occasionally
> show it too. Put every frame you don't want doing that into `pinned` mode,
> or into `now-playing` as well.

If nothing appears, check the Home Assistant log for `custom_components.frameit`
— every reason the push can bail out (no source, unknown entity, artwork
download failed, upload rejected) is logged there.

### Before turning strict mode on

**Require agent authentication** cuts off any agent still presenting the
one-time registration token instead of its own credential. Check
`sensor.frameit_server_agents_on_legacy_credentials` first — run *Agent Update*
on each frame the per-frame **Agent Credential** sensor reports as `legacy`,
and only flip the switch once the count is zero.

**Require frame tokens** blanks any display that has not reloaded since the
server upgrade. Press **Refresh** on every frame first.

## Installation

### Via HACS (recommended)

1. In HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add the URL of this repo, category **Integration**
3. Search for **FrameIT** and install
4. Restart Home Assistant

### Manual

Copy `custom_components/frameit/` into your
`<config>/custom_components/` directory, then restart Home Assistant.

## Configuration

1. **Settings → Devices & Services → Add Integration → FrameIT**
2. Enter your FrameIT server URL (e.g. `http://192.168.1.10:5000`)
3. Enter your FrameIT admin username and password

The integration signs in with the admin form and keeps the session alive
itself, re-authenticating whenever the server invalidates it. Changing the
admin password on the server signs every other session out, so Home Assistant
will raise a **Reconfigure** notification asking for the new one rather than
silently going stale.

Repeated failed sign-ins are throttled server-side. If the password in the
config entry is wrong, the integration backs off instead of spending the
allowance — so a fixed password may take a few minutes to take effect.

## Automations

Example: turn the living-room display off at midnight and back on at 8 am.

```yaml
automation:
  - alias: "FrameIT display off at midnight"
    trigger:
      platform: time
      at: "00:00:00"
    action:
      service: switch.turn_off
      target:
        entity_id: switch.living_room_display

  - alias: "FrameIT display on at 8am"
    trigger:
      platform: time
      at: "08:00:00"
    action:
      service: switch.turn_on
      target:
        entity_id: switch.living_room_display
```

Example: advance to the next poster when a movie night scene is activated.

```yaml
automation:
  - alias: "FrameIT next on movie night"
    trigger:
      platform: state
      entity_id: input_select.scene
      to: "Movie Night"
    action:
      service: button.press
      target:
        entity_id: button.living_room_next
```
