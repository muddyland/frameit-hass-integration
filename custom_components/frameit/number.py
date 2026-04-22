"""Number platform for FrameIT — display interval in seconds."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        FrameITIntervalNumber(coordinator, frame)
        for frame in coordinator.data.get("frames", [])
    )


class FrameITIntervalNumber(FrameITEntity, NumberEntity):
    """Number entity that controls how long each piece of content is shown."""

    _attr_name = "Display Interval"
    _attr_icon = "mdi:timer"
    _attr_native_min_value = 10
    _attr_native_max_value = 3600
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: FrameITCoordinator, frame: dict) -> None:
        super().__init__(coordinator, frame)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_interval"
        )

    @property
    def native_value(self) -> float | None:
        frame = self._frame
        return frame.get("interval_seconds") if frame else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.update_frame(
            self._frame_id, {"interval_seconds": int(value)}
        )
        await self.coordinator.async_request_refresh()
