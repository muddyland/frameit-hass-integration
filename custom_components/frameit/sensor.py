from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up sensors for each FrameIt device."""
    data = config_entry.data
    device_name = data["device_name"]
    ip = data["ip"]
    api_key = data["api_key"]

    entities = [
        FrameItCPU(device_name + " CPU", f"http://{ip}:5000/system/stats", api_key),
        FrameItMem(device_name + " RAM", f"http://{ip}:5000/system/stats", api_key)
        # Add more sensors as needed
    ]

    async_add_entities(entities, True)

class FrameItMem(Entity):
    def __init__(self, name, resource, api_key):
        self._name = name
        self._resource = resource
        self._api_key = api_key
        self._state = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def device_info(self):
        """Return the device information."""
        return {
            "identifiers": {(DOMAIN, self._name)},
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
            async with async_get_clientsession(self.hass).get(
                self._resource, headers=headers
            ) as response:
                data = await response.json()
                self._state = data.get('mem')
        except Exception as e:
            _LOGGER.error(f"Error updating {self.name}: {e}")
class FrameItCPU(Entity):
    def __init__(self, name, resource, api_key):
        self._name = name
        self._resource = resource
        self._api_key = api_key
        self._state = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def device_info(self):
        """Return the device information."""
        return {
            "identifiers": {(DOMAIN, self._name)},
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
            async with async_get_clientsession(self.hass).get(
                self._resource, headers=headers
            ) as response:
                data = await response.json()
                self._state = data.get('cpu')
        except Exception as e:
            _LOGGER.error(f"Error updating {self.name}: {e}")