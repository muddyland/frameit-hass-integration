"""Config flow for FrameIT."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import (
    FrameITApiClient,
    FrameITAuthError,
    FrameITConnectionError,
    FrameITLockoutError,
)
from .const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, DOMAIN

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _try_login(url: str, username: str, password: str) -> str | None:
    """Return an error key for the form, or None if the credentials work."""
    client = FrameITApiClient(base_url=url, username=username, password=password)
    try:
        await client.login()
    except FrameITLockoutError:
        return "too_many_attempts"
    except FrameITAuthError:
        return "invalid_auth"
    except FrameITConnectionError:
        return "cannot_connect"
    except Exception:  # pylint: disable=broad-except
        return "unknown"
    finally:
        await client.close()
    return None


class FrameITConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FrameIT."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _try_login(
                user_input[CONF_URL],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]  # pylint: disable=unused-argument
    ) -> FlowResult:
        """Start re-authentication.

        Changing the FrameIT admin password signs every other session out, so
        this is a routine path rather than an exceptional one.
        """
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Collect fresh credentials for an existing entry."""
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _try_login(
                entry.data[CONF_URL],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, **user_input}
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )
