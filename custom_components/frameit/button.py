from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import requests
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
        FrameItButton(device_name, f"http://{ip}/system/reboot", api_key, config_entry.entry_id)
        # Add more buttons if needed
    ]

    async_add_entities(entities, True)

class FrameItButton(ButtonEntity):
    def __init__(self, name, resource, api_key, config_entry_id):
        self._name = name
        self._resource = resource
        self._api_key = api_key
        self._config_entry_id = config_entry_id

    @property
    def name(self):
        return self._name

    @property
    def device_info(self):
        """Return device information for the button."""
        return {
            "identifiers": {(DOMAIN, self._resource)},
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
            response = requests.post(self._resource, headers=headers, timeout=10)
            response.raise_for_status()  # Raise an error for unsuccessful HTTP requests
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Failed to send command for {self.name}: {e}")