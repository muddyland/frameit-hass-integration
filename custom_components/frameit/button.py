from homeassistant.components.button import ButtonEntity
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
        FrameItButton(f"{device_name} Reboot", f"http://{ip}/system/reboot", headers)
        # Add more buttons if needed
    ]

    async_add_entities(entities, True)

class FrameItButton(ButtonEntity):
    def __init__(self, name, resource, headers):
        self._name = name
        self._resource = resource
        self._headers = headers

    @property
    def name(self):
        return self._name

    async def async_press(self):
        """Handle the button press."""
        try:
            await self.hass.async_add_executor_job(
                requests.post, self._resource, headers=self._headers
            )
        except Exception as e:
            _LOGGER.error(f"Error occurred while activating {self.name}: {e}")