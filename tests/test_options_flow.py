"""Tests for the options flow — now-playing source player and webhook token."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frameit.const import (
    CONF_NOW_PLAYING_SOURCE,
    CONF_NOW_PLAYING_TOKEN,
    DOMAIN,
)
from tests.conftest import (
    MOCK_PASSWORD,
    MOCK_URL,
    MOCK_USERNAME,
    mock_client,
    mock_coordinator_data,
)

SOURCE = "media_player.apple_tv"


@pytest.fixture
async def entry(hass: HomeAssistant, mock_client, mock_coordinator_data):
    hass.states.async_set(SOURCE, "off", {})
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": MOCK_URL, "username": MOCK_USERNAME, "password": MOCK_PASSWORD},
        entry_id="options_test_entry",
    )
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.frameit.FrameITApiClient", return_value=mock_client),
        patch(
            "custom_components.frameit.coordinator.FrameITCoordinator._async_update_data",
            return_value=mock_coordinator_data,
        ),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    return config_entry


async def test_options_flow_shows_form(hass: HomeAssistant, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_saves_source_and_token(hass: HomeAssistant, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("custom_components.frameit.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_NOW_PLAYING_SOURCE: SOURCE,
                CONF_NOW_PLAYING_TOKEN: "pasted-token",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_NOW_PLAYING_SOURCE] == SOURCE
    assert entry.options[CONF_NOW_PLAYING_TOKEN] == "pasted-token"


async def test_options_flow_generates_token(
    hass: HomeAssistant, entry, mock_client
):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("custom_components.frameit.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_NOW_PLAYING_SOURCE: SOURCE,
                CONF_NOW_PLAYING_TOKEN: "",
                "generate_token": True,
            },
        )
        await hass.async_block_till_done()

    mock_client.create_now_playing_token.assert_awaited_once()
    assert entry.options[CONF_NOW_PLAYING_TOKEN] == "minted-token"


async def test_options_flow_does_not_mint_unless_asked(
    hass: HomeAssistant, entry, mock_client
):
    """Minting invalidates the token already in use, so it must be deliberate."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("custom_components.frameit.async_setup_entry", return_value=True):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_NOW_PLAYING_SOURCE: SOURCE,
                CONF_NOW_PLAYING_TOKEN: "existing-token",
                "generate_token": False,
            },
        )
        await hass.async_block_till_done()

    mock_client.create_now_playing_token.assert_not_awaited()
    assert entry.options[CONF_NOW_PLAYING_TOKEN] == "existing-token"


async def test_options_flow_reports_mint_failure(
    hass: HomeAssistant, entry, mock_client
):
    mock_client.create_now_playing_token.return_value = None
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_NOW_PLAYING_TOKEN: "", "generate_token": True},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "token_failed"}


async def test_options_flow_allows_clearing_the_source(hass: HomeAssistant, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("custom_components.frameit.async_setup_entry", return_value=True):
        await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={}
        )
        await hass.async_block_till_done()

    assert entry.options[CONF_NOW_PLAYING_SOURCE] == ""
    assert entry.options[CONF_NOW_PLAYING_TOKEN] == ""
