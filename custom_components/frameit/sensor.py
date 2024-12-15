from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import requests
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Setup sensors for each FrameIt device."""
    data = config_entry.data
    device_name = data["device_name"]
    ip = data["ip"]
    api_key = data["api_key"]
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }

    entities = [
        FrameItSensor(f"{device_name} Status", f"http://{ip}/status", headers),
        # Add more sensors as needed
    ]
    async_add_entities(entities, True)

class FrameItSensor(Entity):
    def __init__(self, name, resource, headers):
        self._name = name
        self._resource = resource
        self._state = None
        self._headers = headers

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    async def async_update(self):
        try:
            response = requests.get(self._resource, headers=self._headers, timeout=10)
            data = response.json()
            self._state = data.get('status')
        except Exception as e:
            _LOGGER.error(f"Error updating {self.name}: {e}")