"""Shared fixtures and constants used by all tests."""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make 'custom_components.frameit' importable — HA's loader does
# `import custom_components` and walks __path__, so the project root
# must be on sys.path before the HA instance starts.
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# Load the HA test harness (hass fixture, MockConfigEntry, etc.)
# Must be in the root conftest — pytest 7+ disallows it elsewhere.
pytest_plugins = "pytest_homeassistant_custom_component"

# ---------------------------------------------------------------------------
# Mock data — mirrors what the FrameIT server API actually returns
# ---------------------------------------------------------------------------

MOCK_URL = "http://frameit.local:5000"
MOCK_USERNAME = "admin"
MOCK_PASSWORD = "secret"

MOCK_FRAMES = [
    {
        "id": 1,
        "ip": "192.168.1.100",
        "name": "Living Room",
        "agent_url": "http://192.168.1.100:5001",
        "agent_version": "abc123def456",
        "agent_last_seen": "2024-01-01T12:00:00",
        "last_seen": "2024-01-01T12:00:00",
        "rotation": 0,
        "interval_seconds": 300,
        "content_mode": "pool",
        "pinned_type": None,
        "pinned_id": None,
        "preview": {
            "type": "poster",
            "shown_at": "2024-01-01T12:00:00",
            "thumb_url": "/images/poster1.jpg",
            "title": "Poster One",
        },
    },
    {
        "id": 2,
        "ip": "192.168.1.101",
        "name": "Bedroom",
        "agent_url": None,  # no agent registered
        "agent_version": None,
        "agent_last_seen": None,
        "last_seen": "2024-01-01T12:00:00",
        "rotation": 90,
        "interval_seconds": 60,
        "content_mode": "pinned",
        "pinned_type": "poster",
        "pinned_id": 3,
        "preview": None,
    },
]

MOCK_SYSTEM_INFO = {
    "cpu_percent": 15.2,
    "ram_percent": 42.0,
    "disk_percent": 61.0,
    "cpu_temp": 52.3,
    "hostname": "frameit-living",
    "uptime_seconds": 3600,
}

MOCK_DISPLAY_ON = {"on": True}
MOCK_DISPLAY_OFF = {"on": False}

# Same as Living Room's agent_version — no update by default
MOCK_SERVER_VERSION = "abc123def456"
# A different version used by tests that need an update to be available
MOCK_SERVER_VERSION_NEW = "999999999999"

MOCK_SERVICES = {"frameit-agent": True, "frameit-ui": True}

MOCK_POSTERS = [
    {
        "id": 1,
        "filename": "poster1.jpg",
        "url": "/images/poster1.jpg",
        "title_above": "Poster One",
        "title_below": None,
        "sort_order": 0,
        "active": True,
        "created_at": "2024-01-01T12:00:00",
    },
    {
        "id": 2,
        "filename": "poster2.jpg",
        "url": "/images/poster2.jpg",
        "title_above": None,
        "title_below": "Poster Two",
        "sort_order": 1,
        "active": True,
        "created_at": "2024-01-02T12:00:00",
    },
]

MOCK_SETTINGS = {
    "default_title_above": "Now Playing",
    "default_title_below": "",
    "default_interval_seconds": 300,
    "default_rotation": 0,
    "default_content_mode": "pool",
    "default_pinned_type": None,
    "default_pinned_id": None,
    "pool_order": "random",
    "trailer_weight_percent": None,
    "dashboard_refresh_seconds": 30,
    "log_retention_days": None,
    "default_title_above_options": (
        "Now Playing\nComing Soon\nNow in Theaters\n"
        "Get Your Tickets\nFeature Presentation\nNow Showing"
    ),
    "default_title_below_options": (
        "Now in Theaters\nOnly in Theaters\nReserve Your Seats Today\n"
        "Experience the Magic\nComing Soon to Theaters"
    ),
}

MOCK_TRAILERS = [
    {
        "id": 1,
        "youtube_id": "dQw4w9WgXcQ",
        "title": "Test Trailer",
        "active": True,
        "created_at": "2024-01-01T12:00:00",
        "cache_status": "ready",
        "cached_url": "/videos/dQw4w9WgXcQ.mp4",
        "thumb_url": "/videos/dQw4w9WgXcQ.jpg",
    },
    {
        "id": 2,
        "youtube_id": "xxxxxxxxxxx",
        "title": "Pending Trailer",
        "active": True,
        "created_at": "2024-01-02T12:00:00",
        "cache_status": "pending",
        "cached_url": None,
        "thumb_url": "https://i.ytimg.com/vi/xxxxxxxxxxx/hqdefault.jpg",
    },
]


# ---------------------------------------------------------------------------
# Shared fixture — a pre-configured mock FrameITApiClient
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    """A pre-configured mock FrameITApiClient."""
    client = MagicMock()
    client.login = AsyncMock()
    client.close = AsyncMock()
    client.get_frames = AsyncMock(return_value=MOCK_FRAMES)
    client.get_system_info = AsyncMock(return_value=MOCK_SYSTEM_INFO)
    client.get_display = AsyncMock(return_value=MOCK_DISPLAY_ON)
    client.get_services = AsyncMock(return_value=MOCK_SERVICES)
    client.get_server_agent_version = AsyncMock(return_value=MOCK_SERVER_VERSION)
    client.get_posters = AsyncMock(return_value=MOCK_POSTERS)
    client.get_trailers = AsyncMock(return_value=MOCK_TRAILERS)
    client.get_settings = AsyncMock(return_value=MOCK_SETTINGS)
    client.update_settings = AsyncMock(return_value=MOCK_SETTINGS)
    client.trigger_agent_update = AsyncMock()
    client.restart_service = AsyncMock()
    client.upload_poster = AsyncMock(return_value={"id": 99, "url": "/images/now_playing_1.jpg"})
    client.delete_poster = AsyncMock()
    client.set_display = AsyncMock()
    client.send_command = AsyncMock()
    client.reboot = AsyncMock()
    client.update_frame = AsyncMock()
    client._base_url = MOCK_URL
    return client


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Clear HA's component cache so it re-scans and finds our integration."""


@pytest.fixture
def mock_coordinator_data():
    """Coordinator data dict as _async_update_data would return it."""
    return {
        "frames": MOCK_FRAMES,
        "agent_info": {
            1: {
                "system_info": MOCK_SYSTEM_INFO,
                "display": MOCK_DISPLAY_ON,
                "services": MOCK_SERVICES,
            }
        },
        "server_agent_version": MOCK_SERVER_VERSION,
        "posters": MOCK_POSTERS,
        "trailers": MOCK_TRAILERS,
        "settings": MOCK_SETTINGS,
    }
