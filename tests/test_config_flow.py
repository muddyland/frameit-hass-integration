"""Tests for the FrameIT config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frameit.api import (
    FrameITAuthError,
    FrameITConnectionError,
    FrameITLockoutError,
)
from custom_components.frameit.const import DOMAIN
from tests.conftest import MOCK_PASSWORD, MOCK_URL, MOCK_USERNAME

USER_INPUT = {
    "url": MOCK_URL,
    "username": MOCK_USERNAME,
    "password": MOCK_PASSWORD,
}

EMPTY_DATA = {
    "frames": [],
    "agent_info": {},
    "server_agent_version": None,
    "posters": [],
    "trailers": [],
    "settings": {},
}


async def test_config_flow_shows_form(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


async def test_config_flow_success(hass: HomeAssistant):
    # Patch both the config-flow client (validation) and the __init__ client
    # (entry setup) so no real network calls are made after entry creation.
    mock_coord = AsyncMock()
    mock_coord.data = {"frames": [], "agent_info": {}}
    mock_coord.async_config_entry_first_refresh = AsyncMock()

    with patch(
        "custom_components.frameit.config_flow.FrameITApiClient"
    ) as mock_cls, patch(
        "custom_components.frameit.FrameITApiClient"
    ), patch(
        "custom_components.frameit.FrameITCoordinator", return_value=mock_coord
    ):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_URL
    assert result["data"] == USER_INPUT
    mock_client.login.assert_awaited_once()
    mock_client.close.assert_awaited_once()


async def test_config_flow_auth_error(hass: HomeAssistant):
    with patch(
        "custom_components.frameit.config_flow.FrameITApiClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.login.side_effect = FrameITAuthError("bad creds")
        mock_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_connection_error(hass: HomeAssistant):
    with patch(
        "custom_components.frameit.config_flow.FrameITApiClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.login.side_effect = FrameITConnectionError("timeout")
        mock_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_lockout(hass: HomeAssistant):
    """A server-side login lockout gets its own message, not "wrong password"."""
    with patch(
        "custom_components.frameit.config_flow.FrameITApiClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.login.side_effect = FrameITLockoutError("locked out")
        mock_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "too_many_attempts"}


# ---------------------------------------------------------------------------
# Re-authentication
#
# Changing the FrameIT admin password invalidates every other session, so an
# entry that was working can start failing without anything else changing.
# ---------------------------------------------------------------------------


def _reauth_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=USER_INPUT,
        entry_id="reauth_entry",
        unique_id=MOCK_URL,
        title=MOCK_URL,
    )
    entry.add_to_hass(hass)
    return entry


async def test_reauth_updates_the_stored_password(hass: HomeAssistant):
    entry = _reauth_entry(hass)
    mock_coord = AsyncMock()
    mock_coord.data = EMPTY_DATA
    mock_coord.async_config_entry_first_refresh = AsyncMock()

    with patch(
        "custom_components.frameit.config_flow.FrameITApiClient"
    ) as mock_cls, patch(
        "custom_components.frameit.FrameITApiClient"
    ), patch(
        "custom_components.frameit.FrameITCoordinator", return_value=mock_coord
    ):
        mock_cls.return_value = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": MOCK_USERNAME, "password": "a-new-password"},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "a-new-password"
    assert entry.data["url"] == MOCK_URL


async def test_reauth_rejects_wrong_credentials(hass: HomeAssistant):
    entry = _reauth_entry(hass)

    with patch(
        "custom_components.frameit.config_flow.FrameITApiClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.login.side_effect = FrameITAuthError("bad creds")
        mock_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": MOCK_USERNAME, "password": "still-wrong"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["password"] == MOCK_PASSWORD


async def test_config_flow_duplicate_server(hass: HomeAssistant):
    """Adding the same server URL a second time should abort."""
    mock_coord = AsyncMock()
    mock_coord.data = {"frames": [], "agent_info": {}}
    mock_coord.async_config_entry_first_refresh = AsyncMock()

    with patch(
        "custom_components.frameit.config_flow.FrameITApiClient"
    ) as mock_cls, patch(
        "custom_components.frameit.FrameITApiClient"
    ), patch(
        "custom_components.frameit.FrameITCoordinator", return_value=mock_coord
    ):
        mock_cls.return_value = AsyncMock()

        # First entry
        r1 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(r1["flow_id"], USER_INPUT)
        await hass.async_block_till_done()

        # Second entry with the same URL
        r2 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            r2["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
