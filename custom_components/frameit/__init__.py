"""FrameIT integration for Home Assistant."""
from __future__ import annotations

import logging
import os
import re

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import FrameITApiClient, FrameITAuthError, FrameITConnectionError
from .const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, DOMAIN
from .coordinator import FrameITCoordinator
from .now_playing import NowPlayingReporter

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["update", "sensor", "switch", "button", "select", "number", "media_player"]

_WWW_DIR = os.path.join(os.path.dirname(__file__), "www")

# Version 1 mirrored artwork by uploading it as a poster named
# now_playing_<frame_id>.jpg and pinning it. The server prefixes uploads with a
# uuid, so the leftovers look like "<32 hex>_now_playing_1.jpg".
_LEGACY_POSTER_RE = re.compile(r"now_playing_\d+\.(jpg|jpeg|png|webp)$", re.IGNORECASE)
_LEGACY_STORAGE_VERSION = 1


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

    coordinator = FrameITCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    await _async_cleanup_legacy_posters(hass, entry, coordinator)

    reporter = NowPlayingReporter(hass, entry, coordinator)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "now_playing": reporter,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await reporter.async_start()

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a FrameIT config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        data["now_playing"].async_stop()
        await data["client"].close()
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the source player or token changes.

    A reload is the simplest correct answer: the reporter caches the token and
    its state subscription, and both are chosen at start.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_cleanup_legacy_posters(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: FrameITCoordinator
) -> None:
    """Delete the artwork posters version 1 uploaded, once.

    Version 1 pinned album art to each frame by uploading it as an inactive
    poster. Version 2 lets the server hold one now-playing image instead, so
    those uploads are orphaned — they clutter the library and take up disk
    until something removes them. The v1 store file is the marker: while it
    exists there is cleaning up to do, and removing it is what makes this a
    one-time job.
    """
    store = Store(
        hass, _LEGACY_STORAGE_VERSION, f"{DOMAIN}.now_playing.{entry.entry_id}"
    )
    try:
        stored = await store.async_load()
    except Exception:  # pylint: disable=broad-except
        stored = None

    if stored is None:
        return

    # Poster IDs v1 recorded, plus anything in the library still carrying the
    # old filename — a crash between upload and save could leave an orphan the
    # store never heard about.
    poster_ids: set[int] = set()
    for cfg in stored.values():
        if isinstance(cfg, dict) and cfg.get("poster_id"):
            poster_ids.add(int(cfg["poster_id"]))

    for poster in (coordinator.data or {}).get("posters", []) or []:
        if _LEGACY_POSTER_RE.search(poster.get("filename") or ""):
            poster_ids.add(int(poster["id"]))

    for poster_id in sorted(poster_ids):
        try:
            await coordinator.client.delete_poster(poster_id)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Could not remove leftover now-playing poster %s: %s", poster_id, exc
            )

    if poster_ids:
        _LOGGER.info(
            "Removed %d leftover now-playing poster(s) from the previous "
            "FrameIT integration version",
            len(poster_ids),
        )
        await coordinator.async_request_refresh()

    try:
        await store.async_remove()
    except Exception as exc:  # pylint: disable=broad-except
        _LOGGER.debug("Could not remove legacy now-playing store: %s", exc)
