"""FrameIT media source — browse the poster and trailer library."""
from __future__ import annotations

from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant

from .const import CONF_URL, DOMAIN


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    return FrameITMediaSource(hass)


class FrameITMediaSource(MediaSource):
    """Browse posters and trailers from the FrameIT server."""

    name = "FrameIT"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        identifier = item.identifier or ""
        parts = [p for p in identifier.split("/") if p]

        if not parts:
            return self._root()

        entry_id = parts[0]

        if len(parts) == 1:
            return self._entry_root(entry_id)

        section = parts[1]
        client, base_url = self._client_and_url(entry_id)

        if section == "posters":
            return await self._browse_posters(entry_id, base_url, client)
        if section == "trailers":
            return await self._browse_trailers(entry_id, base_url, client)

        raise ValueError(f"Unknown section: {section!r}")

    def _root(self) -> BrowseMediaSource:
        entries = self.hass.config_entries.async_entries(DOMAIN)
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=e.entry_id,
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.IMAGE,
                title=e.title,
                can_play=False,
                can_expand=True,
            )
            for e in entries
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE,
            title="FrameIT",
            can_play=False,
            can_expand=True,
            children=children,
        )

    def _entry_root(self, entry_id: str) -> BrowseMediaSource:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        title = entry.title if entry else entry_id
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=entry_id,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE,
            title=title,
            can_play=False,
            can_expand=True,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{entry_id}/posters",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.IMAGE,
                    title="Posters",
                    can_play=False,
                    can_expand=True,
                ),
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{entry_id}/trailers",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MOVIE,
                    title="Trailers",
                    can_play=False,
                    can_expand=True,
                ),
            ],
        )

    async def _browse_posters(
        self, entry_id: str, base_url: str, client
    ) -> BrowseMediaSource:
        posters = await client.get_posters()
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{entry_id}/posters/{p['id']}",
                media_class=MediaClass.IMAGE,
                media_content_type=MediaType.IMAGE,
                title=p.get("title_above") or p.get("title_below") or p["filename"],
                can_play=True,
                can_expand=False,
                thumbnail=self._abs_url(base_url, p["url"]),
            )
            for p in posters
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"{entry_id}/posters",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE,
            title="Posters",
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def _browse_trailers(
        self, entry_id: str, base_url: str, client
    ) -> BrowseMediaSource:
        trailers = await client.get_trailers()
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{entry_id}/trailers/{t['id']}",
                media_class=MediaClass.VIDEO,
                media_content_type=MediaType.MOVIE,
                title=t.get("title") or t["youtube_id"],
                can_play=True,
                can_expand=False,
                thumbnail=self._abs_url(base_url, t["thumb_url"])
                if t.get("thumb_url")
                else None,
            )
            for t in trailers
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"{entry_id}/trailers",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MOVIE,
            title="Trailers",
            can_play=False,
            can_expand=True,
            children=children,
        )

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        parts = item.identifier.split("/", 2)
        if len(parts) < 3:
            raise ValueError(f"Cannot resolve identifier: {item.identifier!r}")
        entry_id, section, media_id = parts
        client, base_url = self._client_and_url(entry_id)

        if section == "posters":
            posters = await client.get_posters()
            poster = next((p for p in posters if str(p["id"]) == media_id), None)
            if poster is None:
                raise ValueError(f"Poster {media_id} not found")
            return PlayMedia(self._abs_url(base_url, poster["url"]), "image/jpeg")

        if section == "trailers":
            trailers = await client.get_trailers()
            trailer = next((t for t in trailers if str(t["id"]) == media_id), None)
            if trailer is None:
                raise ValueError(f"Trailer {media_id} not found")
            if trailer.get("cached_url"):
                return PlayMedia(
                    self._abs_url(base_url, trailer["cached_url"]), "video/mp4"
                )
            return PlayMedia(
                f"https://www.youtube.com/watch?v={trailer['youtube_id']}",
                "video/youtube",
            )

        raise ValueError(f"Unknown section: {section!r}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _client_and_url(self, entry_id: str):
        data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        client = data.get("client")
        if client is None:
            raise ValueError(f"No FrameIT client for entry {entry_id!r}")
        entry = self.hass.config_entries.async_get_entry(entry_id)
        base_url = entry.data[CONF_URL].rstrip("/") if entry else ""
        return client, base_url

    def _abs_url(self, base_url: str, url: str) -> str:
        """Prepend base_url to server-relative paths; leave absolute URLs unchanged."""
        if url.startswith("/"):
            return f"{base_url}{url}"
        return url
