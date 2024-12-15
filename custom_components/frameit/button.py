from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up buttons for each FrameIt device."""
    data = config_entry.data
    device_name = data["device_name"]
    ip = data["ip"]
    api_key = data["api_key"]
    
    entities = [
        FrameItButton(device_name + " Reboot", f"http://{ip}:5000/system/reboot", api_key)
        # Add more buttons if needed
    ]

    async_add_entities(entities, True)

class FrameItButton(ButtonEntity):
    def __init__(self, name, resource, api_key):
        self._name = name
        self._resource = resource
        self._api_key = api_key

    @property
    def name(self):
        return self._name

    @property
    def device_info(self):
        """Return device information for the button."""
        return {
            "identifiers": {(DOMAIN, self._name)},
            "name": self._name,
            "manufacturer": "FrameIt Manufacturer",
            "model": "Smart Frame",
            "via_device": (DOMAIN, self._resource)
        }

    async def async_press(self):
        """Handle the button press."""
        headers = {
            'X-API-Key': self._api_key,
            'Content-Type': 'application/json'
        }

        try:
            async with async_get_clientsession(self.hass).post(
                self._resource, headers=headers
            ) as response:
                response.raise_for_status()
        except Exception as e:
            _LOGGER.error(f"Error occurred while pressing {self.name}: {e}")