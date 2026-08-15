"""DataUpdateCoordinator for FrameIT."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FrameITApiClient,
    FrameITAuthError,
    FrameITError,
    FrameITLockoutError,
)
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


def _or_previous(result: Any, previous: dict, key: str, default: Any) -> Any:
    """Keep the last good value when one leg of the poll fails.

    Zeroing the library on a single hiccup would empty the media browser and
    make every settings switch unavailable for a cycle, which reads as data
    loss rather than as the transient it is.
    """
    if isinstance(result, BaseException):
        _LOGGER.debug("FrameIT poll of %s failed: %s", key, result)
        return previous.get(key, default)
    return result


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
        previous = self.data or {}

        try:
            frames = await self.client.get_frames()
        except FrameITLockoutError as exc:
            # Time-limited and self-clearing — keep polling rather than asking
            # the user to re-enter a password that is probably correct.
            raise UpdateFailed(str(exc)) from exc
        except FrameITAuthError as exc:
            # Changing the admin password on the server invalidates this
            # session for good; only new credentials will fix it.
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except FrameITError as exc:
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

        server_version, posters, trailers, settings = await asyncio.gather(
            self.client.get_server_agent_version(),
            self.client.get_posters(),
            self.client.get_trailers(),
            self.client.get_settings(),
            return_exceptions=True,
        )

        return {
            "frames": frames,
            "agent_info": agent_info,
            "server_agent_version": _or_previous(
                server_version, previous, "server_agent_version", None
            ),
            "posters": _or_previous(posters, previous, "posters", []),
            "trailers": _or_previous(trailers, previous, "trailers", []),
            "settings": _or_previous(settings, previous, "settings", {}),
        }

    async def _fetch_agent_info(self, frame_id: int) -> dict:
        system_info, display, services = await asyncio.gather(
            self.client.get_system_info(frame_id),
            self.client.get_display(frame_id),
            self.client.get_services(frame_id),
        )
        return {"system_info": system_info, "display": display, "services": services}
