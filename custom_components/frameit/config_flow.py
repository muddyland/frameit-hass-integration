"""Config flow for FrameIT."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import FrameITApiClient, FrameITAuthError, FrameITConnectionError
from .const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, DOMAIN

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class FrameITConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FrameIT."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            client = FrameITApiClient(
                base_url=user_input[CONF_URL],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )
            try:
                await client.login()
            except FrameITAuthError:
                errors["base"] = "invalid_auth"
            except FrameITConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                # Use the server URL as the unique ID so you can't add the
                # same server twice.
                await self.async_set_unique_id(user_input[CONF_URL].rstrip("/"))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_URL].rstrip("/"),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_SCHEMA,
            errors=errors,
        )
