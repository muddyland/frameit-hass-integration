"""Tests for now-playing reporting — reporter, per-frame switch, options flow."""
from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.frameit.api import FrameITAuthError, FrameITConnectionError
from custom_components.frameit.const import (
    CONF_NOW_PLAYING_SOURCE,
    CONF_NOW_PLAYING_TOKEN,
    DOMAIN,
    NOW_PLAYING_STATES,
)
from custom_components.frameit.now_playing import (
    NowPlayingReporter,
    _describe,
    _map_state,
)
from tests.conftest import (
    MOCK_FRAMES,
    MOCK_PASSWORD,
    MOCK_SETTINGS,
    MOCK_URL,
    MOCK_USERNAME,
    mock_client,
    mock_coordinator_data,
)

SOURCE = "media_player.apple_tv"
TOKEN = "deadbeef" * 8


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_client, mock_coordinator_data):
    """Load the integration with a source player and token configured."""
    hass.states.async_set(SOURCE, "off", {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        options={
            CONF_NOW_PLAYING_SOURCE: SOURCE,
            CONF_NOW_PLAYING_TOKEN: TOKEN,
        },
        entry_id="test_frameit_entry",
        title="FrameIT Test",
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.frameit.FrameITApiClient", return_value=mock_client),
        patch(
            "custom_components.frameit.coordinator.FrameITCoordinator._async_update_data",
            return_value=mock_coordinator_data,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


def _reporter(hass, entry_id="test_frameit_entry") -> NowPlayingReporter:
    return hass.data[DOMAIN][entry_id]["now_playing"]


@pytest.fixture
def reporter(hass):
    """A standalone reporter over a mock coordinator, with options configured."""
    coordinator = MagicMock()
    coordinator.data = {"frames": MOCK_FRAMES, "settings": MOCK_SETTINGS}
    coordinator.client = MagicMock()
    coordinator.client.post_now_playing = AsyncMock(
        return_value={"ok": True, "state": "playing", "frames_signalled": 1}
    )
    coordinator.async_request_refresh = AsyncMock()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        options={CONF_NOW_PLAYING_SOURCE: SOURCE, CONF_NOW_PLAYING_TOKEN: TOKEN},
        entry_id="reporter_test_entry",
    )
    # Registered so tests can change options through the normal API.
    entry.add_to_hass(hass)
    return NowPlayingReporter(hass, entry, coordinator)


def _playing(hass, **overrides):
    attrs = {
        "entity_picture": "https://example.com/cover.jpg",
        "media_title": "Bohemian Rhapsody",
        "media_artist": "Queen",
        "media_album_name": "A Night at the Opera",
        "media_content_id": "track-1",
    }
    attrs.update(overrides)
    hass.states.async_set(SOURCE, "playing", attrs)


# ---------------------------------------------------------------------------
# State mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ha_state", "expected"),
    [
        ("playing", "playing"),
        ("paused", "paused"),
        ("idle", "idle"),
        ("off", "off"),
        ("standby", "idle"),
        ("buffering", "idle"),
        ("unavailable", "off"),
        ("unknown", "off"),
        (None, "off"),
    ],
)
def test_map_state(ha_state, expected):
    assert _map_state(ha_state) == expected


@pytest.mark.parametrize(
    "ha_state",
    ["playing", "paused", "idle", "off", "standby", "buffering", "on", "", "weird"],
)
def test_map_state_only_emits_states_the_server_accepts(ha_state):
    """The webhook 400s on anything outside its four values."""
    assert _map_state(ha_state) in NOW_PLAYING_STATES


# ---------------------------------------------------------------------------
# Banner text: what a film, an episode and a track each put on the two lines
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "attrs", "expected"),
    [
        (
            "film with an app name",
            {
                "media_title": "Blade Runner 2049",
                "media_content_type": "movie",
                "app_name": "Plex",
            },
            {"title": "Blade Runner 2049", "artist": "Plex", "album": None},
        ),
        (
            "film with no app name leaves the bottom line blank",
            {"media_title": "Blade Runner 2049", "media_content_type": "movie"},
            {"title": "Blade Runner 2049", "artist": None, "album": None},
        ),
        (
            "film reported as generic video",
            {
                "media_title": "Blade Runner 2049",
                "media_content_type": "video",
                "app_name": "Jellyfin",
            },
            {"title": "Blade Runner 2049", "artist": "Jellyfin", "album": None},
        ),
        (
            "episode shows the series, never the episode title",
            {
                "media_title": "Ozymandias",
                "media_series_title": "Breaking Bad",
                "media_season": 5,
                "media_episode": 14,
                "media_content_type": "episode",
                "app_name": "Plex",
            },
            {"title": "Breaking Bad", "artist": "Plex", "album": None},
        ),
        (
            "episode with a series title but no app name",
            {
                "media_title": "Ozymandias",
                "media_series_title": "Breaking Bad",
                "media_content_type": "tvshow",
            },
            {"title": "Breaking Bad", "artist": None, "album": None},
        ),
        (
            "tvshow content type with no series title falls back to the title",
            {"media_title": "Episode 3", "media_content_type": "tvshow"},
            {"title": "Episode 3", "artist": None, "album": None},
        ),
        (
            "series title alone is enough, whatever the content type says",
            {
                "media_title": "Ozymandias",
                "media_series_title": "Breaking Bad",
                "media_content_type": "video",
                "app_name": "Netflix",
            },
            {"title": "Breaking Bad", "artist": "Netflix", "album": None},
        ),
        (
            "music is mapped exactly as it always was",
            {
                "media_title": "Bohemian Rhapsody",
                "media_artist": "Queen",
                "media_album_name": "A Night at the Opera",
                "media_content_type": "music",
            },
            {
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
            },
        ),
        (
            "music without a content type is still music",
            {
                "media_title": "Bohemian Rhapsody",
                "media_artist": "Queen",
                "media_album_name": "A Night at the Opera",
            },
            {
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "A Night at the Opera",
            },
        ),
        (
            "unknown content type gives the title and nothing else",
            {"media_title": "Some Stream", "media_content_type": "channel"},
            {"title": "Some Stream", "artist": None, "album": None},
        ),
        (
            "no attributes at all",
            {},
            {"title": None, "artist": None, "album": None},
        ),
        (
            "blank strings are not banner text",
            {
                "media_title": "The Bear",
                "media_series_title": "   ",
                "media_content_type": "tvshow",
                "app_name": "",
            },
            {"title": "The Bear", "artist": None, "album": None},
        ),
        (
            "content type casing does not matter",
            {
                "media_title": "Arrival",
                "media_content_type": "Movie",
                "app_name": "Kodi",
            },
            {"title": "Arrival", "artist": "Kodi", "album": None},
        ),
    ],
)
def test_describe(case, attrs, expected):
    assert _describe(attrs) == expected, case


def test_describe_does_not_invent_series_info_for_an_app_only_episode():
    """The Apple TV case: an episode arrives as bare title + "video".

    There is genuinely no series name in the state, so the only honest thing
    to put on the wall is the title the player gave us. Reconstructing a
    series name out of it would be a guess.
    """
    described = _describe(
        {
            "media_title": "Stranger Things: Chapter One",
            "media_content_type": "video",
            "app_name": "Netflix",
        }
    )
    assert described == {
        "title": "Stranger Things: Chapter One",
        "artist": "Netflix",
        "album": None,
    }


def test_describe_prefers_series_over_a_stray_artist():
    """Some video players put a channel or director in media_artist."""
    described = _describe(
        {
            "media_title": "Ozymandias",
            "media_series_title": "Breaking Bad",
            "media_artist": "Rian Johnson",
            "app_name": "Plex",
        }
    )
    assert described["title"] == "Breaking Bad"
    assert described["artist"] == "Plex"


# ---------------------------------------------------------------------------
# Reporting and dedup
# ---------------------------------------------------------------------------


async def test_report_posts_state_and_metadata(hass: HomeAssistant, reporter):
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"\xff\xd8\xffart")):
        await reporter.async_report()

    reporter._coordinator.client.post_now_playing.assert_awaited_once_with(
        TOKEN,
        "playing",
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        entity_id=SOURCE,
        image=b"\xff\xd8\xffart",
        clear_artwork=False,
    )


async def test_report_does_nothing_without_token(hass: HomeAssistant, reporter):
    hass.config_entries.async_update_entry(
        reporter._entry, options={CONF_NOW_PLAYING_SOURCE: SOURCE}
    )
    _playing(hass)
    await reporter.async_report()
    reporter._coordinator.client.post_now_playing.assert_not_awaited()


async def test_report_does_nothing_without_source(hass: HomeAssistant, reporter):
    hass.config_entries.async_update_entry(
        reporter._entry, options={CONF_NOW_PLAYING_TOKEN: TOKEN}
    )
    _playing(hass)
    await reporter.async_report()
    reporter._coordinator.client.post_now_playing.assert_not_awaited()


async def test_position_tick_does_not_repost(hass: HomeAssistant, reporter):
    """The whole point of the fingerprint: position updates are not track changes."""
    _playing(hass, media_position=10)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
    assert reporter._coordinator.client.post_now_playing.await_count == 1

    for position in (11, 12, 13, 14):
        _playing(hass, media_position=position, media_position_updated_at="now")
        await reporter.async_report()

    assert reporter._coordinator.client.post_now_playing.await_count == 1


async def test_track_change_reposts(hass: HomeAssistant, reporter):
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art1")):
        await reporter.async_report()
        _playing(
            hass,
            media_title="Under Pressure",
            media_content_id="track-2",
            entity_picture="https://example.com/cover2.jpg",
        )
        await reporter.async_report()

    assert reporter._coordinator.client.post_now_playing.await_count == 2
    second = reporter._coordinator.client.post_now_playing.await_args_list[1]
    assert second.args[1] == "playing"
    assert second.kwargs["title"] == "Under Pressure"


def _watching(hass, **overrides):
    """A television episode playing, in the shape Plex or Kodi reports one."""
    attrs = {
        "entity_picture": "https://example.com/s05e14.jpg",
        "media_title": "Ozymandias",
        "media_series_title": "Breaking Bad",
        "media_season": 5,
        "media_episode": 14,
        "media_content_type": "episode",
        "media_content_id": "episode-514",
        "app_name": "Plex",
    }
    attrs.update(overrides)
    hass.states.async_set(SOURCE, "playing", attrs)


async def test_report_posts_series_name_and_app_for_an_episode(
    hass: HomeAssistant, reporter
):
    _watching(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()

    reporter._coordinator.client.post_now_playing.assert_awaited_once_with(
        TOKEN,
        "playing",
        title="Breaking Bad",
        artist="Plex",
        album=None,
        entity_id=SOURCE,
        image=b"art",
        clear_artwork=False,
    )


async def test_report_posts_title_and_app_for_a_film(hass: HomeAssistant, reporter):
    hass.states.async_set(
        SOURCE,
        "playing",
        {
            "entity_picture": "https://example.com/poster.jpg",
            "media_title": "Blade Runner 2049",
            "media_content_type": "movie",
            "media_content_id": "movie-1",
            "app_name": "Jellyfin",
        },
    )
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()

    call = reporter._coordinator.client.post_now_playing.await_args
    assert call.kwargs["title"] == "Blade Runner 2049"
    assert call.kwargs["artist"] == "Jellyfin"
    assert call.kwargs["album"] is None


async def test_next_episode_of_the_same_series_reposts(hass: HomeAssistant, reporter):
    """Same series, same app: identical banners, but a different episode.

    The banner text is deliberately the same for both, so keying dedup off it
    would leave the previous episode's still on the wall for the whole of the
    next one.
    """
    _watching(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art1")):
        await reporter.async_report()
        _watching(
            hass,
            media_title="Granite State",
            media_episode=15,
            media_content_id="episode-515",
            entity_picture="https://example.com/s05e15.jpg",
        )
        await reporter.async_report()

    assert reporter._coordinator.client.post_now_playing.await_count == 2
    second = reporter._coordinator.client.post_now_playing.await_args_list[1]
    assert second.kwargs["title"] == "Breaking Bad"
    assert second.kwargs["image"] == b"art1"


async def test_switching_app_reposts(hass: HomeAssistant, reporter):
    """app_name is stored server-side and fingerprinted, so it has to be sent."""
    _watching(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
        _watching(hass, app_name="Netflix")
        await reporter.async_report()

    assert reporter._coordinator.client.post_now_playing.await_count == 2
    assert (
        reporter._coordinator.client.post_now_playing.await_args.kwargs["artist"]
        == "Netflix"
    )


async def test_video_position_tick_still_does_not_repost(
    hass: HomeAssistant, reporter
):
    """The extra video attributes must not make the fingerprint noisy."""
    _watching(hass, media_position=10)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()

    for position in (11, 12, 13):
        _watching(hass, media_position=position, media_position_updated_at="now")
        await reporter.async_report()

    assert reporter._coordinator.client.post_now_playing.await_count == 1


async def test_pause_reposts_without_refetching_art(hass: HomeAssistant, reporter):
    """Same track, new state: the server already holds the image."""
    _playing(hass)
    download = AsyncMock(return_value=b"art")
    with patch.object(reporter, "_download", download):
        await reporter.async_report()
        hass.states.async_set(
            SOURCE, "paused", dict(hass.states.get(SOURCE).attributes)
        )
        await reporter.async_report()

    assert download.await_count == 1
    second = reporter._coordinator.client.post_now_playing.await_args_list[1]
    assert second.args[1] == "paused"
    assert second.kwargs["image"] is None


async def test_stopping_reports_off_without_image(hass: HomeAssistant, reporter):
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
    hass.states.async_set(SOURCE, "off", {})
    await reporter.async_report()

    last = reporter._coordinator.client.post_now_playing.await_args_list[-1]
    assert last.args[1] == "off"
    assert last.kwargs["image"] is None


async def test_failed_download_still_reports_state(hass: HomeAssistant, reporter):
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=None)):
        await reporter.async_report()

    call = reporter._coordinator.client.post_now_playing.await_args
    assert call.args[1] == "playing"
    assert call.kwargs["image"] is None
    # The art was never delivered, so the next attempt must try again.
    assert reporter._last_picture is None


async def test_failed_download_retries_on_next_report(hass: HomeAssistant, reporter):
    _playing(hass)
    download = AsyncMock(side_effect=[None, b"art"])
    with patch.object(reporter, "_download", download):
        await reporter.async_report()
        await reporter.async_report(force=True)

    assert download.await_count == 2


# ---------------------------------------------------------------------------
# The no-artwork signal
#
# Two things are being protected here, and they pull in opposite directions:
# a new item with no cover must clear the previous item's cover, and a repost
# of an item that is already on the wall must never clear anything.
# ---------------------------------------------------------------------------


def _artless(hass, **overrides):
    """A YouTube-on-Apple-TV shaped state: a title and no entity_picture."""
    attrs = {
        "media_title": "Some YouTube Video",
        "media_content_type": "video",
        "media_content_id": "yt-1",
        "app_name": "YouTube",
    }
    attrs.update(overrides)
    hass.states.async_set(SOURCE, "playing", attrs)


def _clear_flags(reporter) -> list[bool]:
    return [
        call.kwargs["clear_artwork"]
        for call in reporter._coordinator.client.post_now_playing.await_args_list
    ]


async def test_new_item_without_a_picture_signals_no_artwork(
    hass: HomeAssistant, reporter
):
    """The Apple TV/YouTube case: no entity_picture at all is published."""
    _artless(hass)
    await reporter.async_report()

    call = reporter._coordinator.client.post_now_playing.await_args
    assert call.kwargs["image"] is None
    assert call.kwargs["clear_artwork"] is True
    assert call.kwargs["title"] == "Some YouTube Video"


async def test_switching_to_an_artless_item_clears_the_previous_art(
    hass: HomeAssistant, reporter
):
    """The reported bug: the old cover used to stay up under the new title."""
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
    _artless(hass)
    await reporter.async_report()

    assert _clear_flags(reporter) == [False, True]


async def test_heartbeat_does_not_clear_artwork_for_an_unchanged_item(
    hass: HomeAssistant, reporter
):
    """The regression this feature must never introduce.

    A track with a cover is re-posted by the heartbeat every few minutes with
    no image, because the server already holds the bytes. If those reposts
    carried the no-artwork signal the cover would blink off, come back on the
    next real change, and blink off again — once per heartbeat, forever.
    """
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
        for _ in range(4):
            await reporter.async_report(force=True)

    flags = _clear_flags(reporter)
    assert len(flags) == 5
    assert flags == [False, False, False, False, False]


async def test_heartbeat_does_not_re_signal_for_an_unchanged_artless_item(
    hass: HomeAssistant, reporter
):
    """The same guard for the art-less case.

    The first post clears the stale cover. Every heartbeat after it is the same
    item, so it must say nothing about the artwork rather than re-clearing —
    the server would be doing needless work, and any art that arrived in the
    meantime would be thrown away.
    """
    _artless(hass)
    await reporter.async_report()
    for _ in range(4):
        await reporter.async_report(force=True)

    assert _clear_flags(reporter) == [True, False, False, False, False]


async def test_pause_repost_does_not_clear_artwork(hass: HomeAssistant, reporter):
    """A pause is the same item in a new state, not a new item."""
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
        hass.states.async_set(
            SOURCE, "paused", dict(hass.states.get(SOURCE).attributes)
        )
        await reporter.async_report()
        hass.states.async_set(
            SOURCE, "playing", dict(hass.states.get(SOURCE).attributes)
        )
        await reporter.async_report()

    assert _clear_flags(reporter) == [False, False, False]


async def test_pause_of_an_artless_item_does_not_re_signal(
    hass: HomeAssistant, reporter
):
    _artless(hass)
    await reporter.async_report()
    hass.states.async_set(SOURCE, "paused", dict(hass.states.get(SOURCE).attributes))
    await reporter.async_report()

    assert _clear_flags(reporter) == [True, False]


async def test_position_ticks_never_signal_no_artwork(hass: HomeAssistant, reporter):
    """Dedup already suppresses these, but belt and braces: no clears either."""
    _artless(hass, media_position=10)
    await reporter.async_report()
    for position in (11, 12, 13):
        _artless(hass, media_position=position, media_position_updated_at="now")
        await reporter.async_report()

    assert _clear_flags(reporter) == [True]


async def test_stopping_does_not_signal_no_artwork(hass: HomeAssistant, reporter):
    """An inactive state is not a frame override, so there is nothing to clear."""
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
    hass.states.async_set(SOURCE, "off", {})
    await reporter.async_report()

    assert _clear_flags(reporter) == [False, False]


async def test_failed_download_on_a_new_item_signals_no_artwork(
    hass: HomeAssistant, reporter
):
    """A cover we could not fetch is, to the frame, no cover at all."""
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
    _playing(hass, media_title="Under Pressure", media_content_id="track-2",
             entity_picture="https://example.com/broken.jpg")
    with patch.object(reporter, "_download", AsyncMock(return_value=None)):
        await reporter.async_report()

    assert _clear_flags(reporter) == [False, True]


async def test_failed_download_retry_on_the_same_item_does_not_re_signal(
    hass: HomeAssistant, reporter
):
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=None)):
        await reporter.async_report()
        await reporter.async_report(force=True)

    assert _clear_flags(reporter) == [True, False]


async def test_artwork_arriving_later_is_sent_without_the_signal(
    hass: HomeAssistant, reporter
):
    """A player that publishes its cover a beat late must recover cleanly."""
    _artless(hass)
    await reporter.async_report()
    _artless(hass, entity_picture="https://example.com/late.jpg")
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()

    assert _clear_flags(reporter) == [True, False]
    assert (
        reporter._coordinator.client.post_now_playing.await_args.kwargs["image"]
        == b"art"
    )


# ---------------------------------------------------------------------------
# Logging — both of these were debug-only, which is what made the bug invisible
# ---------------------------------------------------------------------------


async def test_missing_artwork_is_logged_at_info_once_per_title(
    hass: HomeAssistant, reporter, caplog
):
    caplog.set_level(logging.INFO, logger="custom_components.frameit.now_playing")
    _artless(hass)
    await reporter.async_report()
    for _ in range(3):
        await reporter.async_report(force=True)

    records = [
        r for r in caplog.records
        if r.levelno == logging.INFO and "publishes no artwork" in r.message
    ]
    assert len(records) == 1
    assert "Some YouTube Video" in records[0].getMessage()


async def test_missing_artwork_is_logged_again_for_a_different_title(
    hass: HomeAssistant, reporter, caplog
):
    caplog.set_level(logging.INFO, logger="custom_components.frameit.now_playing")
    _artless(hass)
    await reporter.async_report()
    _artless(hass, media_title="Another Video", media_content_id="yt-2")
    await reporter.async_report()

    records = [r for r in caplog.records if "publishes no artwork" in r.message]
    assert len(records) == 2


async def test_download_http_error_warns_once_per_url(
    hass: HomeAssistant, reporter, caplog
):
    caplog.set_level(logging.DEBUG, logger="custom_components.frameit.now_playing")
    patcher, _session = _patch_session(_FakeResponse(404))
    with patcher:
        for _ in range(3):
            assert await reporter._download("https://example.com/missing.jpg") is None
        assert await reporter._download("https://example.com/other.jpg") is None

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "returned HTTP 404" in r.message
    ]
    assert len(warnings) == 2
    assert "missing.jpg" in warnings[0].getMessage()
    assert "other.jpg" in warnings[1].getMessage()


async def test_connection_error_is_swallowed_and_retried(hass: HomeAssistant, reporter):
    _playing(hass)
    reporter._coordinator.client.post_now_playing = AsyncMock(
        side_effect=FrameITConnectionError("boom")
    )
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
        # Fingerprint was not committed, so the same state posts again.
        await reporter.async_report()

    assert reporter._coordinator.client.post_now_playing.await_count == 2


async def test_auth_error_stops_further_posts(hass: HomeAssistant, reporter):
    """A bad token will not fix itself; don't hammer the endpoint."""
    _playing(hass)
    reporter._coordinator.client.post_now_playing = AsyncMock(
        side_effect=FrameITAuthError("nope")
    )
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_report()
        hass.states.async_set(SOURCE, "paused", {})
        await reporter.async_report()

    assert reporter._coordinator.client.post_now_playing.await_count == 1


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


def test_heartbeat_is_inside_the_stale_window(hass: HomeAssistant, reporter):
    assert reporter.stale_seconds == 120
    assert reporter.heartbeat_seconds == 60
    assert reporter.heartbeat_seconds < reporter.stale_seconds


def test_heartbeat_follows_server_stale_setting(hass: HomeAssistant, reporter):
    reporter._coordinator.data = {"settings": {"now_playing_stale_seconds": 30}}
    assert reporter.heartbeat_seconds == 15


def test_heartbeat_falls_back_when_setting_missing(hass: HomeAssistant, reporter):
    reporter._coordinator.data = {"settings": {}}
    assert reporter.stale_seconds == 120
    reporter._coordinator.data = {"settings": {"now_playing_stale_seconds": "junk"}}
    assert reporter.stale_seconds == 120
    reporter._coordinator.data = {"settings": {"now_playing_stale_seconds": 0}}
    assert reporter.stale_seconds == 120


def test_heartbeat_has_a_floor(hass: HomeAssistant, reporter):
    reporter._coordinator.data = {"settings": {"now_playing_stale_seconds": 1}}
    assert reporter.heartbeat_seconds == 5


async def test_heartbeat_reposts_while_playing(hass: HomeAssistant, reporter):
    _playing(hass)
    with patch.object(reporter, "_download", AsyncMock(return_value=b"art")):
        await reporter.async_start()
        assert reporter._coordinator.client.post_now_playing.await_count == 1

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
        await hass.async_block_till_done()

    assert reporter._coordinator.client.post_now_playing.await_count == 2
    reporter.async_stop()


async def test_heartbeat_silent_when_nothing_is_playing(hass: HomeAssistant, reporter):
    hass.states.async_set(SOURCE, "off", {})
    await reporter.async_start()
    assert reporter._coordinator.client.post_now_playing.await_count == 1

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()

    assert reporter._coordinator.client.post_now_playing.await_count == 1
    reporter.async_stop()


async def test_stop_cancels_listener_and_heartbeat(hass: HomeAssistant, reporter):
    await reporter.async_start()
    assert reporter._unsub_state is not None
    assert reporter._unsub_heartbeat is not None
    reporter.async_stop()
    assert reporter._unsub_state is None
    assert reporter._unsub_heartbeat is None


async def test_start_is_inert_when_unconfigured(hass: HomeAssistant, reporter):
    hass.config_entries.async_update_entry(reporter._entry, options={})
    await reporter.async_start()
    assert reporter._unsub_state is None
    reporter._coordinator.client.post_now_playing.assert_not_awaited()


# ---------------------------------------------------------------------------
# Live wiring through the integration
# ---------------------------------------------------------------------------


async def test_state_change_triggers_a_post(
    hass: HomeAssistant, setup_integration, mock_client
):
    mock_client.post_now_playing.reset_mock()
    with patch.object(
        _reporter(hass), "_download", AsyncMock(return_value=b"art")
    ):
        _playing(hass)
        await hass.async_block_till_done()

    assert mock_client.post_now_playing.await_count == 1
    assert mock_client.post_now_playing.await_args.args[1] == "playing"


# ---------------------------------------------------------------------------
# Per-frame Now Playing switch
# ---------------------------------------------------------------------------


async def test_now_playing_switch_created_for_every_frame(
    hass: HomeAssistant, setup_integration
):
    assert hass.states.get("switch.living_room_now_playing") is not None
    # Bedroom has no agent, but the opt-in is a server flag, not an agent one.
    assert hass.states.get("switch.bedroom_now_playing") is not None


async def test_now_playing_switch_reflects_server_flag(
    hass: HomeAssistant, setup_integration
):
    assert hass.states.get("switch.living_room_now_playing").state == "off"
    assert hass.states.get("switch.bedroom_now_playing").state == "on"


async def test_now_playing_switch_turn_on(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.living_room_now_playing"},
        blocking=True,
    )
    mock_client.update_frame.assert_awaited_once_with(1, {"show_now_playing": True})


async def test_now_playing_switch_turn_off(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.bedroom_now_playing"},
        blocking=True,
    )
    mock_client.update_frame.assert_awaited_once_with(2, {"show_now_playing": False})


# ---------------------------------------------------------------------------
# Removed in 2.0.0
# ---------------------------------------------------------------------------


async def test_now_playing_source_text_entity_is_gone(
    hass: HomeAssistant, setup_integration
):
    assert hass.states.get("text.living_room_now_playing_source") is None


async def test_content_mode_no_longer_offers_now_playing(
    hass: HomeAssistant, setup_integration
):
    state = hass.states.get("select.living_room_content_mode")
    assert set(state.attributes["options"]) == {"pool", "pinned"}


# ---------------------------------------------------------------------------
# Artwork download
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self) -> bytes:
        return self._body


def _patch_session(response):
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    return patch(
        "custom_components.frameit.now_playing.async_get_clientsession",
        return_value=session,
    ), session


async def test_download_absolute_url(hass: HomeAssistant, reporter):
    patcher, session = _patch_session(_FakeResponse(200, b"\xff\xd8\xffjpeg"))
    with patcher:
        data = await reporter._download("https://example.com/cover.jpg")

    assert data == b"\xff\xd8\xffjpeg"
    assert session.get.call_args.args[0] == "https://example.com/cover.jpg"


async def test_download_resolves_relative_proxy_url(hass: HomeAssistant, reporter):
    """entity_picture is usually an HA-relative /api/media_player_proxy path."""
    patcher, session = _patch_session(_FakeResponse(200, b"art"))
    with (
        patcher,
        patch.object(reporter, "_ha_base_url", return_value="http://ha.local:8123"),
    ):
        data = await reporter._download("/api/media_player_proxy/media_player.atv")

    assert data == b"art"
    assert session.get.call_args.args[0] == (
        "http://ha.local:8123/api/media_player_proxy/media_player.atv"
    )


async def test_download_returns_none_on_http_error(hass: HomeAssistant, reporter):
    patcher, _session = _patch_session(_FakeResponse(404))
    with patcher:
        assert await reporter._download("https://example.com/missing.jpg") is None


async def test_download_returns_none_on_exception(hass: HomeAssistant, reporter):
    session = MagicMock()
    session.get = MagicMock(side_effect=RuntimeError("boom"))
    with patch(
        "custom_components.frameit.now_playing.async_get_clientsession",
        return_value=session,
    ):
        assert await reporter._download("https://example.com/cover.jpg") is None


async def test_ha_base_url_falls_back_when_unavailable(hass: HomeAssistant, reporter):
    from homeassistant.helpers.network import NoURLAvailableError

    with patch(
        "custom_components.frameit.now_playing.get_url",
        side_effect=NoURLAvailableError,
    ):
        assert reporter._ha_base_url() == "http://localhost:8123"
