"""Tests for service switches, IP sensor, rotation, interval, and server stats."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frameit.const import DOMAIN
from tests.conftest import (
    MOCK_PASSWORD,
    MOCK_SERVICES,
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


# ---------------------------------------------------------------------------
# Service switches
# ---------------------------------------------------------------------------


async def test_service_switches_created(hass: HomeAssistant, setup_integration):
    assert hass.states.get("switch.living_room_agent_service") is not None
    assert hass.states.get("switch.living_room_ui_service") is not None


async def test_service_switch_state_on(hass: HomeAssistant, setup_integration):
    assert hass.states.get("switch.living_room_agent_service").state == "on"
    assert hass.states.get("switch.living_room_ui_service").state == "on"


async def test_service_switch_not_created_for_agentless_frame(
    hass: HomeAssistant, setup_integration
):
    assert hass.states.get("switch.bedroom_agent_service") is None
    assert hass.states.get("switch.bedroom_ui_service") is None


async def test_service_switch_turn_on_restarts(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.living_room_agent_service"},
        blocking=True,
    )
    mock_client.restart_service.assert_awaited_once_with(1, "frameit-agent")


async def test_service_switch_turn_off_also_restarts(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.living_room_ui_service"},
        blocking=True,
    )
    mock_client.restart_service.assert_awaited_once_with(1, "frameit-ui")


# ---------------------------------------------------------------------------
# IP sensor
# ---------------------------------------------------------------------------


async def test_ip_sensor_created_for_all_frames(hass: HomeAssistant, setup_integration):
    assert hass.states.get("sensor.living_room_ip_address") is not None
    assert hass.states.get("sensor.bedroom_ip_address") is not None


async def test_ip_sensor_value(hass: HomeAssistant, setup_integration):
    assert hass.states.get("sensor.living_room_ip_address").state == "192.168.1.100"
    assert hass.states.get("sensor.bedroom_ip_address").state == "192.168.1.101"


# ---------------------------------------------------------------------------
# Rotation select
# ---------------------------------------------------------------------------


async def test_rotation_select_created(hass: HomeAssistant, setup_integration):
    assert hass.states.get("select.living_room_rotation") is not None
    assert hass.states.get("select.bedroom_rotation") is not None


async def test_rotation_select_value(hass: HomeAssistant, setup_integration):
    assert hass.states.get("select.living_room_rotation").state == "0"
    assert hass.states.get("select.bedroom_rotation").state == "90"


async def test_rotation_select_options(hass: HomeAssistant, setup_integration):
    options = hass.states.get("select.living_room_rotation").attributes["options"]
    assert options == ["0", "90", "180", "270"]


async def test_rotation_select_change(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.living_room_rotation", "option": "180"},
        blocking=True,
    )
    mock_client.update_frame.assert_awaited_once_with(1, {"rotation": 180})


# ---------------------------------------------------------------------------
# Interval number
# ---------------------------------------------------------------------------


async def test_interval_number_created(hass: HomeAssistant, setup_integration):
    assert hass.states.get("number.living_room_display_interval") is not None
    assert hass.states.get("number.bedroom_display_interval") is not None


async def test_interval_number_value(hass: HomeAssistant, setup_integration):
    assert float(hass.states.get("number.living_room_display_interval").state) == 300
    assert float(hass.states.get("number.bedroom_display_interval").state) == 60


async def test_interval_number_set(
    hass: HomeAssistant, setup_integration, mock_client
):
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.living_room_display_interval", "value": 120},
        blocking=True,
    )
    mock_client.update_frame.assert_awaited_once_with(1, {"interval_seconds": 120})


# ---------------------------------------------------------------------------
# Server stat sensors
# ---------------------------------------------------------------------------


async def test_server_sensors_created(hass: HomeAssistant, setup_integration):
    assert hass.states.get("sensor.frameit_server_frames") is not None
    assert hass.states.get("sensor.frameit_server_online_agents") is not None
    assert hass.states.get("sensor.frameit_server_posters") is not None
    assert hass.states.get("sensor.frameit_server_trailers") is not None


async def test_server_frame_count(hass: HomeAssistant, setup_integration):
    assert hass.states.get("sensor.frameit_server_frames").state == "2"


async def test_server_agent_count(hass: HomeAssistant, setup_integration):
    # Only Living Room has an agent_url
    assert hass.states.get("sensor.frameit_server_online_agents").state == "1"


async def test_server_poster_count(hass: HomeAssistant, setup_integration):
    assert hass.states.get("sensor.frameit_server_posters").state == "2"


async def test_server_trailer_count(hass: HomeAssistant, setup_integration):
    assert hass.states.get("sensor.frameit_server_trailers").state == "2"
