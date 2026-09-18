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
    _extract_csrf_token,
)
from tests.conftest import (
    ADMIN_PAGE,
    LOGIN_PAGE,
    MOCK_DISPLAY_ON,
    MOCK_FRAMES,
    MOCK_PASSWORD,
    MOCK_SYSTEM_INFO,
    MOCK_URL,
    MOCK_USERNAME,
    FakeFrameITServer,
)

# Token baked into the stubbed pages that make_session() serves.
STUB_CSRF = "stub-csrf-token"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(status: int = 200, json_data=None, text: str = "") -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data if json_data is not None else {})
    resp.text = AsyncMock(return_value=text)
    return resp


def make_session(**overrides) -> MagicMock:
    """Build a mock aiohttp.ClientSession with sensible defaults.

    Every GET serves a page carrying a CSRF token, because login() needs one
    from the login form and another from the signed-in dashboard.
    """
    session = MagicMock()
    session.closed = False
    session.close = AsyncMock()
    session.post = AsyncMock(
        return_value=make_response(302, text=ADMIN_PAGE.format(token=STUB_CSRF))
    )
    session.get = AsyncMock(
        return_value=make_response(
            200, MOCK_FRAMES, text=LOGIN_PAGE.format(token=STUB_CSRF)
        )
    )
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
        get=AsyncMock(
            side_effect=[
                # The login page still renders and still carries a token...
                make_response(200, text=LOGIN_PAGE.format(token=STUB_CSRF)),
                # ...but the protected endpoint bounces us.
                make_response(302),
            ]
        ),
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


# ---------------------------------------------------------------------------
# Now playing — bearer-token webhook
# ---------------------------------------------------------------------------


def _form_fields(form) -> dict:
    """Read back the field names and values staged on an aiohttp FormData."""
    return {
        opts["name"]: value
        for opts, _headers, value in form._fields  # noqa: SLF001
    }


async def test_post_now_playing_sends_bearer_token(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.post.return_value = make_response(
            200, {"ok": True, "state": "playing", "frames_signalled": 2}
        )
        result = await client.post_now_playing("tok123", "playing")

    assert result["frames_signalled"] == 2
    call = session.post.call_args
    assert call.args[0] == f"{MOCK_URL}/api/now-playing"
    assert call.kwargs["headers"] == {"Authorization": "Bearer tok123"}


async def test_post_now_playing_does_not_use_the_session_cookie_path(client):
    """The webhook authenticates by token; a 401 must not trigger a re-login."""
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.reset_mock()
        session.post.return_value = make_response(401, {"error": "bad token"})
        with pytest.raises(FrameITAuthError):
            await client.post_now_playing("wrong", "playing")

    session.request.assert_not_called()


async def test_post_now_playing_includes_metadata(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.post.return_value = make_response(200, {"ok": True})
        await client.post_now_playing(
            "tok",
            "playing",
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            entity_id="media_player.atv",
        )

    fields = _form_fields(session.post.call_args.kwargs["data"])
    assert fields["state"] == "playing"
    assert fields["title"] == "Bohemian Rhapsody"
    assert fields["artist"] == "Queen"
    assert fields["album"] == "A Night at the Opera"
    assert fields["entity_id"] == "media_player.atv"
    assert "image" not in fields


async def test_post_now_playing_omits_blank_metadata(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.post.return_value = make_response(200, {"ok": True})
        await client.post_now_playing("tok", "idle", title=None, artist="")

    fields = _form_fields(session.post.call_args.kwargs["data"])
    assert set(fields) == {"state"}


@pytest.mark.parametrize(
    ("magic", "expected_type"),
    [
        (b"\xff\xd8\xff\xe0" + b"0" * 16, "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n" + b"0" * 16, "image/png"),
        (b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 16, "image/webp"),
    ],
)
async def test_post_now_playing_sniffs_image_type(client, magic, expected_type):
    """The server sniffs magic bytes, so the declared type must match them."""
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.post.return_value = make_response(200, {"ok": True})
        await client.post_now_playing("tok", "playing", image=magic)

    form = session.post.call_args.kwargs["data"]
    headers = [h for opts, h, _v in form._fields if opts["name"] == "image"][0]  # noqa: SLF001
    assert headers["Content-Type"] == expected_type


async def test_post_now_playing_raises_on_server_error(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        bad = make_response(400)
        bad.text = AsyncMock(return_value="not a valid image")
        session.post.return_value = bad
        with pytest.raises(FrameITConnectionError, match="400"):
            await client.post_now_playing("tok", "playing", image=b"junk")


async def test_post_now_playing_wraps_client_error(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.post.side_effect = aiohttp.ClientError("down")
        with pytest.raises(FrameITConnectionError):
            await client.post_now_playing("tok", "playing")


async def test_create_now_playing_token(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(200, {"token": "abc123"})
        token = await client.create_now_playing_token()

    assert token == "abc123"
    assert "now-playing-token" in session.request.call_args.args[1]


async def test_create_now_playing_token_failure_returns_none(client):
    session = make_session()
    with patch("custom_components.frameit.api.aiohttp.ClientSession", return_value=session):
        await client.login()
        session.request.return_value = make_response(500)
        assert await client.create_now_playing_token() is None


# ---------------------------------------------------------------------------
# CSRF — against a fake server that enforces the real rules
#
# Regression cover for the "auth has failed" report: FrameIT started rejecting
# every state-changing request without a CSRF token, and the client sent none,
# so login and every write failed regardless of the password.
# ---------------------------------------------------------------------------


async def test_fake_server_rejects_a_login_post_with_no_csrf_token(fake_server):
    """Guard on the guard: the fake must actually enforce what it claims to."""
    resp = await fake_server.post(
        f"{MOCK_URL}/admin/login",
        data={"username": MOCK_USERNAME, "password": MOCK_PASSWORD},
    )
    assert resp.status == 400
    assert "CSRF" in (await resp.text())
    assert fake_server.signed_in is False


async def test_login_gets_the_login_page_then_posts_the_token(client, fake_server):
    """The whole bug in one test: no prior GET means no token means no login."""
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        await client.login()

    assert fake_server.signed_in is True
    assert fake_server.csrf_rejections == 0
    # A GET of the login page must come first...
    assert fake_server.calls[0][:2] == ("GET", "/admin/login")
    # ...and the credential POST must echo the token that GET handed out.
    login_post = next(
        call for call in fake_server.calls if call[:2] == ("POST", "/admin/login")
    )
    assert login_post[2] == "csrf-token-1"


async def test_login_raises_auth_error_when_the_token_is_rejected(client, fake_server):
    """A stale/forged token 400s before the password is ever checked."""
    fake_server.reject_csrf = True
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        with pytest.raises(FrameITAuthError):
            await client.login()

    assert fake_server.signed_in is False
    assert fake_server.csrf_rejections >= 1


async def test_login_raises_connection_error_when_the_page_has_no_token(client):
    """No hidden field: say so clearly instead of posting a None token."""
    server = FakeFrameITServer(serve_login_token=False)
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=server
    ):
        with pytest.raises(FrameITConnectionError, match="No CSRF token"):
            await client.login()

    assert server.login_posts == 0


async def test_login_survives_wrong_password_as_an_auth_error(client):
    """Correct token, wrong password — still an auth error, not a 400."""
    server = FakeFrameITServer(password="something-else")
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=server
    ):
        with pytest.raises(FrameITAuthError):
            await client.login()

    assert server.csrf_rejections == 0


async def test_login_picks_up_a_fresh_token_after_sign_in(client, fake_server):
    """The server clears the session on login, so the login token is dead."""
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        await client.login()

    assert client._csrf_token == fake_server.csrf
    assert client._csrf_token != "csrf-token-1"


async def test_writes_carry_the_csrf_token(client, fake_server):
    """PATCH /api/frames/<id> is CSRF-protected too — not just login."""
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        await client.login()
        await client.update_frame(1, {"rotation": 90})

    patch_call = next(
        call for call in fake_server.calls if call[:2] == ("PATCH", "/api/frames/1")
    )
    assert patch_call[2] == client._csrf_token
    assert fake_server.csrf_rejections == 0


async def test_create_now_playing_token_carries_the_csrf_token(client, fake_server):
    """Minting a webhook token is a POST to a non-exempt endpoint."""
    fake_server.routes[("POST", "/api/settings/now-playing-token")] = (
        200,
        {"token": "minted"},
    )
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        await client.login()
        token = await client.create_now_playing_token()

    assert token == "minted"
    assert fake_server.csrf_rejections == 0


async def test_settings_patch_carries_the_csrf_token(client, fake_server):
    fake_server.routes[("PATCH", "/api/settings")] = (200, {"pool_order": "random"})
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        await client.login()
        await client.update_settings({"pool_order": "random"})

    assert fake_server.csrf_rejections == 0


async def test_safe_requests_send_no_csrf_token(client, fake_server):
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        await client.login()
        await client.get_frames()

    get_call = next(
        call for call in fake_server.calls if call[:2] == ("GET", "/api/frames")
    )
    assert get_call[2] is None


async def test_a_write_before_login_logs_in_first(client, fake_server):
    """No token in hand yet: log in rather than burn a guaranteed 400."""
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        await client.send_command(1, "next")

    assert fake_server.signed_in is True
    assert fake_server.csrf_rejections == 0
    assert fake_server.calls[0][:2] == ("GET", "/admin/login")


async def test_a_stale_csrf_token_is_refreshed_and_the_write_retried(
    client, fake_server
):
    """A 400 is not a 401, so CSRF staleness needs its own recovery path."""
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=fake_server
    ):
        await client.login()
        # The server rotates its token underneath us (a restart, another tab).
        fake_server.csrf = "rotated-token"
        resp = await client._request("POST", "/api/frames/1/command", json={"c": "n"})

    assert resp.status == 200
    assert fake_server.csrf_rejections == 1
    assert fake_server.login_posts == 2


async def test_client_still_works_against_a_server_without_csrf(client):
    """Older FrameIT: no enforcement, and the client must not care."""
    server = FakeFrameITServer(enforce_csrf=False)
    with patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=server
    ):
        await client.login()
        frames = await client.get_frames()

    assert len(frames) == 2


# ---------------------------------------------------------------------------
# _extract_csrf_token()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<input type="hidden" name="_csrf_token" value="abc">', "abc"),
        ('<meta name="csrf-token" content="def">', "def"),
        # Attribute order must not matter.
        ('<input value="ghi" name="_csrf_token" type="hidden">', "ghi"),
        # Single quotes, as some templating setups emit.
        ("<meta name='csrf-token' content='jkl'>", "jkl"),
        # Unrelated fields must not be mistaken for the token.
        ('<input name="username" value="admin">', None),
        ("<html><body>no token here</body></html>", None),
        ('<input name="_csrf_token" value="">', None),
        ("", None),
        (None, None),
    ],
)
def test_extract_csrf_token(html, expected):
    assert _extract_csrf_token(html) == expected
