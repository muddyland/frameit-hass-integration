"""DataUpdateCoordinator for FrameIT."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FrameITApiClient, FrameITConnectionError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class FrameITCoordinator(DataUpdateCoordinator):
    """Polls the FrameIT server for all frame and agent data."""

    def __init__(self, hass: HomeAssistant, client: FrameITApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict:
        try:
            frames = await self.client.get_frames()
        except FrameITConnectionError as exc:
            raise UpdateFailed(f"Cannot connect to FrameIT: {exc}") from exc

        # Fetch agent info for all frames that have a registered agent,
        # in parallel to keep the poll fast.
        agent_frames = [f for f in frames if f.get("agent_url")]
        if agent_frames:
            results = await asyncio.gather(
                *[self._fetch_agent_info(f["id"]) for f in agent_frames],
                return_exceptions=True,
            )
            agent_info = {
                f["id"]: r
                for f, r in zip(agent_frames, results)
                if not isinstance(r, Exception)
            }
        else:
            agent_info = {}

        return {"frames": frames, "agent_info": agent_info}

    async def _fetch_agent_info(self, frame_id: int) -> dict:
        system_info, display = await asyncio.gather(
            self.client.get_system_info(frame_id),
            self.client.get_display(frame_id),
        )
        return {"system_info": system_info, "display": display}
