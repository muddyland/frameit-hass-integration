"""Tests for the FrameIT API client.

The server protects every state-changing call with a CSRF token and answers a
stale session with a redirect, a 401, or a 400 depending on the path — so most
of what is worth testing here is the handshake, not the URLs.

Uses AsyncMock to stub the aiohttp session — no real HTTP connections are
made, so there are no background threads that would trip the HA cleanup checker.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from custom_components.frameit.api import (
    CSRF_FIELD,
    CSRF_HEADER,
    MAX_TITLE_LENGTH,
    FrameITApiClient,
    FrameITApiError,
    FrameITAuthError,
    FrameITConnectionError,
    FrameITError,
    FrameITLockoutError,
    sniff_image,
)
from tests.conftest import (
    MOCK_DISPLAY_ON,
    MOCK_FRAMES,
    MOCK_SYSTEM_INFO,
    MOCK_URL,
)

FORM_TOKEN = "form-token-abc"
META_TOKEN = "meta-token-xyz"

LOGIN_PAGE = (
    '<form method="post">'
    f'<input type="hidden" name="_csrf_token" value="{FORM_TOKEN}">'
    "</form>"
)
ADMIN_PAGE = f'<head><meta name="csrf-token" content="{META_TOKEN}"></head>'

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(status: int = 200, body="") -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(
        return_value=body if isinstance(body, str) else json.dumps(body)
    )
    return resp


def login_exchange() -> list[AsyncMock]:
    """The three round trips a sign-in costs: form, post, admin page."""
    return [
        make_response(200, LOGIN_PAGE),
        make_response(302),
        make_response(200, ADMIN_PAGE),
    ]


class FakeCookieJar:
    """Just enough of aiohttp.CookieJar for the client's clear() call."""

    def __init__(self) -> None:
        self.cleared = 0

    def clear(self) -> None:
        self.cleared += 1


def router(handler=None):
    """Async side_effect that serves the login handshake and delegates the rest.

    Yields to the event loop on every call so concurrent callers actually
    interleave — without that, a mock resolves synchronously and the test
    could never observe a stampede it is meant to rule out.
    """

    async def _next(method, url, **kwargs):
        await asyncio.sleep(0)
        if url.endswith("/admin/login"):
            return make_response(200, LOGIN_PAGE) if method == "GET" else make_response(302)
        if url.endswith("/admin"):
            return make_response(200, ADMIN_PAGE)
        if handler is not None:
            return handler(method, url, **kwargs)
        return make_response(200, MOCK_FRAMES)

    return _next


def make_session(handler=None, **overrides) -> MagicMock:
    """A mock ClientSession that completes the login handshake by default."""
    session = MagicMock()
    session.closed = False
    session.close = AsyncMock()
    session.cookie_jar = FakeCookieJar()
    session.request = AsyncMock(side_effect=router(handler))
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


def patched(session):
    return patch(
        "custom_components.frameit.api.aiohttp.ClientSession", return_value=session
    )


def form_field(form, name):
    """Return the (type_options, headers, value) tuple for a named form field."""
    for field in form._fields:  # pylint: disable=protected-access
        if field[0].get("name") == name:
            return field
    raise AssertionError(f"no {name!r} field in form")


@pytest.fixture
def client():
    return FrameITApiClient(MOCK_URL, "admin", "secret")


# ---------------------------------------------------------------------------
# login()
# ---------------------------------------------------------------------------


async def test_login_posts_the_form_csrf_token(client):
    session = make_session()
    with patched(session):
        await client.login()

    login_post = session.request.await_args_list[1]
    assert login_post.args[0] == "POST"
    assert login_post.args[1].endswith("/admin/login")
    assert login_post.kwargs["data"][CSRF_FIELD] == FORM_TOKEN
    assert login_post.kwargs["data"]["username"] == "admin"


async def test_login_captures_the_post_login_token(client):
    """Signing in clears the session, so the usable token comes from /admin."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(200, {"ok": True})]
        await client.send_command(1, "next")

    assert session.request.await_args.kwargs["headers"][CSRF_HEADER] == META_TOKEN


async def test_reads_carry_no_csrf_header(client):
    session = make_session()
    with patched(session):
        await client.login()
        await client.get_frames()

    assert CSRF_HEADER not in session.request.await_args.kwargs["headers"]


async def test_login_starts_from_a_clean_cookie_jar(client):
    """A leftover cookie makes the server skip the login form entirely."""
    session = make_session()
    with patched(session):
        await client.login()

    assert session.cookie_jar.cleared == 1


async def test_login_works_without_csrf_protection(client):
    """An older server serves no token; the login must still go through."""
    session = make_session()
    session.request.side_effect = [
        make_response(200, "<form method='post'></form>"),
        make_response(302),
        make_response(200, "<html></html>"),
    ]
    with patched(session):
        await client.login()

    assert CSRF_FIELD not in session.request.await_args_list[1].kwargs["data"]
    assert client._csrf_token is None  # pylint: disable=protected-access


async def test_login_invalid_credentials(client):
    """A failed login re-renders the form with a 200 instead of redirecting."""
    session = make_session()
    session.request.side_effect = [
        make_response(200, LOGIN_PAGE),
        make_response(200, "Invalid username or password."),
    ]
    with patched(session):
        with pytest.raises(FrameITAuthError):
            await client.login()


async def test_login_rejects_a_session_it_cannot_use(client):
    """Signed in but /admin still bounces us — treat it as an auth failure."""
    session = make_session()
    session.request.side_effect = [*login_exchange()[:2], make_response(302)]
    with patched(session):
        with pytest.raises(FrameITAuthError):
            await client.login()


async def test_login_reports_a_csrf_handshake_failure_distinctly(client):
    session = make_session()
    session.request.side_effect = [
        make_response(200, LOGIN_PAGE),
        make_response(400, {"error": "CSRF token missing or invalid."}),
    ]
    with patched(session):
        with pytest.raises(FrameITAuthError, match="CSRF"):
            await client.login()


async def test_login_throttled(client):
    """The server locks out after repeated failures; back off instead of retrying."""
    session = make_session()
    session.request.side_effect = [
        make_response(200, LOGIN_PAGE),
        make_response(429, "Too many failed attempts."),
    ]
    with patched(session):
        with pytest.raises(FrameITLockoutError):
            await client.login()

        # The backoff holds without touching the network again.
        session.request.side_effect = AssertionError("must not retry while locked out")
        with pytest.raises(FrameITLockoutError):
            await client.login()


async def test_login_connection_error(client):
    session = make_session()
    session.request.side_effect = aiohttp.ClientConnectionError()
    with patched(session):
        with pytest.raises(FrameITConnectionError):
            await client.login()


# ---------------------------------------------------------------------------
# Reads and session recovery
# ---------------------------------------------------------------------------


async def test_get_frames(client):
    session = make_session()
    with patched(session):
        await client.login()
        frames = await client.get_frames()

    assert len(frames) == 2
    assert frames[0]["name"] == "Living Room"
    assert frames[1]["name"] == "Bedroom"


@pytest.mark.parametrize("status", [302, 401, 403])
async def test_read_reauthenticates_on_a_dead_session(client, status):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [
            make_response(status),
            *login_exchange(),
            make_response(200, MOCK_FRAMES),
        ]
        frames = await client.get_frames()

    assert len(frames) == 2


async def test_rejected_csrf_token_reauthenticates(client):
    """A stale token comes back as a 400, which means the same as a 401."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [
            make_response(400, {"error": "CSRF token missing or invalid."}),
            *login_exchange(),
            make_response(200, {"ok": True}),
        ]
        await client.send_command(1, "next")

    # 3 for the first login, 1 rejected write, 3 to sign in again, 1 retry.
    assert session.request.await_count == 8


async def test_validation_error_is_not_mistaken_for_a_dead_session(client):
    """An ordinary 400 must surface, not trigger a pointless re-login."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [
            make_response(400, {"error": "'rotation' must be one of: 0, 90, 180, 270"})
        ]
        with pytest.raises(FrameITApiError) as excinfo:
            await client.update_frame(1, {"rotation": 45})

    assert "rotation" in excinfo.value.message
    assert excinfo.value.status == 400
    assert session.request.await_count == 4  # login, then the one rejected write


async def test_concurrent_failures_only_log_in_once(client):
    """Parallel agent polls all seeing a dead session must not stampede.

    Failed logins are throttled server-side, so a re-login per in-flight call
    is a good way to lock Home Assistant out of its own server.
    """
    expired = {"remaining": 4}

    def handler(_method, _url, **_kwargs):
        if expired["remaining"]:
            expired["remaining"] -= 1
            return make_response(401, {"error": "Unauthorized"})
        return make_response(200, MOCK_FRAMES)

    session = make_session(handler)
    with patched(session):
        await client.login()

        logins = 0
        original = client._login_locked  # pylint: disable=protected-access

        async def counting_login():
            nonlocal logins
            logins += 1
            await original()

        with patch.object(client, "_login_locked", counting_login):
            results = await asyncio.gather(*[client.get_frames() for _ in range(4)])

    assert logins == 1
    assert all(len(r) == 2 for r in results)


@pytest.mark.parametrize("status", [302, 401])
async def test_persistent_rejection_raises_rather_than_reading_empty(client, status):
    """A login page decodes to nothing — that must not look like an empty fleet."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [
            make_response(status),
            *login_exchange(),
            make_response(status),
        ]
        with pytest.raises(FrameITAuthError):
            await client.get_frames()


async def test_get_frames_connection_error(client):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = aiohttp.ClientConnectionError()
        with pytest.raises(FrameITConnectionError):
            await client.get_frames()


# ---------------------------------------------------------------------------
# Agent calls
# ---------------------------------------------------------------------------


async def test_get_system_info(client):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(200, MOCK_SYSTEM_INFO)]
        info = await client.get_system_info(1)

    assert info["cpu_percent"] == 15.2
    assert info["cpu_temp"] == 52.3


async def test_get_system_info_agent_unreachable(client):
    """Returns None rather than raising when the agent is offline."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(503, {"error": "Agent unreachable"})]
        assert await client.get_system_info(1) is None


async def test_get_system_info_survives_a_timeout(client):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = aiohttp.ServerTimeoutError()
        assert await client.get_system_info(1) is None


async def test_get_display_on(client):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(200, MOCK_DISPLAY_ON)]
        display = await client.get_display(1)

    assert display["on"] is True


@pytest.mark.parametrize(
    ("on", "expected"), [(True, "display/on"), (False, "display/off")]
)
async def test_set_display(client, on, expected):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(200, {"ok": True})]
        await client.set_display(1, on=on)

    assert expected in session.request.await_args.args[1]


@pytest.mark.parametrize("command", ["next", "refresh"])
async def test_send_command(client, command):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(200, {"ok": True})]
        await client.send_command(1, command)

    assert session.request.await_args.kwargs["json"] == {"command": command}


async def test_reboot(client):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(200, {"message": "Rebooting"})]
        await client.reboot(1)

    assert "system/reboot" in session.request.await_args.args[1]


async def test_restart_service_reports_failure(client):
    """Unlike a poll, an explicit action must not fail silently."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [
            make_response(404, {"error": "Unknown agent endpoint"})
        ]
        with pytest.raises(FrameITApiError):
            await client.restart_service(1, "frameit-ui")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


async def test_update_settings(client):
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(200, {"strict_agent_auth": True})]
        result = await client.update_settings({"strict_agent_auth": True})

    assert result == {"strict_agent_auth": True}
    assert session.request.await_args.kwargs["json"] == {"strict_agent_auth": True}


# ---------------------------------------------------------------------------
# Poster upload
# ---------------------------------------------------------------------------


def test_sniff_image():
    assert sniff_image(PNG_BYTES) == ("png", "image/png")
    assert sniff_image(JPEG_BYTES) == ("jpg", "image/jpeg")
    assert sniff_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ("webp", "image/webp")
    assert sniff_image(b"not an image at all") is None


async def test_upload_poster_names_the_file_for_its_real_format(client):
    """The server checks magic bytes and extension separately."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(201, {"id": 9})]
        await client.upload_poster(PNG_BYTES, "now_playing_1.jpg")

    field = form_field(session.request.await_args.kwargs["data"], "file")
    assert field[0]["filename"] == "now_playing_1.png"
    assert field[1].get("Content-Type") == "image/png"


async def test_upload_poster_is_active(client):
    """`active` gates display, not just pool membership.

    /next resolves a pin with filter_by(id=..., active=True) and falls back to
    pool rotation when it misses, so an inactive poster can be pinned to a
    frame and simply never appear.
    """
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(201, {"id": 9})]
        await client.upload_poster(PNG_BYTES, "now_playing_1.jpg")

    field = form_field(session.request.await_args.kwargs["data"], "active")
    assert field[2] == "true"


async def test_upload_poster_truncates_long_titles(client):
    """want_str() rejects anything past 255 characters with a 400."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [make_response(201, {"id": 9})]
        await client.upload_poster(PNG_BYTES, "art.jpg", title_above="A" * 400)

    field = form_field(session.request.await_args.kwargs["data"], "title_above")
    assert len(field[2]) == MAX_TITLE_LENGTH


async def test_upload_poster_rejects_non_images(client):
    """Artwork that is really an error page never reaches the server."""
    session = make_session()
    with patched(session):
        await client.login()
        with pytest.raises(FrameITError, match="JPEG"):
            await client.upload_poster(b"<html>404</html>", "art.jpg")

    assert session.request.await_count == 3  # login only


async def test_upload_poster_rebuilds_the_form_on_retry(client):
    """A FormData body is consumed once sent, so a re-auth retry needs a new one."""
    session = make_session()
    with patched(session):
        await client.login()
        session.request.side_effect = [
            make_response(400, {"error": "CSRF token missing or invalid."}),
            *login_exchange(),
            make_response(201, {"id": 9}),
        ]
        poster = await client.upload_poster(PNG_BYTES, "art.png")

    assert poster == {"id": 9}
    first_form = session.request.await_args_list[3].kwargs["data"]
    retry_form = session.request.await_args_list[-1].kwargs["data"]
    assert first_form is not retry_form
