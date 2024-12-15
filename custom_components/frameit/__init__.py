from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up FrameIt Agent component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up FrameIt Agent from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Store device-specific data under its own entry_id
    hass.data[DOMAIN][entry.entry_id] = entry.data

    for component in ("sensor", "switch", "button"):
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "switch", "button"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok