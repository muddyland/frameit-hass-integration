"""Async API client for the FrameIT server."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import aiohttp
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10)
AGENT_TIMEOUT = aiohttp.ClientTimeout(total=5)

CSRF_HEADER = "X-CSRF-Token"
CSRF_FIELD = "_csrf_token"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}

# The server hands its CSRF token out in two places: a hidden field on the
# login form, needed to post the form itself, and a meta tag on every admin
# page, needed for the JSON API. Both are required — signing in clears the
# session, so the token that authorised the login dies with it.
_FORM_CSRF_RE = re.compile(r'name="_csrf_token"[^>]*?value="([^"]+)"')
_META_CSRF_RE = re.compile(r'<meta[^>]*?name="csrf-token"[^>]*?content="([^"]*)"')

# Failed logins are throttled server-side — ten per five minutes per client IP,
# then a lockout. Backing off locally stops a stale password in the config
# entry from spending that whole allowance on the polling interval.
LOCKOUT_BACKOFF_SECONDS = 300

# want_str() on the server rejects anything longer than this with a 400.
MAX_TITLE_LENGTH = 255

_IMAGE_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FrameITError(HomeAssistantError):
    """Base class for every FrameIT client failure."""


class FrameITAuthError(FrameITError):
    """Raised when authentication fails."""


class FrameITLockoutError(FrameITAuthError):
    """Raised when the server is throttling logins from this client."""


class FrameITConnectionError(FrameITError):
    """Raised when the server cannot be reached."""


class FrameITApiError(FrameITError):
    """Raised when the server answers a request with an error status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"FrameIT server returned HTTP {status}: {message}")
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sniff_image(data: bytes) -> tuple[str, str] | None:
    """Return (extension, content type) for a recognised image, else None.

    The server checks the uploaded file's magic bytes *and* its extension, so
    artwork has to be named for what is actually in the buffer.
    """
    for signature, extension, content_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return extension, content_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def _error_message(body: str) -> str:
    """Pull the human-readable reason out of an error response."""
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict) and parsed.get("error"):
        return str(parsed["error"])
    text = re.sub(r"<[^>]+>", " ", body or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:200] or "no details"


class FrameITApiClient:
    """Async HTTP client for FrameIT.

    Authenticates via the admin session cookie (form login), carries the CSRF
    token the server requires on every state-changing call, and
    re-authenticates transparently when the session expires.
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._csrf_token: str | None = None
        # Bumped on every successful sign-in. A burst of parallel calls that
        # all see a stale session compare against the generation they started
        # with, so only the first one actually logs in again.
        self._auth_generation = 0
        self._auth_lock = asyncio.Lock()
        self._lockout_until = 0.0

    @property
    def base_url(self) -> str:
        """The server's base URL, without a trailing slash."""
        return self._base_url

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> None:
        """Sign in and pick up a CSRF token for subsequent writes."""
        async with self._auth_lock:
            await self._login_locked()

    async def _reauth(self, generation: int) -> None:
        """Re-authenticate unless another caller already did it for us."""
        async with self._auth_lock:
            if generation != self._auth_generation:
                return
            await self._login_locked()

    async def _login_locked(self) -> None:
        """Perform the login handshake. Caller must hold ``_auth_lock``."""
        remaining = self._lockout_until - time.monotonic()
        if remaining > 0:
            raise FrameITLockoutError(
                f"FrameIT is throttling logins from Home Assistant; "
                f"backing off for another {int(remaining)}s"
            )

        # Start from a clean anonymous session. Keeping the old cookie makes
        # the server redirect an already-signed-in caller straight off the
        # login form, so there is no token to post back and the login fails on
        # a CSRF check instead of refreshing the credentials we came for.
        self._csrf_token = None
        self._ensure_session().cookie_jar.clear()

        _, page = await self._raw("GET", "/admin/login", DEFAULT_TIMEOUT, {})
        payload: dict[str, str] = {
            "username": self._username,
            "password": self._password,
        }
        form_token = _FORM_CSRF_RE.search(page or "")
        if form_token:
            payload[CSRF_FIELD] = form_token.group(1)

        status, body = await self._raw(
            "POST", "/admin/login", DEFAULT_TIMEOUT, {"data": payload}
        )
        if status == 429:
            self._lockout_until = time.monotonic() + LOCKOUT_BACKOFF_SECONDS
            raise FrameITLockoutError(
                "Too many failed logins — the FrameIT server has temporarily "
                "locked this client out"
            )
        if status == 400 and "csrf" in (body or "").lower():
            raise FrameITAuthError(
                "The CSRF handshake with the FrameIT server failed"
            )
        if status not in _REDIRECT_STATUSES:
            raise FrameITAuthError("Invalid credentials or server rejected login")

        # Signing in clears the session, so the usable token has to come from
        # a page rendered afterwards. Fetching an admin page doubles as the
        # auth check: it redirects anyone who is not signed in.
        status, page = await self._raw("GET", "/admin", DEFAULT_TIMEOUT, {})
        if status != 200:
            raise FrameITAuthError(
                f"Signed in, but the server answered HTTP {status} for an "
                "authenticated page"
            )
        meta_token = _META_CSRF_RE.search(page or "")
        self._csrf_token = meta_token.group(1) if meta_token else None
        if not self._csrf_token:
            _LOGGER.debug(
                "No CSRF token on the FrameIT admin page — assuming a server "
                "that predates CSRF protection"
            )

        self._lockout_until = 0.0
        self._auth_generation += 1

    # ------------------------------------------------------------------
    # Internal request helpers
    # ------------------------------------------------------------------

    async def _raw(
        self,
        method: str,
        path: str,
        timeout: aiohttp.ClientTimeout,
        kwargs: dict[str, Any],
    ) -> tuple[int, str]:
        """One HTTP round trip. Never re-authenticates — login() uses it too."""
        session = self._ensure_session()
        headers = dict(kwargs.pop("headers", None) or {})
        if method.upper() not in _SAFE_METHODS and self._csrf_token:
            headers.setdefault(CSRF_HEADER, self._csrf_token)
        try:
            resp = await session.request(
                method,
                f"{self._base_url}{path}",
                allow_redirects=False,
                timeout=timeout,
                headers=headers,
                **kwargs,
            )
            return resp.status, await resp.text()
        except asyncio.TimeoutError as exc:
            raise FrameITConnectionError(f"Timed out calling {path}") from exc
        except aiohttp.ClientError as exc:
            raise FrameITConnectionError(str(exc)) from exc

    def _needs_reauth(self, method: str, status: int, body: str) -> bool:
        """Whether a response means "your session is no longer good"."""
        if status in _REDIRECT_STATUSES or status in (401, 403):
            return True
        # A rejected CSRF token comes back as a 400, not a 401, and it means
        # exactly the same thing: the session this token belonged to is gone.
        return (
            status == 400
            and method.upper() not in _SAFE_METHODS
            and "csrf" in (body or "").lower()
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: aiohttp.ClientTimeout | None = None,
        factory: Callable[[], dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> tuple[int, str]:
        """Make an authenticated request, re-logging in if the session expired.

        ``factory`` supplies request kwargs that cannot be reused across
        attempts — an ``aiohttp.FormData`` body is consumed once it is sent, so
        a retry needs a freshly built one.
        """
        timeout = timeout or DEFAULT_TIMEOUT

        def build() -> dict[str, Any]:
            attempt_kwargs = dict(kwargs)
            if factory is not None:
                attempt_kwargs.update(factory())
            return attempt_kwargs

        generation = self._auth_generation
        status, body = await self._raw(method, path, timeout, build())
        if self._needs_reauth(method, status, body):
            _LOGGER.debug(
                "Re-authenticating with FrameIT after HTTP %s on %s %s",
                status,
                method,
                path,
            )
            await self._reauth(generation)
            status, body = await self._raw(method, path, timeout, build())
        return status, body

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        """Request and decode JSON, raising FrameITApiError on an error status."""
        status, body = await self._request(method, path, **kwargs)
        # Still unauthenticated after a re-login attempt. Say so rather than
        # letting an empty redirect body decode to "no frames configured".
        if status in _REDIRECT_STATUSES or status in (401, 403):
            raise FrameITAuthError(
                f"FrameIT rejected an authenticated request to {path} "
                f"with HTTP {status}"
            )
        if status >= 400:
            raise FrameITApiError(status, _error_message(body))
        if not body.strip():
            return None
        try:
            return json.loads(body)
        except ValueError as exc:
            raise FrameITApiError(
                status, "server returned a response that is not JSON"
            ) from exc

    async def _optional(self, method: str, path: str, **kwargs: Any) -> Any | None:
        """Like _json, but returns None instead of raising.

        Used for the agent proxy, where an unreachable Pi is an ordinary state
        the entities render as "unavailable" rather than an error.
        """
        try:
            return await self._json(method, path, **kwargs)
        except FrameITError as exc:
            _LOGGER.debug("Optional call %s %s failed: %s", method, path, exc)
            return None

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    async def get_frames(self) -> list[dict]:
        return await self._json("GET", "/api/frames") or []

    async def update_frame(self, frame_id: int, data: dict) -> dict | None:
        return await self._json("PATCH", f"/api/frames/{frame_id}", json=data)

    async def send_command(self, frame_id: int, command: str) -> None:
        """Send a next/refresh command to a frame."""
        await self._json(
            "POST",
            f"/api/frames/{frame_id}/command",
            json={"command": command},
        )

    # ------------------------------------------------------------------
    # Agent — system info & display
    # ------------------------------------------------------------------

    async def get_system_info(self, frame_id: int) -> dict | None:
        """Return agent system info, or None if the agent is unreachable."""
        return await self._optional(
            "GET", f"/api/frames/{frame_id}/agent/system/info", timeout=AGENT_TIMEOUT
        )

    async def get_display(self, frame_id: int) -> dict | None:
        """Return display state {on: bool}, or None if agent is unreachable."""
        return await self._optional(
            "GET", f"/api/frames/{frame_id}/agent/display", timeout=AGENT_TIMEOUT
        )

    async def set_display(self, frame_id: int, on: bool) -> None:
        action = "on" if on else "off"
        await self._json("POST", f"/api/frames/{frame_id}/agent/display/{action}")

    async def reboot(self, frame_id: int) -> None:
        await self._json("POST", f"/api/frames/{frame_id}/agent/system/reboot")

    async def trigger_agent_update(self, frame_id: int) -> None:
        """Tell the agent to download and apply the latest version."""
        await self._json("POST", f"/api/frames/{frame_id}/agent/system/agent-update")

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    async def get_services(self, frame_id: int) -> dict | None:
        """Return {frameit-agent: bool, frameit-ui: bool}, or None if unreachable."""
        return await self._optional(
            "GET",
            f"/api/frames/{frame_id}/agent/system/services",
            timeout=AGENT_TIMEOUT,
        )

    async def restart_service(self, frame_id: int, name: str) -> None:
        await self._json(
            "POST", f"/api/frames/{frame_id}/agent/system/services/{name}/restart"
        )

    # ------------------------------------------------------------------
    # Library — posters and trailers
    # ------------------------------------------------------------------

    async def get_posters(self) -> list[dict]:
        return await self._json("GET", "/api/posters") or []

    async def get_trailers(self) -> list[dict]:
        return await self._json("GET", "/api/trailers") or []

    async def upload_poster(
        self,
        image_data: bytes,
        filename: str,
        title_above: str | None = None,
        title_below: str | None = None,
    ) -> dict:
        """Upload image bytes as a new poster. Returns the created poster dict."""
        sniffed = sniff_image(image_data)
        if sniffed is None:
            raise FrameITError(
                "Artwork is not a JPEG, PNG, or WebP image — the server would "
                "reject it"
            )
        extension, content_type = sniffed
        stem = filename.rsplit(".", 1)[0] or "poster"
        upload_name = f"{stem}.{extension}"

        def build_form() -> dict[str, Any]:
            form = aiohttp.FormData()
            form.add_field(
                "file", image_data, filename=upload_name, content_type=content_type
            )
            if title_above:
                form.add_field("title_above", title_above[:MAX_TITLE_LENGTH])
            if title_below:
                form.add_field("title_below", title_below[:MAX_TITLE_LENGTH])
            # inactive so it doesn't appear in pool rotation or active counts
            form.add_field("active", "false")
            return {"data": form}

        return await self._json("POST", "/api/posters/upload", factory=build_form)

    async def delete_poster(self, poster_id: int) -> None:
        await self._json("DELETE", f"/api/posters/{poster_id}")

    # ------------------------------------------------------------------
    # Global settings
    # ------------------------------------------------------------------

    async def get_settings(self) -> dict:
        """Return the global FrameIT settings dict."""
        return await self._json("GET", "/api/settings") or {}

    async def update_settings(self, data: dict) -> dict:
        """Patch global settings; returns the updated settings dict."""
        return await self._json("PATCH", "/api/settings", json=data) or {}

    # ------------------------------------------------------------------
    # Agent version
    # ------------------------------------------------------------------

    async def get_server_agent_version(self) -> str | None:
        """Return the server's current agent version hash, or None on error."""
        data = await self._optional("GET", "/api/agent/version")
        if isinstance(data, dict):
            return data.get("version")
        return None
