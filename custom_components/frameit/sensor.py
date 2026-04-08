"""Sensor platform for FrameIT — exposes agent system metrics."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity


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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        FrameITSensor(coordinator, frame, desc)
        for frame in coordinator.data.get("frames", [])
        if frame.get("agent_url")
        for desc in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


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
