"""Select platform for FrameIT — switches a frame between pool and pinned mode."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONTENT_MODES, DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        FrameITContentModeSelect(coordinator, frame)
        for frame in coordinator.data.get("frames", [])
    ]
    async_add_entities(entities)


class FrameITContentModeSelect(FrameITEntity, SelectEntity):
    """Select entity that switches a frame between pool and pinned content mode.

    Switching to 'pinned' retains whichever item is currently pinned in the
    FrameIT admin UI — use the admin panel to choose which poster or trailer
    is shown when pinned.
    """

    _attr_name = "Content Mode"
    _attr_icon = "mdi:television-play"
    _attr_options = CONTENT_MODES

    def __init__(self, coordinator: FrameITCoordinator, frame: dict) -> None:
        super().__init__(coordinator, frame)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_content_mode"
        )

    @property
    def current_option(self) -> str | None:
        frame = self._frame
        return frame.get("content_mode") if frame else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.update_frame(
            self._frame_id, {"content_mode": option}
        )
        await self.coordinator.async_request_refresh()
