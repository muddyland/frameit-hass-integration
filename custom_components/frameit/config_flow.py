import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN

class FrameItConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FrameIt Agent."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FrameItOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            device_name = user_input.get("device_name")

            # You can add additional validation logic here if needed

            return self.async_create_entry(
                title=f"{device_name}",
                data=user_input,
            )

        data_schema = vol.Schema({
            vol.Required("device_name"): str,
            vol.Required("ip"): str,
            vol.Required("api_key"): str,
        })

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)