from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN
import requests
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up sensors for each FrameIt device."""
    data = config_entry.data
    device_name = data["device_name"]
    ip = data["ip"]
    api_key = data["api_key"]

    entities = [
        FrameItSensor(device_name, f"http://{ip}/status", api_key, config_entry.entry_id)
        # Add more sensors as needed
    ]

    async_add_entities(entities, True)

class FrameItSensor(Entity):
    def __init__(self, name, resource, api_key, config_entry_id):
        self._name = name
        self._resource = resource
        self._api_key = api_key
        self._state = None
        self._config_entry_id = config_entry_id

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def device_info(self):
        """Return device information for the sensor."""
        return {
            "identifiers": {(DOMAIN, self._resource)},
            "name": self._name,
            "manufacturer": "FrameIt Manufacturer",
            "model": "Smart Frame",
            "via_device": (DOMAIN, self._resource)
        }

    async def async_update(self):
        headers = {
            'X-API-Key': self._api_key,
            'Content-Type': 'application/json'
        }
        try:
            response = requests.get(self._resource, headers=headers, timeout=10)
            data = response.json()
            self._state = data.get('status')
        except Exception as e:
            _LOGGER.error(f"Error updating {self.name}: {e}")