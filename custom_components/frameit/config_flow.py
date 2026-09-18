"""Config and options flows for FrameIT."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import FrameITApiClient, FrameITAuthError, FrameITConnectionError
from .const import (
    CONF_NOW_PLAYING_SOURCE,
    CONF_NOW_PLAYING_TOKEN,
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    DOMAIN,
)

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

CONF_GENERATE_TOKEN = "generate_token"


class FrameITConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FrameIT."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # pylint: disable=unused-argument
    ) -> "FrameITOptionsFlow":
        # HA calls this positionally and the flow reads self.config_entry, so
        # the argument is part of the signature rather than something we use.
        return FrameITOptionsFlow()

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


class FrameITOptionsFlow(config_entries.OptionsFlow):
    """Configure the now-playing source player and webhook token.

    These live in the config entry rather than in entities: the token is a
    credential, and a text entity would put it in plain sight on a dashboard
    and in the state machine's history.
    """

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        options = dict(self.config_entry.options)
        current_token = options.get(CONF_NOW_PLAYING_TOKEN, "")

        if user_input is not None:
            source = (user_input.get(CONF_NOW_PLAYING_SOURCE) or "").strip()
            token = (user_input.get(CONF_NOW_PLAYING_TOKEN) or "").strip()

            if user_input.get(CONF_GENERATE_TOKEN):
                # Minting invalidates any token already issued, so only do it
                # when the box is explicitly ticked.
                new_token = await self._async_mint_token()
                if new_token is None:
                    errors["base"] = "token_failed"
                else:
                    token = new_token

            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_NOW_PLAYING_SOURCE: source,
                        CONF_NOW_PLAYING_TOKEN: token,
                    },
                )
            current_token = token

        schema = vol.Schema(
            {
                # Suggested rather than defaulted: an EntitySelector will not
                # validate the empty string, so leaving it blank has to mean
                # "key absent" rather than "key set to nothing".
                vol.Optional(
                    CONF_NOW_PLAYING_SOURCE,
                    description={
                        "suggested_value": options.get(CONF_NOW_PLAYING_SOURCE, "")
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="media_player")
                ),
                vol.Optional(
                    CONF_NOW_PLAYING_TOKEN, default=current_token
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(CONF_GENERATE_TOKEN, default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )

    async def _async_mint_token(self) -> str | None:
        """Ask the server for a fresh webhook token, or None if it could not."""
        data = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if not data:
            return None
        try:
            return await data["client"].create_now_playing_token()
        except Exception:  # pylint: disable=broad-except
            return None
