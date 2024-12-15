from homeassistant.components.button import ButtonEntity
import requests
import logging
from .const import DOMAIN, CONF_DEVICES, BUTTON_NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the buttons from a config entry."""
    api_key = hass.data[DOMAIN]['api_key']
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }

    devices = hass.data[DOMAIN]['devices']
    buttons = [RebootDeviceButton(device['name'], f"http://{device['ip']}:5000/system/reboot", headers) for device in devices]
    
    async_add_entities(buttons, True)

class RebootDeviceButton(ButtonEntity):
    def __init__(self, name, url, headers):
        """Initialize the button."""
        self._name = f"{name} {BUTTON_NAME}"
        self._url = url
        self._headers = headers

    @property
    def name(self):
        """Return the name of the button."""
        return self._name

    async def async_press(self):
        """Handle the button press."""
        try:
            response = await self.hass.async_add_executor_job(
                requests.post, self._url, {'headers': self._headers, 'timeout': 10}
            )
            if response.status_code != 200:
                _LOGGER.error(f"Failed to reboot {self._name}. Status code: {response.status_code}")
        except requests.RequestException as e:
            _LOGGER.error(f"Error attempting to reboot {self._name}: {e}")