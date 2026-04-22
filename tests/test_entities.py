"""Integration tests — verifies entity states and actions after full setup."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frameit.const import DOMAIN
from tests.conftest import (
    MOCK_DISPLAY_OFF,
    MOCK_PASSWORD,
    MOCK_SERVER_VERSION_NEW,
    MOCK_URL,
    MOCK_USERNAME,
    mock_client,          # re-export so pytest sees it as a fixture
    mock_coordinator_data,
)

# ---------------------------------------------------------------------------
# Fixture — sets up a config entry and loads all platforms
# ---------------------------------------------------------------------------


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_client, mock_coordinator_data):
    """Load the FrameIT integration with mocked API and coordinator data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        entry_id="test_frameit_entry",
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
# Sensor
# ---------------------------------------------------------------------------


async def test_sensor_cpu(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.living_room_cpu")
    assert state is not None
    assert float(state.state) == pytest.approx(15.2)
    assert state.attributes["unit_of_measurement"] == "%"


async def test_sensor_ram(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.living_room_ram")
    assert state is not None
    assert float(state.state) == pytest.approx(42.0)


async def test_sensor_disk(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.living_room_disk")
    assert state is not None
    assert float(state.state) == pytest.approx(61.0)


async def test_sensor_cpu_temp(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.living_room_cpu_temperature")
    assert state is not None
    assert float(state.state) == pytest.approx(52.3)
    assert state.attributes["unit_of_measurement"] == "°C"


async def test_sensor_not_created_for_agentless_frame(hass: HomeAssistant, setup_integration):
    """The Bedroom frame has no agent — no sensor entities should exist for it."""
    assert hass.states.get("sensor.bedroom_cpu") is None
    assert hass.states.get("sensor.bedroom_ram") is None


# ---------------------------------------------------------------------------
# Switch (display)
# ---------------------------------------------------------------------------


async def test_display_switch_on(hass: HomeAssistant, setup_integration):
    state = hass.states.get("switch.living_room_display")
    assert state is not None
    assert state.state == STATE_ON


async def test_display_switch_turn_off(hass: HomeAssistant, setup_integration, mock_client):
    await hass.services.async_call(
        "switch", "turn_off",
        {"entity_id": "switch.living_room_display"},
        blocking=True,
    )
    mock_client.set_display.assert_awaited_once_with(1, on=False)


async def test_display_switch_turn_on(hass: HomeAssistant, setup_integration, mock_client):
    # Start with display off
    mock_client.get_display.return_value = MOCK_DISPLAY_OFF
    await hass.services.async_call(
        "switch", "turn_on",
        {"entity_id": "switch.living_room_display"},
        blocking=True,
    )
    mock_client.set_display.assert_awaited_once_with(1, on=True)


async def test_display_switch_not_created_for_agentless_frame(
    hass: HomeAssistant, setup_integration
):
    assert hass.states.get("switch.bedroom_display") is None


# ---------------------------------------------------------------------------
# Button
# ---------------------------------------------------------------------------


async def test_button_next_exists_for_all_frames(hass: HomeAssistant, setup_integration):
    """Next button should exist even for frames without an agent."""
    assert hass.states.get("button.living_room_next") is not None
    assert hass.states.get("button.bedroom_next") is not None


async def test_button_next_sends_command(hass: HomeAssistant, setup_integration, mock_client):
    await hass.services.async_call(
        "button", "press",
        {"entity_id": "button.living_room_next"},
        blocking=True,
    )
    mock_client.send_command.assert_awaited_once_with(1, "next")


async def test_button_refresh_sends_command(hass: HomeAssistant, setup_integration, mock_client):
    await hass.services.async_call(
        "button", "press",
        {"entity_id": "button.living_room_refresh"},
        blocking=True,
    )
    mock_client.send_command.assert_awaited_once_with(1, "refresh")


async def test_button_reboot_only_for_agent_frames(hass: HomeAssistant, setup_integration):
    assert hass.states.get("button.living_room_reboot") is not None
    assert hass.states.get("button.bedroom_reboot") is None


async def test_button_reboot_calls_api(hass: HomeAssistant, setup_integration, mock_client):
    await hass.services.async_call(
        "button", "press",
        {"entity_id": "button.living_room_reboot"},
        blocking=True,
    )
    mock_client.reboot.assert_awaited_once_with(1)


# ---------------------------------------------------------------------------
# Select (content mode)
# ---------------------------------------------------------------------------


async def test_select_content_mode_pool(hass: HomeAssistant, setup_integration):
    state = hass.states.get("select.living_room_content_mode")
    assert state is not None
    assert state.state == "pool"


async def test_select_content_mode_pinned(hass: HomeAssistant, setup_integration):
    state = hass.states.get("select.bedroom_content_mode")
    assert state is not None
    assert state.state == "pinned"


async def test_select_content_mode_options(hass: HomeAssistant, setup_integration):
    state = hass.states.get("select.living_room_content_mode")
    assert set(state.attributes["options"]) == {"pool", "pinned", "now-playing"}


async def test_select_content_mode_change(hass: HomeAssistant, setup_integration, mock_client):
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.living_room_content_mode", "option": "pinned"},
        blocking=True,
    )
    mock_client.update_frame.assert_awaited_once_with(1, {"content_mode": "pinned"})


# ---------------------------------------------------------------------------
# Update entity
# ---------------------------------------------------------------------------


async def test_update_entity_no_update(hass: HomeAssistant, setup_integration):
    """State is off when installed version matches the server version."""
    state = hass.states.get("update.living_room_agent")
    assert state is not None
    assert state.state == "off"
    assert state.attributes["installed_version"] == "abc123def456"
    assert state.attributes["latest_version"] == "abc123def456"


async def test_update_entity_update_available(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    """State is on when the server has a newer version."""
    mock_coordinator_data["server_agent_version"] = MOCK_SERVER_VERSION_NEW
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        entry_id="test_frameit_update",
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

    state = hass.states.get("update.living_room_agent")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["installed_version"] == "abc123def456"
    assert state.attributes["latest_version"] == MOCK_SERVER_VERSION_NEW


async def test_update_entity_install(
    hass: HomeAssistant, mock_client, mock_coordinator_data
):
    """Calling update.install triggers agent update — requires an update to be available."""
    mock_coordinator_data["server_agent_version"] = MOCK_SERVER_VERSION_NEW
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        entry_id="test_frameit_install",
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

    await hass.services.async_call(
        "update", "install",
        {"entity_id": "update.living_room_agent"},
        blocking=True,
    )
    mock_client.trigger_agent_update.assert_awaited_once_with(1)


async def test_update_entity_not_created_for_agentless_frame(
    hass: HomeAssistant, setup_integration
):
    """Bedroom has no agent — no update entity should be created."""
    assert hass.states.get("update.bedroom_agent") is None


# ---------------------------------------------------------------------------
# Unload
# ---------------------------------------------------------------------------


async def test_unload_entry(hass: HomeAssistant, setup_integration, mock_client):
    entry = setup_integration
    assert await hass.config_entries.async_unload(entry.entry_id)
    mock_client.close.assert_awaited_once()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
