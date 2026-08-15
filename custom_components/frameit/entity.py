"""Base entity for FrameIT."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FrameITCoordinator


def server_device_info(coordinator: FrameITCoordinator) -> DeviceInfo:
    """DeviceInfo for the FrameIT server itself, shared by server-wide entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        name="FrameIT Server",
        manufacturer="FrameIT",
        model="FrameIT Server",
        configuration_url=f"{coordinator.client.base_url}/admin",
    )


class FrameITServerEntity(CoordinatorEntity[FrameITCoordinator]):
    """Base class for entities that belong to the server rather than a frame."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FrameITCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = server_device_info(coordinator)

    @property
    def _settings(self) -> dict:
        return (self.coordinator.data or {}).get("settings") or {}


class FrameITEntity(CoordinatorEntity[FrameITCoordinator]):
    """Base class for all FrameIT entities.

    Each frame in FrameIT maps to a Home Assistant device.  Entities on
    that device share the device's DeviceInfo and derive their unique_id
    from the config-entry ID + frame ID.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: FrameITCoordinator, frame: dict) -> None:
        super().__init__(coordinator)
        self._frame_id: int = frame["id"]
        frame_name = frame.get("name") or frame["ip"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_{frame['id']}")},
            name=frame_name,
            manufacturer="FrameIT",
            model="Raspberry Pi Frame",
            configuration_url=f"{coordinator.client.base_url}/admin/frames",
        )

    # ------------------------------------------------------------------
    # Helpers used by subclasses
    # ------------------------------------------------------------------

    @property
    def _frame(self) -> dict | None:
        """Return the latest data for this frame, or None if not found."""
        for f in (self.coordinator.data or {}).get("frames", []):
            if f["id"] == self._frame_id:
                return f
        return None

    @property
    def _agent_info(self) -> dict | None:
        """Return agent info dict {system_info, display} or None."""
        return (self.coordinator.data or {}).get("agent_info", {}).get(self._frame_id)

    @property
    def _system_info(self) -> dict | None:
        ai = self._agent_info
        return ai["system_info"] if ai else None

    @property
    def _display_info(self) -> dict | None:
        ai = self._agent_info
        return ai["display"] if ai else None

    @property
    def _services(self) -> dict | None:
        ai = self._agent_info
        return ai.get("services") if ai else None

    @property
    def available(self) -> bool:
        """Mark unavailable if coordinator data is absent."""
        return self.coordinator.last_update_success and self._frame is not None
