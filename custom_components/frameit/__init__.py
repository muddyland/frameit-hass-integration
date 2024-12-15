from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Movie Poster component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Movie Poster from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN] = entry.data

    # Update to async_forward_entry_setups with a list of platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "switch", "button"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "switch", "button"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok