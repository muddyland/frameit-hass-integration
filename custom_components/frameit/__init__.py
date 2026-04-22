"""FrameIT integration for Home Assistant."""
from __future__ import annotations

import logging
import os

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import FrameITApiClient, FrameITAuthError, FrameITConnectionError
from .const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, DOMAIN
from .coordinator import FrameITCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["update", "sensor", "switch", "button", "select", "number", "media_player"]

_WWW_DIR = os.path.join(os.path.dirname(__file__), "www")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:  # pylint: disable=unused-argument
    """Register static assets and brand icon JS (runs once at domain load)."""
    if hass.http:
        await hass.http.async_register_static_paths(
            [StaticPathConfig("/frameit_www", _WWW_DIR, cache_headers=True)]
        )
    # frontend_extra_module_url is populated by the frontend component; guard
    # here so minimal test environments (where frontend isn't loaded) don't crash.
    if "frontend_extra_module_url" in hass.data:
        frontend.add_extra_js_url(hass, "/frameit_www/brand.js")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a FrameIT config entry."""
    client = FrameITApiClient(
        base_url=entry.data[CONF_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    try:
        await client.login()
    except FrameITAuthError as exc:
        _LOGGER.error("FrameIT authentication failed: %s", exc)
        await client.close()
        return False
    except FrameITConnectionError as exc:
        _LOGGER.error("Cannot connect to FrameIT: %s", exc)
        await client.close()
        return False

    coordinator = FrameITCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a FrameIT config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].close()
    return unload_ok
