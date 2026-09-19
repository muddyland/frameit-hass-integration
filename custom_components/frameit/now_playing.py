"""Now-playing reporter — pushes one media player's state to the FrameIT server.

The server owns the fan-out: a single global now-playing state is mirrored to
every frame that has opted in via ``show_now_playing``. Home Assistant's only
job is to keep that state fresh, so this module watches one media_player and
POSTs to ``/api/now-playing``.

Three things make that more than a state listener:

* The server stores three text fields, named ``title``/``artist``/``album``
  after the music case it was first built for. A frame renders ``title`` in
  its top banner; the bottom banner is a static "Now Playing" label and no
  longer reflects any of them. (It used to show the source app, which was
  simply blank on integrations that publish no ``app_name`` — HA's Plex
  media_player among them.) ``artist`` and ``album`` are still sent because
  the server stores them, so :func:`_describe` still fills them sensibly for
  video as well as for music.

* A player emits a state_changed event on every position tick. Re-posting on
  each of those would hammer the server and rewrite the album art file several
  times a second, so posts are deduplicated against a fingerprint of the
  fields the server actually stores.
* The server expires now-playing art after ``now_playing_stale_seconds`` with
  no fresh POST. A track longer than that window would fall off the wall
  mid-play if we only posted on change, so an active state is also re-posted
  on a heartbeat comfortably inside the window.

Artwork is not guaranteed. Plenty of sources publish none — YouTube on an
Apple TV is the confirmed case, where the upstream integration genuinely has
no image to offer — so this module has to tell the server the difference
between two situations that used to look identical on the wire:

* **A new item that has no cover.** Sent as ``clear_artwork``, so the server
  drops whatever it is holding. Without this the *previous* item's cover sits
  behind the new title, which reads as the wrong thing playing.
* **The same item, reported again** by a heartbeat or a pause. These carry no
  image because the server already has it, and must never clear anything —
  otherwise the art blinks off once every heartbeat interval.

:meth:`NowPlayingReporter._item_changed` is what separates the two: it compares
the fingerprint with the play state dropped, so a pause or a heartbeat is
recognisably the same thing playing.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .api import FrameITAuthError, FrameITConnectionError
from .const import (
    CONF_NOW_PLAYING_SOURCE,
    CONF_NOW_PLAYING_TOKEN,
    NOW_PLAYING_ACTIVE_STATES,
    NOW_PLAYING_DEFAULT_STALE_SECONDS,
    NOW_PLAYING_HEARTBEAT_RATIO,
    NOW_PLAYING_MIN_HEARTBEAT_SECONDS,
    NOW_PLAYING_MUSIC_CONTENT_TYPE,
    NOW_PLAYING_TV_CONTENT_TYPES,
    NOW_PLAYING_VIDEO_CONTENT_TYPES,
)

_LOGGER = logging.getLogger(__name__)

# HA states that are not media states at all; treat them as "nothing playing"
# rather than passing them to a server that only knows four values.
_UNKNOWN_STATES = ("unavailable", "unknown", "none", "")


def _map_state(ha_state: str | None) -> str:
    """Translate a media_player state into one the webhook accepts."""
    if ha_state is None or ha_state.lower() in _UNKNOWN_STATES:
        return "off"
    value = ha_state.lower()
    if value in NOW_PLAYING_ACTIVE_STATES:
        return value
    if value == "off":
        return "off"
    # standby, idle, buffering and anything a custom integration invents all
    # mean "there is no artwork to show right now".
    return "idle"


def _text(value: Any) -> str | None:
    """Normalise an attribute to a non-blank string, or None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _describe(attrs: Mapping[str, Any]) -> dict[str, str | None]:
    """Map media_player attributes onto the three text fields the server stores.

    The server keeps ``title``, ``artist`` and ``album``. A frame renders
    ``title`` in the top banner; the other two are stored but no longer drive
    any banner, since the bottom one is now a static "Now Playing" label. The
    names are historical, so video content reuses them rather than needing new
    server fields:

    * **TV** — a series title, or a content type that says episode. The title
      is the *series name*, deliberately without a season or episode number,
      so consecutive episodes read as one continuous thing on the wall.
      ``artist`` carries the app the show is coming from.
    * **Film** — a movie or video content type with no series title. The film
      title, with the app in ``artist``.
    * **Music** — unchanged from the original music-only mapping: track,
      artist, album.
    * **Anything else** — the title on its own. Nothing is inferred.

    The order matters. A series title beats everything, because that is the
    one attribute that is never ambiguous. Content type is consulted next, and
    ``media_artist`` only decides the case when nothing before it matched —
    some video players populate it with a director or a channel.

    Nothing here invents metadata. An episode streamed through an app that
    only publishes ``media_title`` and ``media_content_type: video`` (Netflix
    on an Apple TV, among others) is reported as exactly that title: no series
    name reconstructed out of it, and no season or episode guessed.
    """
    series = _text(attrs.get("media_series_title"))
    title = _text(attrs.get("media_title"))
    artist = _text(attrs.get("media_artist"))
    album = _text(attrs.get("media_album_name"))
    app = _text(attrs.get("app_name"))
    content_type = (_text(attrs.get("media_content_type")) or "").lower()

    if series or content_type in NOW_PLAYING_TV_CONTENT_TYPES:
        return {"title": series or title, "artist": app, "album": None}

    if content_type in NOW_PLAYING_VIDEO_CONTENT_TYPES:
        return {"title": title, "artist": app, "album": None}

    if content_type == NOW_PLAYING_MUSIC_CONTENT_TYPE or artist:
        return {"title": title, "artist": artist, "album": album}

    return {"title": title, "artist": None, "album": None}


class NowPlayingReporter:
    """Watches the configured media player and reports it to the server."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._unsub_state: callable | None = None
        self._unsub_heartbeat: callable | None = None
        # The last payload we successfully described to the server, used to
        # suppress re-posts on position ticks.
        self._last_fingerprint: tuple | None = None
        self._last_state: str | None = None
        # The artwork URL whose bytes the server already holds. Heartbeats and
        # metadata-only changes skip the download and the upload.
        self._last_picture: str | None = None
        self._heartbeat_seconds: int | None = None
        self._auth_failed = False
        # Log-once bookkeeping. These exist because both conditions used to be
        # debug-only, which made a real artwork failure invisible to anyone
        # running at default log levels — the bug that started this.
        self._warned_download_urls: set[str] = set()
        self._logged_no_artwork: set[str] = set()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def source(self) -> str | None:
        """The media_player entity_id to mirror, if one is configured."""
        return self._entry.options.get(CONF_NOW_PLAYING_SOURCE) or None

    @property
    def token(self) -> str | None:
        """The webhook bearer token, if one has been stored."""
        return self._entry.options.get(CONF_NOW_PLAYING_TOKEN) or None

    @property
    def configured(self) -> bool:
        return bool(self.source and self.token)

    @property
    def stale_seconds(self) -> int:
        """The server's now_playing_stale_seconds, or the documented default."""
        settings = (self._coordinator.data or {}).get("settings") or {}
        value = settings.get("now_playing_stale_seconds")
        try:
            value = int(value)
        except (TypeError, ValueError):
            return NOW_PLAYING_DEFAULT_STALE_SECONDS
        return value if value > 0 else NOW_PLAYING_DEFAULT_STALE_SECONDS

    @property
    def heartbeat_seconds(self) -> int:
        """How often to re-post while something is playing.

        Half the staleness window, so one dropped request still leaves time for
        the next one to land before the frame drops the art.
        """
        interval = int(self.stale_seconds * NOW_PLAYING_HEARTBEAT_RATIO)
        return max(NOW_PLAYING_MIN_HEARTBEAT_SECONDS, interval)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Subscribe to the source player and push its current state once."""
        if not self.configured:
            _LOGGER.debug(
                "Now-playing reporting is idle: set a source player and a token "
                "in the FrameIT integration options to enable it"
            )
            return

        source = self.source
        self._unsub_state = async_track_state_change_event(
            self._hass, [source], self._handle_state_event
        )
        self._schedule_heartbeat()
        await self.async_report(force=True)

    @callback
    def async_stop(self) -> None:
        """Cancel the state listener and heartbeat (called on entry unload)."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        self._cancel_heartbeat()

    @callback
    def _cancel_heartbeat(self) -> None:
        if self._unsub_heartbeat:
            self._unsub_heartbeat()
            self._unsub_heartbeat = None
        self._heartbeat_seconds = None

    @callback
    def _schedule_heartbeat(self) -> None:
        """(Re)arm the heartbeat timer for the server's current staleness window.

        The window is a server setting the user can change at any time, so the
        interval is re-derived on every beat rather than fixed at startup. A
        change therefore takes effect within one old beat, which is well inside
        the window it is protecting.
        """
        seconds = self.heartbeat_seconds
        if self._unsub_heartbeat and seconds == self._heartbeat_seconds:
            return
        self._cancel_heartbeat()
        self._heartbeat_seconds = seconds
        self._unsub_heartbeat = async_track_time_interval(
            self._hass, self._handle_heartbeat, timedelta(seconds=seconds)
        )

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    @callback
    def _handle_state_event(self, _event: Event) -> None:
        """React to a state_changed event on the source player.

        The event payload is ignored on purpose: async_report re-reads the
        current state and decides for itself whether anything worth sending
        actually changed.
        """
        self._hass.async_create_task(self.async_report())

    async def _handle_heartbeat(self, _now) -> None:
        """Keep an active now-playing state from going stale on the server."""
        self._schedule_heartbeat()
        if self._last_state not in NOW_PLAYING_ACTIVE_STATES:
            # Nothing is on the wall, so there is nothing to keep alive. The
            # server ages the row out on its own.
            return
        await self.async_report(force=True)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _fingerprint(self, state) -> tuple:
        """The subset of the player's state the server actually stores.

        Everything else a media player publishes — position, volume, shuffle —
        is deliberately excluded so a position tick does not look like a track
        change.

        The raw attributes are fingerprinted rather than the banner text
        _describe derives from them. Two consecutive episodes of the same show
        on the same app produce identical banners by design, and that must
        still count as a change: the artwork behind them is different, and the
        server would otherwise keep showing the previous episode's still.
        """
        attrs = state.attributes if state else {}
        return (
            _map_state(state.state if state else None),
            attrs.get("media_title"),
            attrs.get("media_artist"),
            attrs.get("media_album_name"),
            attrs.get("media_series_title"),
            attrs.get("media_season"),
            attrs.get("media_episode"),
            attrs.get("media_content_type"),
            attrs.get("app_name"),
            attrs.get("media_content_id"),
            attrs.get("entity_picture"),
        )

    def _item_changed(self, fingerprint: tuple) -> bool:
        """Whether this is a different *item* from the one last reported.

        The fingerprint minus its first element, which is the mapped play
        state. Dropping that is the whole point: a pause, a resume or a
        heartbeat is the same item in a new state, and must not be mistaken
        for new content whose artwork needs clearing.
        """
        if self._last_fingerprint is None:
            return True
        return fingerprint[1:] != self._last_fingerprint[1:]

    async def async_report(self, force: bool = False) -> None:
        """Post the source player's current state, unless nothing has changed."""
        if not self.configured or self._auth_failed:
            return

        source = self.source
        state = self._hass.states.get(source)
        fingerprint = self._fingerprint(state)
        if not force and fingerprint == self._last_fingerprint:
            return

        mapped = fingerprint[0]
        attrs = state.attributes if state else {}
        picture = attrs.get("entity_picture")
        item_changed = self._item_changed(fingerprint)
        active = mapped in NOW_PLAYING_ACTIVE_STATES
        described = _describe(attrs)

        image: bytes | None = None
        if active and picture:
            # Only fetch the artwork when it is genuinely new. A heartbeat or a
            # pause/resume on the same track re-uses what the server already has.
            if picture != self._last_picture:
                image = await self._download(picture)
                if image is None:
                    # Leave _last_picture alone so the next attempt retries the
                    # download rather than assuming the server has the art.
                    _LOGGER.debug("Reporting now-playing without artwork for %s", source)
        elif active and not picture:
            self._log_missing_artwork(source, described["title"])

        # Only a *new* item with no usable art may clear what the server holds.
        # A heartbeat or a pause repost of the same item takes the quiet path,
        # or the cover would blink off once per heartbeat interval.
        clear_artwork = active and image is None and item_changed

        try:
            await self._coordinator.client.post_now_playing(
                self.token,
                mapped,
                title=described["title"],
                artist=described["artist"],
                album=described["album"],
                entity_id=source,
                image=image,
                clear_artwork=clear_artwork,
            )
        except FrameITAuthError as exc:
            # A bad token will not fix itself; stop hammering the endpoint and
            # leave a message that says what to do about it.
            self._auth_failed = True
            _LOGGER.error("%s", exc)
            return
        except FrameITConnectionError as exc:
            _LOGGER.warning("Could not report now-playing to FrameIT: %s", exc)
            return

        self._last_fingerprint = fingerprint
        self._last_state = mapped
        if image is not None:
            self._last_picture = picture
        elif not active:
            self._last_picture = None
            # Nothing is on the wall, so the next thing to play is worth a
            # fresh line in the log even if it is the same title as before.
            self._logged_no_artwork.clear()

    # ------------------------------------------------------------------
    # Artwork
    # ------------------------------------------------------------------

    def _log_missing_artwork(self, source: str, title: str | None) -> None:
        """Note, once per title, that a player is publishing no artwork at all.

        Info rather than debug: this is the normal, permanent behaviour of some
        sources (HA's apple_tv integration publishes no ``entity_picture`` for
        YouTube, because pyatv has none to give), and someone looking at a
        frame showing a placeholder should be able to find out why without
        turning on debug logging for the whole component.
        """
        key = title or source
        if key in self._logged_no_artwork:
            return
        # Bounded: a long session of art-less items should not grow this set
        # without limit. Forgetting just means one more log line later.
        if len(self._logged_no_artwork) >= 64:
            self._logged_no_artwork.clear()
        self._logged_no_artwork.add(key)
        _LOGGER.info(
            "%s is playing %s but publishes no artwork; the frame will show a "
            "placeholder instead",
            source,
            title or "an untitled item",
        )

    async def _download(self, entity_picture: str) -> bytes | None:
        """Fetch image bytes; resolves relative HA proxy URLs to an absolute URL."""
        session = async_get_clientsession(self._hass)
        try:
            if entity_picture.startswith("/"):
                url = f"{self._ha_base_url()}{entity_picture}"
            else:
                url = entity_picture
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                # Once per URL: a heartbeat retries the same failing URL every
                # few minutes, and a warning repeated forever is noise. The
                # first one is the useful one.
                if url not in self._warned_download_urls:
                    self._warned_download_urls.add(url)
                    _LOGGER.warning(
                        "Now-playing artwork download returned HTTP %s for %s; "
                        "the frame will show a placeholder instead",
                        resp.status,
                        url,
                    )
                else:
                    _LOGGER.debug(
                        "Image download returned HTTP %s for %s", resp.status, url
                    )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Could not download now-playing artwork: %s", exc)
        return None

    def _ha_base_url(self) -> str:
        try:
            return get_url(
                self._hass,
                allow_internal=True,
                prefer_external=False,
                require_ssl=False,
            )
        except NoURLAvailableError:
            return "http://localhost:8123"
