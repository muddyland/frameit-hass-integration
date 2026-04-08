"""Button platform for FrameIT — next content, refresh browser, reboot Pi."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import FrameITApiClient
from .const import DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity


@dataclass(frozen=True)
class FrameITButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[FrameITApiClient, int], Coroutine[Any, Any, None]] | None = None
    requires_agent: bool = False


BUTTON_DESCRIPTIONS: tuple[FrameITButtonDescription, ...] = (
    FrameITButtonDescription(
        key="next",
        name="Next",
        icon="mdi:skip-next",
        press_fn=lambda client, fid: client.send_command(fid, "next"),
        requires_agent=False,
    ),
    FrameITButtonDescription(
        key="refresh",
        name="Refresh",
        icon="mdi:refresh",
        press_fn=lambda client, fid: client.send_command(fid, "refresh"),
        requires_agent=False,
    ),
    FrameITButtonDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
        press_fn=lambda client, fid: client.reboot(fid),
        requires_agent=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        FrameITButton(coordinator, frame, desc)
        for frame in coordinator.data.get("frames", [])
        for desc in BUTTON_DESCRIPTIONS
        if not desc.requires_agent or frame.get("agent_url")
    ]
    async_add_entities(entities)


class FrameITButton(FrameITEntity, ButtonEntity):
    """A button that triggers a single action on a frame."""

    entity_description: FrameITButtonDescription

    def __init__(
        self,
        coordinator: FrameITCoordinator,
        frame: dict,
        description: FrameITButtonDescription,
    ) -> None:
        super().__init__(coordinator, frame)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_{description.key}"
        )

    async def async_press(self) -> None:
        if self.entity_description.press_fn:
            await self.entity_description.press_fn(
                self.coordinator.client, self._frame_id
            )
