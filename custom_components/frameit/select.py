"""Select platform for FrameIT — content mode and display rotation."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONTENT_MODES, DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity

ROTATION_OPTIONS = ["0", "90", "180", "270"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    for frame in coordinator.data.get("frames", []):
        entities.append(FrameITContentModeSelect(coordinator, frame))
        entities.append(FrameITRotationSelect(coordinator, frame))

    async_add_entities(entities)


class FrameITContentModeSelect(FrameITEntity, SelectEntity):
    """Select entity that switches a frame between pool and pinned content mode."""

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


class FrameITRotationSelect(FrameITEntity, SelectEntity):
    """Select entity that sets the display rotation of a frame."""

    _attr_name = "Rotation"
    _attr_icon = "mdi:screen-rotation"
    _attr_options = ROTATION_OPTIONS
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: FrameITCoordinator, frame: dict) -> None:
        super().__init__(coordinator, frame)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_rotation"
        )

    @property
    def current_option(self) -> str | None:
        frame = self._frame
        return str(frame.get("rotation", 0)) if frame else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.update_frame(
            self._frame_id, {"rotation": int(option)}
        )
        await self.coordinator.async_request_refresh()
