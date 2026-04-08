"""Switch platform for FrameIT — controls the display (monitor on/off)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Only create display switches for frames that have a registered agent.
    entities = [
        FrameITDisplaySwitch(coordinator, frame)
        for frame in coordinator.data.get("frames", [])
        if frame.get("agent_url")
    ]
    async_add_entities(entities)


class FrameITDisplaySwitch(FrameITEntity, SwitchEntity):
    """Switch that turns the connected monitor on or off via DPMS."""

    _attr_name = "Display"
    _attr_icon = "mdi:monitor"

    def __init__(self, coordinator: FrameITCoordinator, frame: dict) -> None:
        super().__init__(coordinator, frame)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_display"
        )

    @property
    def is_on(self) -> bool | None:
        display = self._display_info
        if display is None:
            return None
        return display.get("on")

    @property
    def available(self) -> bool:
        return super().available and self._display_info is not None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.set_display(self._frame_id, on=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.set_display(self._frame_id, on=False)
        await self.coordinator.async_request_refresh()
