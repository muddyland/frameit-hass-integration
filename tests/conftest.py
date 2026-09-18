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
        "show_now_playing": False,
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
        "show_now_playing": True,
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
    "now_playing_token_set": True,
    "now_playing_stale_seconds": 120,
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
# Fake FrameIT server — models the server's CSRF rules
#
# The real server rejects any state-changing request whose endpoint is not
# machine-to-machine unless it carries the session's CSRF token, and it
# *clears the session* on a successful login, so the token that authorises
# the login POST is dead by the time the first write goes out. Mocking the
# aiohttp session with a plain AsyncMock hides both of those, which is how the
# "auth has failed" regression got through: every login test passed against a
# server that never checked anything.
# ---------------------------------------------------------------------------

LOGIN_PAGE = (
    "<!DOCTYPE html><html><body>"
    '<form method="post">'
    '<input type="hidden" name="_csrf_token" value="{token}">'
    '<input type="text" name="username">'
    '<input type="password" name="password">'
    "</form></body></html>"
)

ADMIN_PAGE = (
    "<!DOCTYPE html><html><head>"
    '<meta name="csrf-token" content="{token}">'
    "</head><body>Dashboard</body></html>"
)

CSRF_ERROR_BODY = {
    "error": "CSRF token missing or invalid. Reload the page and try again."
}

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class FakeResponse:
    """The slice of aiohttp.ClientResponse that FrameITApiClient uses."""

    def __init__(self, status: int, *, json_data=None, text: str = "") -> None:
        self.status = status
        self._json = json_data
        self._text = text

    async def json(self):
        return self._json if self._json is not None else {}

    async def text(self):
        return self._text


class FakeFrameITServer:
    """A stand-in aiohttp.ClientSession backed by FrameIT's real auth rules.

    Pass ``enforce_csrf=False`` to model a server from before the hardening
    commit, and set ``reject_csrf=True`` to model a session whose token has
    gone stale underneath the client.
    """

    def __init__(
        self,
        *,
        username: str = MOCK_USERNAME,
        password: str = MOCK_PASSWORD,
        enforce_csrf: bool = True,
        serve_login_token: bool = True,
    ) -> None:
        self.username = username
        self.password = password
        self.enforce_csrf = enforce_csrf
        self.serve_login_token = serve_login_token
        self.reject_csrf = False

        self.closed = False
        self.signed_in = False
        self.csrf: str | None = None
        self._minted = 0

        # Call log: (method, path, csrf_token_sent)
        self.calls: list[tuple[str, str, str | None]] = []
        self.login_posts = 0
        self.csrf_rejections = 0
        # Canned JSON for non-auth paths: {(METHOD, path): (status, json)}
        self.routes: dict[tuple[str, str], tuple[int, object]] = {
            ("GET", "/api/frames"): (200, MOCK_FRAMES),
        }

    # -- helpers ---------------------------------------------------------

    def _mint(self) -> str:
        self._minted += 1
        self.csrf = f"csrf-token-{self._minted}"
        return self.csrf

    @staticmethod
    def _path(url: str) -> str:
        return url[len(MOCK_URL):] if url.startswith(MOCK_URL) else url

    @staticmethod
    def _sent_token(data, headers) -> str | None:
        if headers:
            for key, value in headers.items():
                if key.lower() == "x-csrf-token":
                    return value
        if isinstance(data, dict):
            return data.get("_csrf_token")
        return None

    def _csrf_ok(self, sent: str | None) -> bool:
        if not self.enforce_csrf:
            return True
        if self.reject_csrf or not self.csrf or not sent:
            return False
        return sent == self.csrf

    def _csrf_refusal(self) -> FakeResponse:
        self.csrf_rejections += 1
        return FakeResponse(400, json_data=CSRF_ERROR_BODY, text=CSRF_ERROR_BODY["error"])

    def _admin_page(self) -> FakeResponse:
        return FakeResponse(200, text=ADMIN_PAGE.format(token=self._mint()))

    # -- the aiohttp.ClientSession surface --------------------------------

    async def close(self) -> None:
        self.closed = True

    async def get(self, url, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def request(self, method, url, **kwargs):  # noqa: C901
        method = method.upper()
        path = self._path(url)
        data = kwargs.get("data")
        sent = self._sent_token(data, kwargs.get("headers"))
        self.calls.append((method, path, sent))

        if path == "/admin/login":
            return await self._handle_login(method, data, sent)

        if path == "/admin":
            if not self.signed_in:
                return FakeResponse(302, text="")
            return self._admin_page()

        if not self.signed_in:
            return FakeResponse(401, json_data={"error": "Unauthorized"})

        if method not in SAFE_METHODS and not self._csrf_ok(sent):
            return self._csrf_refusal()

        status, body = self.routes.get((method, path), (200, {"ok": True}))
        return FakeResponse(status, json_data=body)

    async def _handle_login(self, method, data, sent):
        if method == "GET":
            if self.signed_in:
                # The real server redirects an authenticated GET to /admin.
                return self._admin_page()
            token = self._mint() if self.serve_login_token else None
            if token is None:
                return FakeResponse(200, text="<html><body>no token here</body></html>")
            return FakeResponse(200, text=LOGIN_PAGE.format(token=token))

        self.login_posts += 1
        if not self._csrf_ok(sent):
            # Rejected by the before_request hook — the password is never
            # even looked at, which is exactly what the bug report saw.
            return self._csrf_refusal()

        data = data or {}
        if data.get("username") != self.username or data.get("password") != self.password:
            return FakeResponse(200, text=LOGIN_PAGE.format(token=self._mint()))

        # _sign_in() calls session.clear(), so the login token dies here.
        self.signed_in = True
        self.csrf = None
        # allow_redirects=True lands us on the dashboard, which mints a new one.
        return self._admin_page()


@pytest.fixture
def fake_server():
    """A FakeFrameITServer enforcing CSRF exactly like the real one."""
    return FakeFrameITServer()


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
    client.delete_poster = AsyncMock()
    client.post_now_playing = AsyncMock(
        return_value={"ok": True, "state": "playing", "frames_signalled": 1}
    )
    client.create_now_playing_token = AsyncMock(return_value="minted-token")
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
