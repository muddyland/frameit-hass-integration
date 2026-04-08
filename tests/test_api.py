"""Tests for the FrameIT API client.

Uses AsyncMock to stub the aiohttp session — no real HTTP connections are
made, so there are no background threads that would trip the HA cleanup checker.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from custom_components.frameit.api import (
    FrameITApiClient,
    FrameITAuthError,
    FrameITConnectionError,
)
from tests.conftest import (
    MOCK_DISPLAY_ON,
    MOCK_FRAMES,
    MOCK_SYSTEM_INFO,
    MOCK_URL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(status: int = 200, json_data=None) -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data if json_data is not None else {})
    return resp


def make_session(**overrides) -> MagicMock:
    """Build a mock aiohttp.ClientSession with sensible defaults."""
    session = MagicMock()
    session.closed = False
    session.close = AsyncMock()
    session.post = AsyncMock(return_value=make_response(302))
    session.get = AsyncMock(return_value=make_response(200, MOCK_FRAMES))
    session.request = AsyncMock(return_value=make_response(200, MOCK_FRAMES))
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


@pytest.fixture
def client():
    """FrameITApiClient with a mocked aiohttp.ClientSession pre-injected."""
    c = FrameITApiClient(MOCK_URL, "admin", "secret")
    return c


# ---------------------------------------------------------------------------
# login()
# ---------------------------------------------------------------------------


async def test_login_success(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
    # Logged in and verified — no exception raised


async def test_login_invalid_credentials(client):
    """Verification GET returns 302 → treat as bad credentials."""
    session = make_session(
        get=AsyncMock(return_value=make_response(302)),
    )
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        with pytest.raises(FrameITAuthError):
            await client.login()


async def test_login_connection_error(client):
    session = make_session(
        post=AsyncMock(side_effect=aiohttp.ClientConnectionError()),
    )
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        with pytest.raises(FrameITConnectionError):
            await client.login()


# ---------------------------------------------------------------------------
# get_frames()
# ---------------------------------------------------------------------------


async def test_get_frames(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, MOCK_FRAMES)
        frames = await client.get_frames()

    assert len(frames) == 2
    assert frames[0]["name"] == "Living Room"
    assert frames[1]["name"] == "Bedroom"


async def test_get_frames_reauth_on_302(client):
    """A 302 on a request triggers re-login, then retries successfully."""
    session = make_session()
    # First request: 302 (session expired); after re-login: 200
    session.request.side_effect = [
        make_response(302),           # first attempt → expired
        make_response(200, MOCK_FRAMES),  # retry after re-login
    ]
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        frames = await client.get_frames()

    assert len(frames) == 2


async def test_get_frames_connection_error(client):
    session = make_session(
        request=AsyncMock(side_effect=aiohttp.ClientConnectionError()),
    )
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        with pytest.raises(FrameITConnectionError):
            await client.get_frames()


# ---------------------------------------------------------------------------
# Agent calls
# ---------------------------------------------------------------------------


async def test_get_system_info(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, MOCK_SYSTEM_INFO)
        info = await client.get_system_info(1)

    assert info["cpu_percent"] == 15.2
    assert info["cpu_temp"] == 52.3


async def test_get_system_info_agent_unreachable(client):
    """Returns None rather than raising when the agent is offline."""
    session = make_session(
        request=AsyncMock(side_effect=aiohttp.ServerTimeoutError()),
    )
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        # Reset to timeout after login succeeds
        session.request.side_effect = aiohttp.ServerTimeoutError()
        info = await client.get_system_info(1)

    assert info is None


async def test_get_display_on(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, MOCK_DISPLAY_ON)
        display = await client.get_display(1)

    assert display["on"] is True


async def test_set_display_on(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, {"ok": True})
        await client.set_display(1, on=True)

    # Verify the correct URL was called
    call_args = session.request.call_args
    assert "display/on" in call_args.args[1]


async def test_set_display_off(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, {"ok": True})
        await client.set_display(1, on=False)

    call_args = session.request.call_args
    assert "display/off" in call_args.args[1]


async def test_send_command_next(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, {"ok": True})
        await client.send_command(1, "next")

    call_kwargs = session.request.call_args.kwargs
    assert call_kwargs["json"] == {"command": "next"}


async def test_send_command_refresh(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, {"ok": True})
        await client.send_command(1, "refresh")

    call_kwargs = session.request.call_args.kwargs
    assert call_kwargs["json"] == {"command": "refresh"}


async def test_reboot(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, {"message": "Rebooting"})
        await client.reboot(1)

    call_args = session.request.call_args
    assert "system/reboot" in call_args.args[1]
