from homeassistant.components.switch import SwitchEntity
import requests
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    devices = hass.data.get(DOMAIN, {}).values()
    switches = []

    for device in devices:
        ip = device['ip']
        api_key = device['api_key']
        headers = {
            'X-API-Key': api_key,
            'Content-Type': 'application/json'
        }

        switches.append(FrameItSwitch(f"{device['name']} Display", f"http://{ip}/display", headers))

    async_add_entities(switches, True)

class FrameItSwitch(SwitchEntity):
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
            _LOGGER.error(f"Error fetching switch state for {self._name}: {e}")

    async def _async_send_request(self, payload):
        try:
            await self.hass.async_add_executor_job(
                requests.post, self._resource, {'data': payload, 'headers': self._headers, 'timeout': 10}
            )
        except Exception as e:
            _LOGGER.error(f"Error sending request to {self._name}: {e}")