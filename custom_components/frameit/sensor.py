from datetime import timedelta
import requests
import logging
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, CONF_API_KEY, CONF_DEVICES

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=60)

async def async_setup_entry(hass, config_entry, async_add_entities):
    api_key = hass.data[DOMAIN]['api_key']
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }

    devices = hass.data[DOMAIN]['devices']
    sensors = []

    for device in devices:
        ip = device['ip']
        sensors.append(MoviePosterSensor(f"{device['name']} CPU Usage", f"http://{ip}:5000/system/stats", "cpu", headers))
        sensors.append(MoviePosterSensor(f"{device['name']} RAM Usage", f"http://{ip}:5000/system/stats", "mem", headers))

    async_add_entities(sensors, True)

class MoviePosterSensor(Entity):
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
            _LOGGER.error(f"Error fetching data: {e}")