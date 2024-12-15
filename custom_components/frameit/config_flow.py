import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN

class FrameItConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FrameIt Agent."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(
                title="FrameIt Agent Configuration",
                data={},
            )

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))