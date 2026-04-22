"""Tests for now-playing mode — manager, select entity, and text entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frameit.const import DOMAIN, CONTENT_MODE_NOW_PLAYING
from custom_components.frameit.now_playing import NowPlayingManager
from tests.conftest import (
    MOCK_FRAMES,
    MOCK_PASSWORD,
    MOCK_URL,
    MOCK_USERNAME,
    mock_client,
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


def _manager(hass, entry_id="test_frameit_entry") -> NowPlayingManager:
    return hass.data[DOMAIN][entry_id]["now_playing"]


# ---------------------------------------------------------------------------
# Select entity — now-playing option
# ---------------------------------------------------------------------------


async def test_content_mode_includes_now_playing(hass: HomeAssistant, setup_integration):
    state = hass.states.get("select.living_room_content_mode")
    assert CONTENT_MODE_NOW_PLAYING in state.attributes["options"]


async def test_select_shows_server_mode_by_default(hass: HomeAssistant, setup_integration):
    # Manager not active → select reflects server mode ("pool")
    state = hass.states.get("select.living_room_content_mode")
    assert state.state == "pool"


async def test_select_shows_now_playing_when_manager_active(
    hass: HomeAssistant, setup_integration, mock_coordinator_data
):
    mgr = _manager(hass)
    mgr._config[1] = {"active": True, "source": "media_player.apple_tv"}
    # Trigger coordinator listeners so entities re-evaluate their properties
    coordinator = hass.data[DOMAIN]["test_frameit_entry"]["coordinator"]
    coordinator.async_set_updated_data(mock_coordinator_data)
    await hass.async_block_till_done()
    state = hass.states.get("select.living_room_content_mode")
    assert state.state == CONTENT_MODE_NOW_PLAYING


async def test_select_now_playing_calls_enable(
    hass: HomeAssistant, setup_integration
):
    mgr = _manager(hass)
    mgr.enable = AsyncMock()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.living_room_content_mode", "option": "now-playing"},
        blocking=True,
    )
    mgr.enable.assert_awaited_once_with(1)


async def test_select_pool_calls_disable_when_now_playing_active(
    hass: HomeAssistant, setup_integration, mock_client
):
    mgr = _manager(hass)
    mgr._config[1] = {"active": True, "source": "media_player.apple_tv"}
    mgr.disable = AsyncMock()

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.living_room_content_mode", "option": "pool"},
        blocking=True,
    )
    mgr.disable.assert_awaited_once_with(1)


async def test_select_pool_updates_frame_when_not_now_playing(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.living_room_content_mode", "option": "pinned"},
        blocking=True,
    )
    mock_client.update_frame.assert_awaited_once_with(1, {"content_mode": "pinned"})


# ---------------------------------------------------------------------------
# Text entity — now-playing source
# ---------------------------------------------------------------------------


async def test_now_playing_source_entity_created(hass: HomeAssistant, setup_integration):
    assert hass.states.get("text.living_room_now_playing_source") is not None
    assert hass.states.get("text.bedroom_now_playing_source") is not None


async def test_now_playing_source_empty_by_default(hass: HomeAssistant, setup_integration):
    state = hass.states.get("text.living_room_now_playing_source")
    assert state.state == ""


async def test_now_playing_source_set_value(
    hass: HomeAssistant, setup_integration
):
    mgr = _manager(hass)
    await hass.services.async_call(
        "text",
        "set_value",
        {
            "entity_id": "text.living_room_now_playing_source",
            "value": "media_player.apple_tv",
        },
        blocking=True,
    )
    assert mgr.get_source(1) == "media_player.apple_tv"


async def test_now_playing_source_reflects_manager(
    hass: HomeAssistant, setup_integration, mock_coordinator_data
):
    mgr = _manager(hass)
    mgr._config[1] = {"source": "media_player.theater_atv", "active": False}
    coordinator = hass.data[DOMAIN]["test_frameit_entry"]["coordinator"]
    coordinator.async_set_updated_data(mock_coordinator_data)
    await hass.async_block_till_done()
    state = hass.states.get("text.living_room_now_playing_source")
    assert state.state == "media_player.theater_atv"


# ---------------------------------------------------------------------------
# NowPlayingManager unit tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mgr(hass):
    """A NowPlayingManager with a mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {"frames": MOCK_FRAMES}
    coordinator.client = MagicMock()
    coordinator.client.upload_poster = AsyncMock(return_value={"id": 99, "url": "/images/np.jpg"})
    coordinator.client.delete_poster = AsyncMock()
    coordinator.client.update_frame = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        entry_id="mgr_test_entry",
    )
    return NowPlayingManager(hass, entry, coordinator)


async def test_manager_enable_subscribes_and_pushes(hass: HomeAssistant, mgr):
    mgr._config[1] = {"source": "media_player.atv", "active": False}
    mgr._push = AsyncMock()
    await mgr.enable(1)
    assert mgr.is_active(1)
    assert 1 in mgr._unsubs
    mgr._push.assert_awaited_once_with(1)


async def test_manager_disable_cleans_up(hass: HomeAssistant, mgr):
    mgr._config[1] = {"source": "media_player.atv", "active": True, "poster_id": 42}
    mgr._subscribe(1, "media_player.atv")
    assert 1 in mgr._unsubs

    await mgr.disable(1)

    assert not mgr.is_active(1)
    assert 1 not in mgr._unsubs
    mgr._coordinator.client.delete_poster.assert_awaited_once_with(42)
    mgr._coordinator.client.update_frame.assert_awaited_once_with(
        1, {"content_mode": "pool"}
    )


async def test_manager_push_uploads_and_pins(hass: HomeAssistant, mgr):
    mgr._config[1] = {"source": "media_player.atv", "active": True}

    # Simulate Apple TV playing with an entity picture
    hass.states.async_set(
        "media_player.atv",
        "playing",
        {"entity_picture": "https://example.com/artwork.jpg"},
    )

    with patch.object(mgr, "_download", AsyncMock(return_value=b"fake-image-data")):
        await mgr._push(1)

    mgr._coordinator.client.upload_poster.assert_awaited_once_with(
        b"fake-image-data",
        "now_playing_1.jpg",
        title_above="Now Playing",
        title_below="In Theater",
    )
    mgr._coordinator.client.update_frame.assert_awaited_once_with(
        1,
        {"content_mode": "pinned", "pinned_type": "poster", "pinned_id": 99},
    )
    assert mgr._config[1]["poster_id"] == 99


async def test_manager_push_skips_when_no_entity_picture(hass: HomeAssistant, mgr):
    mgr._config[1] = {"source": "media_player.atv", "active": True}
    hass.states.async_set("media_player.atv", "playing", {})

    await mgr._push(1)

    mgr._coordinator.client.upload_poster.assert_not_awaited()


async def test_manager_push_skips_when_source_missing(hass: HomeAssistant, mgr):
    mgr._config[1] = {"source": "media_player.nonexistent", "active": True}
    await mgr._push(1)
    mgr._coordinator.client.upload_poster.assert_not_awaited()


async def test_manager_push_deletes_old_poster_first(hass: HomeAssistant, mgr):
    mgr._config[1] = {
        "source": "media_player.atv",
        "active": True,
        "poster_id": 77,
    }
    hass.states.async_set(
        "media_player.atv", "playing", {"entity_picture": "https://example.com/art.jpg"}
    )

    with patch.object(mgr, "_download", AsyncMock(return_value=b"img")):
        await mgr._push(1)

    mgr._coordinator.client.delete_poster.assert_awaited_once_with(77)


async def test_manager_set_source_updates_config(hass: HomeAssistant, mgr):
    await mgr.set_source(1, "media_player.atv")
    assert mgr.get_source(1) == "media_player.atv"


async def test_manager_stop_removes_all_listeners(hass: HomeAssistant, mgr):
    mgr._config[1] = {"source": "media_player.atv", "active": True}
    mgr._subscribe(1, "media_player.atv")
    assert 1 in mgr._unsubs
    mgr.async_stop()
    assert not mgr._unsubs
