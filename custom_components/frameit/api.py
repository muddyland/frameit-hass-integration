"""Async API client for the FrameIT server."""
from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# FrameIT protects every state-changing endpoint that is not machine-to-machine
# with a per-session CSRF token. A browser picks it up by rendering a page; we
# have to scrape it out of the same HTML.
#
# Two places carry it: the login form's hidden field
# (`<input name="_csrf_token" value="...">`) and, once signed in, the admin
# layout's `<meta name="csrf-token" content="...">`. Both are needed, because
# the server's _sign_in() clears the session — the token that authorises the
# login POST is destroyed by the successful login itself.
_CSRF_FIELD = "_csrf_token"
_CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

_CSRF_TAG_RE = re.compile(r"<(?:input|meta)\b[^>]*>", re.IGNORECASE)
_CSRF_NAME_RE = re.compile(
    r"""name\s*=\s*["'](?:_csrf_token|csrf-token)["']""", re.IGNORECASE
)
_CSRF_VALUE_RE = re.compile(
    r"""(?:value|content)\s*=\s*["']([^"']*)["']""", re.IGNORECASE
)


def _extract_csrf_token(html: str | None) -> str | None:
    """Pull the CSRF token out of a FrameIT HTML page, or None if absent.

    Scans whole ``<input>``/``<meta>`` tags rather than matching a fixed
    attribute order, so a template tweak that reorders attributes does not
    silently break authentication.
    """
    if not html or not isinstance(html, str):
        return None
    for match in _CSRF_TAG_RE.finditer(html):
        tag = match.group(0)
        if not _CSRF_NAME_RE.search(tag):
            continue
        value = _CSRF_VALUE_RE.search(tag)
        if value and value.group(1):
            return value.group(1)
    return None


class FrameITAuthError(Exception):
    """Raised when authentication fails."""


class FrameITConnectionError(Exception):
    """Raised when the server cannot be reached."""


def _sniff_image(data: bytes) -> tuple[str, str]:
    """Return (extension, mime) for image bytes.

    The server sniffs magic bytes and ignores the filename, but sending a
    content type that matches the payload keeps the request honest and makes
    a rejected upload easy to read in a packet capture.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    # Unknown: send it anyway and let the server's 400 be the authority.
    return "img", "application/octet-stream"


def _now_playing_form(
    state: str,
    *,
    title: str | None,
    artist: str | None,
    album: str | None,
    entity_id: str | None,
    image: bytes | None,
) -> aiohttp.FormData:
    """Build the multipart body for /api/now-playing.

    Empty metadata fields are omitted rather than sent blank, so the server
    stores None and a frame falls back to its own defaults.
    """
    form = aiohttp.FormData()
    form.add_field("state", state)
    for name, value in (
        ("title", title),
        ("artist", artist),
        ("album", album),
        ("entity_id", entity_id),
    ):
        if value:
            form.add_field(name, value)
    if image:
        ext, mime = _sniff_image(image)
        form.add_field("image", image, filename=f"cover.{ext}", content_type=mime)
    return form


class FrameITApiClient:
    """Async HTTP client for FrameIT.

    Authenticates via the admin session cookie (form login) and
    re-authenticates transparently when the session expires.
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        # Minted by login(); replayed as X-CSRF-Token on every write.
        self._csrf_token: str | None = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )
        return self._session

    async def login(self) -> None:
        """Sign in and obtain both a session cookie and a CSRF token.

        Three steps, and all three are load-bearing:

        1. GET /admin/login — the cookie jar picks up the session cookie and
           the page body carries the CSRF token that POST must echo back.
           Without this the POST is rejected with HTTP 400 before the
           credential check ever runs.
        2. POST the credentials plus the token, then verify against a
           protected endpoint.
        3. Re-read a CSRF token from the signed-in page. The server clears the
           session on successful login, so the token from step 1 is dead and
           subsequent writes need the new one.
        """
        session = self._ensure_session()
        self._csrf_token = None
        login_url = f"{self._base_url}/admin/login"

        try:
            page = await session.get(
                login_url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            login_html = await page.text()
        except aiohttp.ClientError as exc:
            raise FrameITConnectionError(str(exc)) from exc

        token = _extract_csrf_token(login_html)
        if not token:
            raise FrameITConnectionError(
                f"No CSRF token found on the FrameIT login page at {login_url}. "
                "Check that the URL points at a FrameIT server and that it is "
                "up to date."
            )

        try:
            resp = await session.post(
                login_url,
                data={
                    "username": self._username,
                    "password": self._password,
                    _CSRF_FIELD: token,
                },
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            landing_html = await resp.text()
            # Verify auth by hitting a protected endpoint
            resp = await session.get(
                f"{self._base_url}/api/frames",
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            if resp.status in (302, 401, 403):
                raise FrameITAuthError("Invalid credentials or server rejected login")
        except aiohttp.ClientError as exc:
            raise FrameITConnectionError(str(exc)) from exc

        # The login POST usually lands on the admin dashboard, which already
        # embeds a fresh token; only fetch the page again if it did not.
        self._csrf_token = _extract_csrf_token(landing_html)
        if not self._csrf_token:
            self._csrf_token = await self._fetch_csrf_token()
        if not self._csrf_token:
            _LOGGER.warning(
                "Signed in to FrameIT but found no CSRF token on the admin "
                "page; changes sent to the server may be rejected"
            )

    async def _fetch_csrf_token(self) -> str | None:
        """GET the admin dashboard and scrape its CSRF meta tag."""
        session = self._ensure_session()
        try:
            resp = await session.get(
                f"{self._base_url}/admin",
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            return _extract_csrf_token(await resp.text())
        except aiohttp.ClientError as exc:
            raise FrameITConnectionError(str(exc)) from exc

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _is_csrf_rejection(resp: aiohttp.ClientResponse) -> bool:
        """True if this 400 is the server refusing a missing/stale CSRF token.

        A rejection is a 400, not a 401, so it does not trip the session-expiry
        path above; without this check a stale token would fail every write
        until Home Assistant restarted.
        """
        if resp.status != 400:
            return False
        try:
            body = await resp.text()
        except Exception:  # pylint: disable=broad-except
            return False
        return isinstance(body, str) and "csrf" in body.lower()

    async def _send(
        self,
        method: str,
        url: str,
        timeout: aiohttp.ClientTimeout,
        kwargs: dict[str, Any],
    ) -> aiohttp.ClientResponse:
        """One attempt, with the CSRF token attached if the method needs it."""
        session = self._ensure_session()
        call_kwargs = dict(kwargs)
        if method.upper() not in _SAFE_METHODS and self._csrf_token:
            headers = dict(call_kwargs.get("headers") or {})
            headers.setdefault(_CSRF_HEADER, self._csrf_token)
            call_kwargs["headers"] = headers
        return await session.request(
            method, url, allow_redirects=False, timeout=timeout, **call_kwargs
        )

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make an authenticated request, re-logging in if the session expired.

        Writes carry a CSRF token: every state-changing FrameIT endpoint this
        client touches (PATCH /api/frames/<id>, PATCH /api/settings, POST
        /api/settings/now-playing-token, the agent proxy, DELETE /api/posters/
        <id>) is CSRF-protected. Only the frame/agent machine-to-machine
        endpoints are exempt, and this client does not call those.
        """
        url = f"{self._base_url}{path}"
        timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=10))
        unsafe = method.upper() not in _SAFE_METHODS

        if unsafe and self._csrf_token is None:
            # Nothing to sign the write with yet — log in first rather than
            # spending a guaranteed 400 to find that out.
            await self.login()

        try:
            resp = await self._send(method, url, timeout, kwargs)
            if resp.status in (302, 401, 403):
                _LOGGER.debug("Session expired, re-authenticating")
                await self.login()
                resp = await self._send(method, url, timeout, kwargs)
            elif unsafe and await self._is_csrf_rejection(resp):
                _LOGGER.debug("CSRF token rejected, re-authenticating")
                await self.login()
                resp = await self._send(method, url, timeout, kwargs)
            return resp
        except aiohttp.ClientError as exc:
            raise FrameITConnectionError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    async def get_frames(self) -> list[dict]:
        resp = await self._request("GET", "/api/frames")
        return await resp.json()

    async def update_frame(self, frame_id: int, data: dict) -> None:
        await self._request("PATCH", f"/api/frames/{frame_id}", json=data)

    async def send_command(self, frame_id: int, command: str) -> None:
        """Send a next/refresh command to a frame."""
        await self._request(
            "POST",
            f"/api/frames/{frame_id}/command",
            json={"command": command},
        )

    # ------------------------------------------------------------------
    # Agent — system info & display
    # ------------------------------------------------------------------

    async def get_system_info(self, frame_id: int) -> dict | None:
        """Return agent system info, or None if the agent is unreachable."""
        try:
            resp = await self._request(
                "GET",
                f"/api/frames/{frame_id}/agent/system/info",
                timeout=aiohttp.ClientTimeout(total=5),
            )
            if resp.status == 200:
                return await resp.json()
        except Exception:  # pylint: disable=broad-except
            pass
        return None

    async def get_display(self, frame_id: int) -> dict | None:
        """Return display state {on: bool}, or None if agent is unreachable."""
        try:
            resp = await self._request(
                "GET",
                f"/api/frames/{frame_id}/agent/display",
                timeout=aiohttp.ClientTimeout(total=5),
            )
            if resp.status == 200:
                return await resp.json()
        except Exception:  # pylint: disable=broad-except
            pass
        return None

    async def set_display(self, frame_id: int, on: bool) -> None:
        action = "on" if on else "off"
        await self._request(
            "POST",
            f"/api/frames/{frame_id}/agent/display/{action}",
        )

    async def reboot(self, frame_id: int) -> None:
        await self._request("POST", f"/api/frames/{frame_id}/agent/system/reboot")

    async def trigger_agent_update(self, frame_id: int) -> None:
        """Tell the agent to download and apply the latest version."""
        await self._request(
            "POST", f"/api/frames/{frame_id}/agent/system/agent-update"
        )

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    async def get_services(self, frame_id: int) -> dict | None:
        """Return {frameit-agent: bool, frameit-ui: bool}, or None if unreachable."""
        try:
            resp = await self._request(
                "GET",
                f"/api/frames/{frame_id}/agent/system/services",
                timeout=aiohttp.ClientTimeout(total=5),
            )
            if resp.status == 200:
                return await resp.json()
        except Exception:  # pylint: disable=broad-except
            pass
        return None

    async def restart_service(self, frame_id: int, name: str) -> None:
        await self._request(
            "POST",
            f"/api/frames/{frame_id}/agent/system/services/{name}/restart",
        )

    # ------------------------------------------------------------------
    # Library — posters and trailers
    # ------------------------------------------------------------------

    async def get_posters(self) -> list[dict]:
        resp = await self._request("GET", "/api/posters")
        return await resp.json()

    async def get_trailers(self) -> list[dict]:
        resp = await self._request("GET", "/api/trailers")
        return await resp.json()

    async def delete_poster(self, poster_id: int) -> None:
        await self._request("DELETE", f"/api/posters/{poster_id}")

    # ------------------------------------------------------------------
    # Global settings
    # ------------------------------------------------------------------

    async def get_settings(self) -> dict:
        """Return the global FrameIT settings dict."""
        resp = await self._request("GET", "/api/settings")
        return await resp.json()

    async def update_settings(self, data: dict) -> dict:
        """Patch global settings; returns the updated settings dict."""
        resp = await self._request("PATCH", "/api/settings", json=data)
        return await resp.json()

    # ------------------------------------------------------------------
    # Now playing
    # ------------------------------------------------------------------

    async def create_now_playing_token(self) -> str | None:
        """Mint a new webhook token. The server returns it exactly once.

        Minting invalidates whatever token was there before, so this is only
        called when the user explicitly asks for one in the options flow.
        """
        resp = await self._request("POST", "/api/settings/now-playing-token")
        if resp.status != 200:
            return None
        data = await resp.json()
        return data.get("token")

    async def post_now_playing(
        self,
        token: str,
        state: str,
        *,
        title: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        entity_id: str | None = None,
        image: bytes | None = None,
    ) -> dict:
        """POST the current media state to the now-playing webhook.

        This endpoint authenticates with a bearer token rather than the admin
        session, so it deliberately bypasses ``_request``: a 401 here means a
        wrong token, and re-running the cookie login would neither fix it nor
        be worth the round trip.
        """
        session = self._ensure_session()
        form = _now_playing_form(
            state,
            title=title,
            artist=artist,
            album=album,
            entity_id=entity_id,
            image=image,
        )

        try:
            resp = await session.post(
                f"{self._base_url}/api/now-playing",
                data=form,
                headers={"Authorization": f"Bearer {token}"},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        except aiohttp.ClientError as exc:
            raise FrameITConnectionError(str(exc)) from exc

        if resp.status == 401:
            raise FrameITAuthError(
                "FrameIT rejected the now-playing token. Generate a new one in "
                "the integration options."
            )
        if resp.status != 200:
            body = await resp.text()
            raise FrameITConnectionError(
                f"now-playing webhook returned HTTP {resp.status}: {body[:200]}"
            )
        return await resp.json()

    # ------------------------------------------------------------------
    # Agent version
    # ------------------------------------------------------------------

    async def get_server_agent_version(self) -> str | None:
        """Return the server's current agent version hash, or None on error."""
        try:
            resp = await self._request("GET", "/api/agent/version")
            if resp.status == 200:
                data = await resp.json()
                return data.get("version")
        except Exception:  # pylint: disable=broad-except
            pass
        return None
