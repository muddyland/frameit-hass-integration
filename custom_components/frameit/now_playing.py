"""Now-playing manager — watches a media player and mirrors its artwork to a frame."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1


class NowPlayingManager:
    """Manages per-frame "now-playing" mode.

    Watches a nominated media_player entity and, whenever it starts playing
    new content, downloads its artwork, uploads it to the FrameIT server as
    an (inactive) poster, and pins that poster to the frame.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._store = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}.now_playing.{entry.entry_id}"
        )
        # {frame_id: {"source": entity_id, "active": bool, "poster_id": int|None}}
        self._config: dict[int, dict] = {}
        self._unsubs: dict[int, callable] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Restore persisted config and re-subscribe for active frames."""
        stored = await self._store.async_load() or {}
        self._config = {int(k): v for k, v in stored.items()}
        for frame_id, cfg in self._config.items():
            if cfg.get("active") and cfg.get("source"):
                self._subscribe(frame_id, cfg["source"])

    @callback
    def async_stop(self) -> None:
        """Cancel all state listeners (called on entry unload)."""
        for unsub in self._unsubs.values():
            unsub()
        self._unsubs.clear()

    # ------------------------------------------------------------------
    # Public API (used by select and text entities)
    # ------------------------------------------------------------------

    def is_active(self, frame_id: int) -> bool:
        return bool(self._config.get(frame_id, {}).get("active"))

    def get_source(self, frame_id: int) -> str | None:
        return self._config.get(frame_id, {}).get("source")

    async def set_source(self, frame_id: int, source: str) -> None:
        """Update the tracked media player for a frame."""
        cfg = self._config.setdefault(frame_id, {})
        cfg["source"] = source.strip() or None
        await self._save()
        if cfg.get("active") and cfg["source"]:
            self._subscribe(frame_id, cfg["source"])
            await self._push(frame_id)

    async def enable(self, frame_id: int) -> None:
        """Switch a frame into now-playing mode."""
        cfg = self._config.setdefault(frame_id, {})
        cfg["active"] = True
        await self._save()
        source = cfg.get("source")
        if source:
            self._subscribe(frame_id, source)
            await self._push(frame_id)

    async def disable(self, frame_id: int) -> None:
        """Deactivate now-playing mode and revert the frame to pool."""
        self._unsubscribe(frame_id)
        cfg = self._config.get(frame_id, {})
        poster_id = cfg.pop("poster_id", None)
        cfg["active"] = False
        if poster_id:
            try:
                await self._coordinator.client.delete_poster(poster_id)
            except Exception:  # pylint: disable=broad-except
                pass
        await self._save()
        try:
            await self._coordinator.client.update_frame(
                frame_id, {"content_mode": "pool"}
            )
            await self._coordinator.async_request_refresh()
        except Exception:  # pylint: disable=broad-except
            pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _subscribe(self, frame_id: int, source: str) -> None:
        self._unsubscribe(frame_id)

        @callback
        def _handle(event: Event) -> None:
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            if new is None or new.state != "playing":
                return
            old_pic = old.attributes.get("entity_picture") if old else None
            new_pic = new.attributes.get("entity_picture")
            if new_pic and new_pic != old_pic:
                self._hass.async_create_task(self._push(frame_id))

        self._unsubs[frame_id] = async_track_state_change_event(
            self._hass, [source], _handle
        )

    def _unsubscribe(self, frame_id: int) -> None:
        unsub = self._unsubs.pop(frame_id, None)
        if unsub:
            unsub()

    async def _push(self, frame_id: int) -> None:
        """Download artwork from the source player and pin it to the frame."""
        cfg = self._config.get(frame_id, {})
        source = cfg.get("source")
        if not source:
            return

        state = self._hass.states.get(source)
        if not state:
            return

        entity_picture = state.attributes.get("entity_picture")
        if not entity_picture:
            return

        image_data = await self._download(entity_picture)
        if not image_data:
            return

        client = self._coordinator.client

        old_poster_id = cfg.get("poster_id")
        if old_poster_id:
            try:
                await client.delete_poster(old_poster_id)
            except Exception:  # pylint: disable=broad-except
                pass
            cfg["poster_id"] = None

        try:
            poster = await client.upload_poster(
                image_data,
                f"now_playing_{frame_id}.jpg",
                title_above="Now Playing",
                title_below="In Theater",
            )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to upload now-playing artwork for frame %s: %s", frame_id, exc)
            return

        poster_id = poster["id"]
        cfg["poster_id"] = poster_id
        await self._save()

        try:
            await client.update_frame(
                frame_id,
                {"content_mode": "pinned", "pinned_type": "poster", "pinned_id": poster_id},
            )
            await self._coordinator.async_request_refresh()
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to pin now-playing poster to frame %s: %s", frame_id, exc)

    async def _download(self, entity_picture: str) -> bytes | None:
        """Fetch image bytes; resolves relative HA proxy URLs to an absolute URL."""
        session = async_get_clientsession(self._hass)
        try:
            if entity_picture.startswith("/"):
                base = await self._ha_base_url()
                url = f"{base}{entity_picture}"
            else:
                url = entity_picture
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                _LOGGER.debug("Image download returned HTTP %s for %s", resp.status, url)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Could not download now-playing artwork: %s", exc)
        return None

    async def _ha_base_url(self) -> str:
        from homeassistant.helpers.network import get_url
        from homeassistant.exceptions import NoURLAvailableError

        try:
            return get_url(
                self._hass,
                allow_internal=True,
                prefer_external=False,
                require_ssl=False,
            )
        except NoURLAvailableError:
            return "http://localhost:8123"

    def _frame_name(self, frame_id: int) -> str:
        for f in (self._coordinator.data or {}).get("frames", []):
            if f["id"] == frame_id:
                return f.get("name") or f.get("ip", str(frame_id))
        return str(frame_id)

    async def _save(self) -> None:
        await self._store.async_save({str(k): v for k, v in self._config.items()})
