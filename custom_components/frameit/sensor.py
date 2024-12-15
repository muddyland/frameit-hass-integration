from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import requests
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    devices = hass.data.get(DOMAIN, {}).values()
    sensors = []

    for device in devices:
        ip = device['ip']
        api_key = device['api_key']
        headers = {
            'X-API-Key': api_key,
            'Content-Type': 'application/json'
        }

        sensors.append(FrameItSensor(f"{device['name']} Frame Status", f"http://{ip}/status", "status", headers))

    async_add_entities(sensors, True)

class FrameItSensor(Entity):
    def __init__(self, name, resource, key, headers):
        self._name = name
        self._resource = resource
        self._key = key
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
            response = await self.hass.async_add_executor_job(
                requests.get, self._resource, {'headers': self._headers, 'timeout': 10}
            )
            data = response.json()
            self._state = data.get(self._key)
        except Exception as e:
            _LOGGER.error(f"Error fetching data for {self._name}: {e}")