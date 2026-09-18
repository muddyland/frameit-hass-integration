"""Tests for the one-time cleanup of version 1's now-playing posters.

Version 1 mirrored artwork by uploading it as an inactive poster per frame and
pinning it. Those uploads are orphaned under the new server-side fan-out, so
the first start of 2.0.0 removes them and drops the store that recorded them.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frameit.const import DOMAIN
from tests.conftest import (
    MOCK_PASSWORD,
    MOCK_POSTERS,
    MOCK_URL,
    MOCK_USERNAME,
    mock_client,
    mock_coordinator_data,
)

ENTRY_ID = "legacy_test_entry"
LEGACY_POSTERS = MOCK_POSTERS + [
    {
        "id": 51,
        "filename": "ab" * 16 + "_now_playing_1.jpg",
        "url": "/images/now_playing_1.jpg",
        "title_above": "Bohemian Rhapsody",
        "title_below": None,
        "sort_order": 9,
        "active": False,
        "created_at": "2024-01-03T12:00:00",
    },
]


async def _setup(hass, mock_client, coordinator_data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        entry_id=ENTRY_ID,
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.frameit.FrameITApiClient", return_value=mock_client),
        patch(
            "custom_components.frameit.coordinator.FrameITCoordinator._async_update_data",
            return_value=coordinator_data,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


def _legacy_store(hass) -> Store:
    return Store(hass, 1, f"{DOMAIN}.now_playing.{ENTRY_ID}")


async def test_no_store_means_no_cleanup(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    """A fresh install has nothing to clean and must not delete anything."""
    await _setup(hass, mock_client, mock_coordinator_data)
    mock_client.delete_poster.assert_not_awaited()


async def test_posters_recorded_by_v1_are_deleted(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    await _legacy_store(hass).async_save(
        {"1": {"active": True, "source": "media_player.atv", "poster_id": 42}}
    )

    await _setup(hass, mock_client, mock_coordinator_data)

    mock_client.delete_poster.assert_awaited_once_with(42)


async def test_orphans_matched_by_filename_are_deleted(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    """A crash between upload and save leaves a poster the store never recorded."""
    await _legacy_store(hass).async_save({"1": {"active": False}})
    mock_coordinator_data["posters"] = LEGACY_POSTERS

    await _setup(hass, mock_client, mock_coordinator_data)

    mock_client.delete_poster.assert_awaited_once_with(51)


async def test_ordinary_posters_are_left_alone(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    await _legacy_store(hass).async_save({"1": {"active": False}})
    mock_coordinator_data["posters"] = MOCK_POSTERS

    await _setup(hass, mock_client, mock_coordinator_data)

    mock_client.delete_poster.assert_not_awaited()


async def test_cleanup_runs_only_once(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    await _legacy_store(hass).async_save({"1": {"poster_id": 42}})
    mock_coordinator_data["posters"] = LEGACY_POSTERS

    entry = await _setup(hass, mock_client, mock_coordinator_data)
    assert mock_client.delete_poster.await_count == 2

    mock_client.delete_poster.reset_mock()
    with (
        patch("custom_components.frameit.FrameITApiClient", return_value=mock_client),
        patch(
            "custom_components.frameit.coordinator.FrameITCoordinator._async_update_data",
            return_value=mock_coordinator_data,
        ),
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    mock_client.delete_poster.assert_not_awaited()


async def test_setup_survives_a_failed_delete(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    """A poster the user already removed by hand must not block the upgrade."""
    await _legacy_store(hass).async_save({"1": {"poster_id": 42}})
    mock_client.delete_poster.side_effect = RuntimeError("404")

    entry = await _setup(hass, mock_client, mock_coordinator_data)

    assert entry.state.recoverable is False or entry.entry_id in hass.data[DOMAIN]
    assert hass.states.get("select.living_room_content_mode") is not None
