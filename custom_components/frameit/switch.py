from homeassistant.components.switch import SwitchEntity
import requests
import logging
from .const import DOMAIN, CONF_API_KEY, CONF_DEVICES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    api_key = hass.data[DOMAIN]['api_key']
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }

    devices = hass.data[DOMAIN]['devices']
    switches = []

    for device in devices:
        ip = device['ip']
        switches.append(MoviePosterSwitch(device['name'], f"http://{ip}:5000/monitor", headers))

    async_add_entities(switches, True)

class MoviePosterSwitch(SwitchEntity):
    def __init__(self, name, resource, headers):
        self._name = name
        self._resource = resource
        self._state = False
        self._headers = headers

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):
        await self._async_send_request('{"on": "true"}')
        self._state = True

    async def async_turn_off(self, **kwargs):
        await self._async_send_request('{"off": "true"}')
        self._state = False

    async def async_update(self):
        try:
            response = await self.hass.async_add_executor_job(
                requests.get, self._resource, {'headers': self._headers, 'timeout': 10}
            )
            data = response.json()
            self._state = data.get("status") == "on"
        except Exception as e:
            _LOGGER.error(f"Error fetching switch state: {e}")

    async def _async_send_request(self, payload):
        try:
            await self.hass.async_add_executor_job(
                requests.post, self._resource, {'data': payload, 'headers': self._headers, 'timeout': 10}
            )
        except Exception as e:
            _LOGGER.error(f"Error sending request to {self._resource}: {e}")