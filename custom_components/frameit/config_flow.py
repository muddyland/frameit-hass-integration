import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.core import callback
from .const import DOMAIN, CONF_API_KEY, CONF_DEVICES

DEVICE_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Required("ip"): str
})

class MoviePosterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Movie Poster API."""

    VERSION = 1

    def __init__(self):
        self.api_key = None
        self.devices = []

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            self.api_key = user_input[CONF_API_KEY]
            return await self.async_step_add_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
        )

    async def async_step_add_device(self, user_input=None):
        """Handle adding devices."""
        if user_input is not None:
            self.devices.append(user_input)
            return await self.async_step_device_finished()

        return self.async_show_form(
            step_id="add_device",
            data_schema=DEVICE_SCHEMA,
        )

    async def async_step_device_finished(self, user_input=None):
        """Decide if we add another device or finish."""
        if user_input is not None:
            # Ensure user_input is handled as a decision to finish
            # or add more devices
            if user_input.get("add_another_device", False):
                return await self.async_step_add_device()

            return self.async_create_entry(
                title="Movie Posters",
                data={CONF_API_KEY: self.api_key, CONF_DEVICES: self.devices},
            )

        return self.async_show_form(
            step_id="device_finished",
            data_schema=vol.Schema({
                vol.Optional("add_another_device", default=False): bool
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )