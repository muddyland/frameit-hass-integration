from homeassistant.components.switch import SwitchEntity
import logging
import requests

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    data = config_entry.data
    device_name = data["device_name"]
    ip = data["ip"]
    api_key = data["api_key"]
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }

    entities = [
        FrameItSwitch(f"{device_name} Display", f"http://{ip}/display", headers)
        # Add more switches if needed
    ]

    async_add_entities(entities, True)

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
                requests.get, self._resource, headers=self._headers
            )
            data = response.json()
            self._state = data.get("status") == "on"
        except Exception as e:
            _LOGGER.error(f"Error fetching state for {self.name}: {e}")

    async def _async_send_request(self, payload):
        try:
            await self.hass.async_add_executor_job(
                requests.post, self._resource, headers=self._headers, data=payload
            )
        except Exception as e:
            _LOGGER.error(f"Error sending request to {self.name}: {e}")