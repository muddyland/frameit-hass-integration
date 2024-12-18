from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from .const import DOMAIN

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the FrameIt Agent component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up FrameIt Agent from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Get the necessary info from config entry
    data = entry.data
    device_name = data["device_name"]
    ip = data["ip"]

    # Register the device in the Device Registry
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_name)},
        manufacturer="FrameIt",
        model="Smart Frame",
        name=device_name,
        sw_version="1.0",  # Adjust the software version appropriately
    )

    # Store device-specific data under its own entry_id
    hass.data[DOMAIN][entry.entry_id] = entry.data

    for component in ("sensor", "switch", "button"):
        hass.async_create_task(
            await hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "switch", "button"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok