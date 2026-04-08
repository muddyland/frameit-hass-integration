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
| CPU | Sensor | CPU usage % (requires agent) |
| RAM | Sensor | RAM usage % (requires agent) |
| Disk | Sensor | Disk usage % (requires agent) |
| CPU Temperature | Sensor | CPU temp in °C (requires agent, Pi only) |

> **"Requires agent"** means the FrameIT agent must be installed and registered
> on the Raspberry Pi. Frames accessed only via the browser (no agent) still
> get Next, Refresh, and Content Mode.

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
