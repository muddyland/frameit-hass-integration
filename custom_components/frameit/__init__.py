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

    async def async_add_frameit_device(call):
        name = call.data.get("name")
        ip = call.data.get("ip")
        api_key = call.data.get("api_key")

        hass.data[DOMAIN][name] = {
            "ip": ip,
            "api_key": api_key
        }

        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, ip)},
            name=name,
            manufacturer="FrameIt",
            model="FrameIt Smart Frame",
        )

        await hass.config_entries.async_forward_entry_setup(entry, "sensor")
        await hass.config_entries.async_forward_entry_setup(entry, "switch")
        await hass.config_entries.async_forward_entry_setup(entry, "button")

    hass.services.async_register(DOMAIN, "add_device", async_add_frameit_device)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "switch", "button"])
    if unload_ok:
        hass.data[DOMAIN].clear()

    return unload_ok