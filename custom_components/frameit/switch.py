from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up switches for each FrameIt device."""
    data = config_entry.data
    device_name = data["device_name"]
    ip = data["ip"]
    api_key = data["api_key"]

    entities = [
        FrameItSwitch(device_name + " Monitor", f"http://{ip}:5000/monitor", api_key, config_entry.entry_id)
        # Add more switches if needed
    ]

    async_add_entities(entities, True)

class FrameItSwitch(SwitchEntity):
    def __init__(self, name, resource, api_key, config_entry_id):
        self._name = name + " Monitor"
        self._device_name = name
        self._resource = resource
        self._api_key = api_key
        self._state = False
        self._config_entry_id = config_entry_id

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._state

    @property
    def device_info(self):
        """Return the device information."""
        return {
            "identifiers": {(DOMAIN, self._device_name)},
            "name": self._name,
            "manufacturer": "FrameIt",
            "model": "Smart Frame",
        }

    async def async_turn_on(self, **kwargs):
        await self._async_send_request('{"on": true}')
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._async_send_request('{"off": true}')
        self._state = False
        self.async_write_ha_state()

    async def async_update(self):
        headers = {
            'X-API-Key': self._api_key,
            'Content-Type': 'application/json'
        }
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(self._resource, headers=headers) as response:
                data = await response.json()
                self._state = data.get("status") == "on"
        except Exception as e:
            _LOGGER.error(f"Error fetching state for {self.name}: {e}")

    async def _async_send_request(self, payload):
        headers = {
            'X-API-Key': self._api_key,
            'Content-Type': 'application/json'
        }
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(self._resource, headers=headers, data=payload) as response:
                response.raise_for_status()
        except Exception as e:
            _LOGGER.error(f"Error sending request to {self.name}: {e}")