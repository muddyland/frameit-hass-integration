"""Switch platform for FrameIT — display on/off and service control."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity

_SERVICE_META: dict[str, tuple[str, str]] = {
    "frameit-agent": ("Agent Service", "mdi:robot"),
    "frameit-ui":    ("UI Service",    "mdi:monitor-dashboard"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SwitchEntity] = []
    for frame in coordinator.data.get("frames", []):
        if frame.get("agent_url"):
            entities.append(FrameITDisplaySwitch(coordinator, frame))
            for svc in _SERVICE_META:
                entities.append(FrameITServiceSwitch(coordinator, frame, svc))

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


class FrameITServiceSwitch(FrameITEntity, SwitchEntity):
    """Switch that shows whether a FrameIT service is running.

    Both turn_on and turn_off restart the service — turn_on to start a stopped
    service, turn_off to restart a running one (e.g. refresh the kiosk UI).
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: FrameITCoordinator, frame: dict, service: str
    ) -> None:
        super().__init__(coordinator, frame)
        self._service = service
        name, icon = _SERVICE_META[service]
        self._attr_name = name
        self._attr_icon = icon
        slug = service.replace("-", "_")
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_{slug}_switch"
        )

    @property
    def is_on(self) -> bool | None:
        services = self._services
        if services is None:
            return None
        return services.get(self._service, False)

    @property
    def available(self) -> bool:
        return super().available and self._services is not None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.restart_service(self._frame_id, self._service)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.restart_service(self._frame_id, self._service)
        await self.coordinator.async_request_refresh()
