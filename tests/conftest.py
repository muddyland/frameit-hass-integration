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
    client.get_server_agent_version = AsyncMock(return_value=MOCK_SERVER_VERSION)
    client.trigger_agent_update = AsyncMock()
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
            }
        },
        "server_agent_version": MOCK_SERVER_VERSION,
    }
