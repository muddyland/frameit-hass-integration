# FrameIT — Home Assistant Integration

Controls and monitors [FrameIT](https://github.com/your-repo/frameit) digital
photo-frame kiosks from Home Assistant.

## Features

Each registered FrameIT frame appears as a **device** in Home Assistant with
the following entities:

| Entity | Type | Description |
|--------|------|-------------|
| Display | Switch | Turn the monitor on/off via DPMS (requires agent) |
| Next | Button | Advance to the next poster or trailer |
| Refresh | Button | Reload the frame's browser |
| Reboot | Button | Reboot the Raspberry Pi (requires agent) |
| Content Mode | Select | Switch between `pool` and `pinned` mode |
| Now Playing | Switch | Show what the now-playing source is playing on this frame |
| CPU | Sensor | CPU usage % (requires agent) |
| RAM | Sensor | RAM usage % (requires agent) |
| Disk | Sensor | Disk usage % (requires agent) |
| CPU Temperature | Sensor | CPU temp in °C (requires agent, Pi only) |

> **"Requires agent"** means the FrameIT agent must be installed and registered
> on the Raspberry Pi. Frames accessed only via the browser (no agent) still
> get Next, Refresh, Content Mode, and Now Playing.

## Now playing

The integration can mirror what a media player is playing onto your frames:
Home Assistant posts the state, the artwork and two lines of caption to the
FrameIT server, and the server shows it on every frame whose **Now Playing**
switch is on. One source player feeds all of them.

Films and television are the main case; music works too.

| Playing | Top banner | Bottom banner |
|---------|------------|---------------|
| A television episode | The **series** name | The app it is streaming from |
| A film | The film title | The app it is streaming from |
| A track | The track title | The artist, or the album |
| Anything else | Whatever title the player reports | *(blank)* |

Episode numbers are deliberately left off: a frame showing *Breaking Bad*
right through a run of episodes reads better than one that changes to
*S05E14* every forty minutes. The bottom banner is blank when the player does
not report an `app_name`, which is common for local libraries.

Which line you get depends on what your player actually publishes, and players
vary a lot. A series name is used whenever `media_series_title` is set. Some
streaming apps — Netflix through an Apple TV, for instance — publish only a
plain title with no series fields at all; that title is then shown as-is
rather than being taken apart to guess a series name out of it.

To set it up:

1. On the FrameIT server, **Settings → Now Playing**, or via the integration:
   **Settings → Devices & Services → FrameIT → Configure**, tick
   **Generate a new token** and submit. The token is stored in the config
   entry — the server shows it only once, so generating a new one invalidates
   whatever was in use before.
2. In the same options dialog, choose the **Media player** to mirror.
3. Turn on the **Now Playing** switch for each frame that should show it.

Leaving the media player blank turns reporting off.

Two details worth knowing:

- Nothing is re-sent for a position tick — only an actual state or metadata
  change posts, so playing something does not hammer the server. A new episode
  of the same series does count as a change, even though the banners read the
  same, because the artwork behind them is different.
- While something is playing the integration re-posts on a heartbeat at half
  the server's `now_playing_stale_seconds` (120 s by default, so every 60 s).
  The server treats art older than that window as cleared, which is what makes
  a frame fall back to its normal rotation when Home Assistant stops reporting.

## Upgrading from 1.x

Version 2.0.0 is a breaking change. In 1.x the integration faked now-playing by
uploading album art as a poster and pinning it to a frame. The server now owns
this properly, so:

- The **now-playing** option is gone from the Content Mode select. Content
  Mode is `pool` or `pinned`, matching the server. Any automation selecting
  `now-playing` needs updating to the Now Playing switch instead.
- The per-frame **Now Playing Source** text entities are gone. The source is
  now one media player set in the integration options, and the token is stored
  there too rather than in an entity anyone can read off a dashboard.
- On first start, the posters 1.x left behind in your library are deleted
  automatically.

## Installation

### Via HACS (recommended)

1. In HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add the URL of this repo, category **Integration**
3. Search for **FrameIT** and install
4. Restart Home Assistant

### Manual

Copy `custom_components/frameit/` into your
`<config>/custom_components/` directory, then restart Home Assistant.

## Running the tests

The test suite runs on **Python 3.14 or newer** — `requirements_test.txt` pins
`pytest-homeassistant-custom-component`, which requires it and pulls in the
matching Home Assistant release. Install it, then run `pytest tests/`.

## Configuration

1. **Settings → Devices & Services → Add Integration → FrameIT**
2. Enter your FrameIT server URL (e.g. `http://192.168.1.10:5000`)
3. Enter your FrameIT admin username and password

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
