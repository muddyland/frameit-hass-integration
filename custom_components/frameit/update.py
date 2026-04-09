"""Update platform for FrameIT — native HA update entity per agent frame."""
from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
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
    entities = [
        FrameITAgentUpdate(coordinator, frame)
        for frame in coordinator.data.get("frames", [])
        if frame.get("agent_url")
    ]
    async_add_entities(entities)


class FrameITAgentUpdate(FrameITEntity, UpdateEntity):
    """Tracks the installed vs available version of the FrameIT agent."""

    _attr_name = "Agent"
    _attr_title = "FrameIT Agent"
    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(self, coordinator: FrameITCoordinator, frame: dict) -> None:
        super().__init__(coordinator, frame)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_agent_update"
        )

    @property
    def installed_version(self) -> str | None:
        frame = self._frame
        return frame.get("agent_version") if frame else None

    @property
    def latest_version(self) -> str | None:
        return (self.coordinator.data or {}).get("server_agent_version")

    async def async_install(self, version: str | None, backup: bool, **kwargs) -> None:
        """Trigger an agent update on the frame."""
        await self.coordinator.client.trigger_agent_update(self._frame_id)
        await self.coordinator.async_request_refresh()
