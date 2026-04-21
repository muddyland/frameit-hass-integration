"""Tests for FrameIT media source browsing and resolution."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.media_source.models import MediaSourceItem
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frameit.const import DOMAIN
from custom_components.frameit.media_source import FrameITMediaSource
from tests.conftest import (
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


@pytest.fixture
def source(hass: HomeAssistant) -> FrameITMediaSource:
    return FrameITMediaSource(hass)


def _item(hass, identifier: str) -> MediaSourceItem:
    return MediaSourceItem(hass, DOMAIN, identifier, None)


# ---------------------------------------------------------------------------
# Browse tests
# ---------------------------------------------------------------------------


async def test_browse_root_lists_entries(hass, setup_integration, source):
    result = await source.async_browse_media(_item(hass, ""))
    assert result.title == "FrameIT"
    assert result.can_expand
    assert not result.can_play
    assert len(result.children) == 1
    assert result.children[0].identifier == "test_frameit_entry"
    assert result.children[0].title == "Living Room Frame"


async def test_browse_entry_shows_sections(hass, setup_integration, source):
    result = await source.async_browse_media(_item(hass, "test_frameit_entry"))
    assert result.title == "Living Room Frame"
    assert result.can_expand
    assert not result.can_play
    sections = {c.title: c for c in result.children}
    assert set(sections) == {"Posters", "Trailers"}
    assert sections["Posters"].identifier == "test_frameit_entry/posters"
    assert sections["Trailers"].identifier == "test_frameit_entry/trailers"


async def test_browse_posters(hass, setup_integration, mock_client, source):
    result = await source.async_browse_media(_item(hass, "test_frameit_entry/posters"))
    assert result.title == "Posters"
    assert len(result.children) == len(MOCK_POSTERS)

    first = result.children[0]
    assert first.can_play
    assert not first.can_expand
    assert first.title == "Poster One"
    assert first.thumbnail == f"{MOCK_URL}/images/poster1.jpg"
    assert first.identifier == "test_frameit_entry/posters/1"

    # title falls back to title_below when title_above is absent
    second = result.children[1]
    assert second.title == "Poster Two"


async def test_browse_trailers(hass, setup_integration, mock_client, source):
    result = await source.async_browse_media(_item(hass, "test_frameit_entry/trailers"))
    assert result.title == "Trailers"
    assert len(result.children) == len(MOCK_TRAILERS)

    cached = result.children[0]
    assert cached.can_play
    assert not cached.can_expand
    assert cached.title == "Test Trailer"
    assert cached.thumbnail == f"{MOCK_URL}/videos/dQw4w9WgXcQ.jpg"

    # Pending trailer uses external YouTube CDN thumb (already absolute)
    pending = result.children[1]
    assert pending.thumbnail == "https://i.ytimg.com/vi/xxxxxxxxxxx/hqdefault.jpg"


async def test_browse_unknown_section_raises(hass, setup_integration, source):
    with pytest.raises(ValueError, match="Unknown section"):
        await source.async_browse_media(_item(hass, "test_frameit_entry/unknown"))


# ---------------------------------------------------------------------------
# Resolve tests
# ---------------------------------------------------------------------------


async def test_resolve_poster(hass, setup_integration, mock_client, source):
    result = await source.async_resolve_media(
        _item(hass, "test_frameit_entry/posters/1")
    )
    assert result.url == f"{MOCK_URL}/images/poster1.jpg"
    assert result.mime_type == "image/jpeg"


async def test_resolve_cached_trailer(hass, setup_integration, mock_client, source):
    result = await source.async_resolve_media(
        _item(hass, "test_frameit_entry/trailers/1")
    )
    assert result.url == f"{MOCK_URL}/videos/dQw4w9WgXcQ.mp4"
    assert result.mime_type == "video/mp4"


async def test_resolve_uncached_trailer_falls_back_to_youtube(
    hass, setup_integration, mock_client, source
):
    mock_client.get_trailers = AsyncMock(
        return_value=[{**MOCK_TRAILERS[1]}]  # id=2, cached_url=None
    )
    result = await source.async_resolve_media(
        _item(hass, "test_frameit_entry/trailers/2")
    )
    assert result.url == "https://www.youtube.com/watch?v=xxxxxxxxxxx"
    assert result.mime_type == "video/youtube"


async def test_resolve_missing_poster_raises(hass, setup_integration, mock_client, source):
    with pytest.raises(ValueError, match="Poster 99 not found"):
        await source.async_resolve_media(
            _item(hass, "test_frameit_entry/posters/99")
        )


async def test_resolve_missing_trailer_raises(hass, setup_integration, mock_client, source):
    with pytest.raises(ValueError, match="Trailer 99 not found"):
        await source.async_resolve_media(
            _item(hass, "test_frameit_entry/trailers/99")
        )


async def test_resolve_bad_identifier_raises(hass, setup_integration, source):
    with pytest.raises(ValueError, match="Cannot resolve"):
        await source.async_resolve_media(_item(hass, "test_frameit_entry/posters"))
