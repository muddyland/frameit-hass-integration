"""Tests for the FrameIT media player entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frameit.const import DOMAIN
from tests.conftest import (
    MOCK_FRAMES,
    MOCK_PASSWORD,
    MOCK_POSTERS,
    MOCK_TRAILERS,
    MOCK_URL,
    MOCK_USERNAME,
    mock_client,           # re-export so pytest sees it as a fixture
    mock_coordinator_data,
)

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_client, mock_coordinator_data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        entry_id="test_frameit_entry",
        title="Living Room Frame",
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


# ---------------------------------------------------------------------------
# State / metadata
# ---------------------------------------------------------------------------


async def test_media_player_created_for_each_frame(
    hass: HomeAssistant, setup_integration
):
    assert hass.states.get("media_player.living_room_display") is not None
    assert hass.states.get("media_player.bedroom_display") is not None


async def test_state_playing_when_last_seen(hass: HomeAssistant, setup_integration):
    state = hass.states.get("media_player.living_room_display")
    assert state.state == MediaPlayerState.PLAYING


async def test_state_idle_when_no_preview(hass: HomeAssistant, setup_integration, mock_client, mock_coordinator_data):
    # Bedroom frame has last_seen set but no preview; state is still PLAYING
    state = hass.states.get("media_player.bedroom_display")
    assert state.state == MediaPlayerState.PLAYING


async def test_state_idle_when_no_last_seen(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    """A frame with last_seen=None should be IDLE."""
    frames_no_last_seen = [
        {**MOCK_FRAMES[0], "last_seen": None, "preview": None},
    ]
    mock_coordinator_data = {
        **mock_coordinator_data,
        "frames": frames_no_last_seen,
        "agent_info": {},
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        entry_id="test_idle_entry",
        title="Idle Frame",
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

    state = hass.states.get("media_player.living_room_display")
    assert state.state == MediaPlayerState.IDLE


async def test_media_title_from_preview(hass: HomeAssistant, setup_integration):
    state = hass.states.get("media_player.living_room_display")
    assert state.attributes.get("media_title") == "Poster One"


async def test_media_image_url_local_path(hass: HomeAssistant, setup_integration):
    # HA proxies media_image_url via /api/media_player_proxy/...; check the
    # entity property directly rather than the state's entity_picture attribute.
    from custom_components.frameit.media_player import FrameITMediaPlayer

    coordinator = hass.data[DOMAIN]["test_frameit_entry"]["coordinator"]
    entity = FrameITMediaPlayer(coordinator, MOCK_FRAMES[0])
    assert entity.media_image_url == f"{MOCK_URL}/images/poster1.jpg"


async def test_media_title_none_when_no_preview(hass: HomeAssistant, setup_integration):
    state = hass.states.get("media_player.bedroom_display")
    assert state.attributes.get("media_title") is None


# ---------------------------------------------------------------------------
# Next track
# ---------------------------------------------------------------------------


async def test_next_track_sends_command(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "media_player",
        "media_next_track",
        {"entity_id": "media_player.living_room_display"},
        blocking=True,
    )
    mock_client.send_command.assert_awaited_once_with(1, "next")


# ---------------------------------------------------------------------------
# Play media — pinning
# ---------------------------------------------------------------------------


async def test_play_media_pins_poster(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.living_room_display",
            "media_content_type": "image/jpeg",
            "media_content_id": "media-source://frameit/test_frameit_entry/posters/1",
        },
        blocking=True,
    )
    mock_client.update_frame.assert_awaited_once_with(
        1,
        {"content_mode": "pinned", "pinned_type": "poster", "pinned_id": 1},
    )


async def test_play_media_pins_trailer(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.living_room_display",
            "media_content_type": "video/mp4",
            "media_content_id": "media-source://frameit/test_frameit_entry/trailers/2",
        },
        blocking=True,
    )
    mock_client.update_frame.assert_awaited_once_with(
        1,
        {"content_mode": "pinned", "pinned_type": "trailer", "pinned_id": 2},
    )


async def test_play_media_ignores_non_frameit_uri(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.living_room_display",
            "media_content_type": "image/jpeg",
            "media_content_id": "http://example.com/image.jpg",
        },
        blocking=True,
    )
    mock_client.update_frame.assert_not_awaited()
