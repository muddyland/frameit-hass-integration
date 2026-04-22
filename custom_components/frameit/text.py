"""Text platform for FrameIT — now-playing source configuration."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity
from .now_playing import NowPlayingManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: FrameITCoordinator = data["coordinator"]
    mgr: NowPlayingManager = data["now_playing"]

    async_add_entities(
        FrameITNowPlayingSource(coordinator, frame, mgr)
        for frame in coordinator.data.get("frames", [])
    )


class FrameITNowPlayingSource(FrameITEntity, TextEntity):
    """Text entity for setting which media_player to mirror in now-playing mode.

    The user enters the entity_id of a media player (e.g.
    'media_player.theater_apple_tv').  The Content Mode select entity must
    also be switched to 'now-playing' to activate mirroring.
    """

    _attr_name = "Now Playing Source"
    _attr_icon = "mdi:television-play"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(
        self,
        coordinator: FrameITCoordinator,
        frame: dict,
        mgr: NowPlayingManager,
    ) -> None:
        super().__init__(coordinator, frame)
        self._mgr = mgr
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_now_playing_source"
        )

    @property
    def native_value(self) -> str:
        return self._mgr.get_source(self._frame_id) or ""

    async def async_set_value(self, value: str) -> None:
        await self._mgr.set_source(self._frame_id, value)
