"""Media player platform for FrameIT — browse and set media on a frame."""
from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components.media_source import async_browse_media as ms_browse_media
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FrameITCoordinator
from .entity import FrameITEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FrameITCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        FrameITMediaPlayer(coordinator, frame)
        for frame in coordinator.data.get("frames", [])
    )


class FrameITMediaPlayer(FrameITEntity, MediaPlayerEntity):
    """Media player for a single FrameIT frame.

    Lets the user browse the poster/trailer library and pin a specific item
    to the frame, or advance to the next item in pool mode.
    """

    _attr_name = "Display"
    _attr_supported_features = (
        MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.NEXT_TRACK
    )

    def __init__(self, coordinator: FrameITCoordinator, frame: dict) -> None:
        super().__init__(coordinator, frame)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{frame['id']}_media_player"
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> MediaPlayerState:
        frame = self._frame
        if not frame or not frame.get("last_seen"):
            return MediaPlayerState.IDLE
        return MediaPlayerState.PLAYING

    # ------------------------------------------------------------------
    # Current media metadata
    # ------------------------------------------------------------------

    @property
    def media_content_type(self) -> str | None:
        preview = (self._frame or {}).get("preview")
        if not preview:
            return None
        return MediaType.IMAGE if preview["type"] == "poster" else MediaType.VIDEO

    @property
    def media_title(self) -> str | None:
        preview = (self._frame or {}).get("preview")
        return preview.get("title") if preview else None

    @property
    def media_image_url(self) -> str | None:
        preview = (self._frame or {}).get("preview")
        if not preview:
            return None
        thumb = preview.get("thumb_url", "")
        if thumb.startswith("/"):
            return f"{self.coordinator.client._base_url}{thumb}"  # noqa: SLF001
        return thumb or None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def async_media_next_track(self) -> None:
        await self.coordinator.client.send_command(self._frame_id, "next")
        await self.coordinator.async_request_refresh()

    async def async_play_media(
        self,
        media_type: str,
        media_id: str,
        **kwargs,
    ) -> None:
        """Pin a poster or trailer to this frame.

        Accepts media-source URIs of the form:
          media-source://frameit/{entry_id}/posters/{id}
          media-source://frameit/{entry_id}/trailers/{id}
        """
        prefix = f"media-source://{DOMAIN}/"
        if not media_id.startswith(prefix):
            _LOGGER.warning("FrameIT media player cannot handle media_id %r", media_id)
            return

        parts = media_id[len(prefix):].split("/")
        if len(parts) < 3:
            raise ValueError(f"Cannot parse media_id: {media_id!r}")

        _entry_id, section, item_id = parts[0], parts[1], parts[2]
        pinned_type = "poster" if section == "posters" else "trailer"

        await self.coordinator.client.update_frame(
            self._frame_id,
            {
                "content_mode": "pinned",
                "pinned_type": pinned_type,
                "pinned_id": int(item_id),
            },
        )
        await self.coordinator.async_request_refresh()

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        if not media_content_id:
            media_content_id = (
                f"media-source://{DOMAIN}/{self.coordinator.config_entry.entry_id}"
            )

        return await ms_browse_media(self.hass, media_content_id)
