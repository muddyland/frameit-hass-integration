"""Sensor platform for FrameIT — system metrics, IP address, and server stats."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity


# ---------------------------------------------------------------------------
# Per-frame system metric sensors (require agent)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FrameITSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a system_info key."""
    info_key: str = ""


SENSOR_DESCRIPTIONS: tuple[FrameITSensorDescription, ...] = (
    FrameITSensorDescription(
        key="cpu_percent",
        info_key="cpu_percent",
        name="CPU",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    FrameITSensorDescription(
        key="ram_percent",
        info_key="ram_percent",
        name="RAM",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    FrameITSensorDescription(
        key="disk_percent",
        info_key="disk_percent",
        name="Disk",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    FrameITSensorDescription(
        key="cpu_temp",
        info_key="cpu_temp",
        name="CPU Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
)


# ---------------------------------------------------------------------------
# Server-level stat sensors
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FrameITServerSensorDescription:
    key: str
    name: str
    icon: str
    value_fn: Callable[[dict], int] = field(default=lambda _: 0)


SERVER_SENSOR_DESCRIPTIONS: tuple[FrameITServerSensorDescription, ...] = (
    FrameITServerSensorDescription(
        key="frame_count",
        name="Frames",
        icon="mdi:monitor-multiple",
        value_fn=lambda d: len(d.get("frames", [])),
    ),
    FrameITServerSensorDescription(
        key="agent_count",
        name="Online agents",
        icon="mdi:robot",
        value_fn=lambda d: sum(
            1 for f in d.get("frames", []) if f.get("agent_url")
        ),
    ),
    FrameITServerSensorDescription(
        key="poster_count",
        name="Posters",
        icon="mdi:image-multiple",
        value_fn=lambda d: len(d.get("posters", [])),
    ),
    FrameITServerSensorDescription(
        key="trailer_count",
        name="Trailers",
        icon="mdi:movie-open",
        value_fn=lambda d: len(d.get("trailers", [])),
    ),
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = []

    for frame in coordinator.data.get("frames", []):
        entities.append(FrameITIPSensor(coordinator, frame))
        if frame.get("agent_url"):
            entities.extend(
                FrameITSensor(coordinator, frame, desc)
                for desc in SENSOR_DESCRIPTIONS
            )

    entities.extend(
        FrameITServerSensor(coordinator, desc)
        for desc in SERVER_SENSOR_DESCRIPTIONS
    )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Entity classes
# ---------------------------------------------------------------------------

class FrameITSensor(FrameITEntity, SensorEntity):
    """A sensor that reads a value from the agent's system/info endpoint."""

    entity_description: FrameITSensorDescription

    def __init__(
        self,
        coordinator: FrameITCoordinator,
        frame: dict,
        description: FrameITSensorDescription,
    ) -> None:
        super().__init__(coordinator, frame)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_{description.key}"
        )

    @property
    def native_value(self) -> float | None:
        sys_info = self._system_info
        if sys_info is None:
            return None
        return sys_info.get(self.entity_description.info_key)

    @property
    def available(self) -> bool:
        return super().available and self._system_info is not None


class FrameITIPSensor(FrameITEntity, SensorEntity):
    """Sensor that exposes the frame's IP address."""

    _attr_name = "IP Address"
    _attr_icon = "mdi:ip-network"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: FrameITCoordinator, frame: dict) -> None:
        super().__init__(coordinator, frame)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_ip"
        )

    @property
    def native_value(self) -> str | None:
        frame = self._frame
        return frame.get("ip") if frame else None


class FrameITServerSensor(CoordinatorEntity[FrameITCoordinator], SensorEntity):
    """Server-level stat sensor (frames, agents, posters, trailers)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FrameITCoordinator,
        description: FrameITServerSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_server_{description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="FrameIT Server",
            manufacturer="FrameIT",
            model="FrameIT Server",
            configuration_url=(
                f"{coordinator.client._base_url}/admin"  # noqa: SLF001
            ),
        )

    @property
    def native_value(self) -> int:
        return self._description.value_fn(self.coordinator.data)
