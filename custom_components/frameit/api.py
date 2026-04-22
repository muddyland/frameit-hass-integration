"""Async API client for the FrameIT server."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class FrameITAuthError(Exception):
    """Raised when authentication fails."""


class FrameITConnectionError(Exception):
    """Raised when the server cannot be reached."""


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
        """POST credentials to obtain a session cookie."""
        session = self._ensure_session()
        try:
            await session.post(
                f"{self._base_url}/admin/login",
                data={"username": self._username, "password": self._password},
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            )
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

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make an authenticated request, re-logging in if the session expired."""
        session = self._ensure_session()
        url = f"{self._base_url}{path}"
        timeout = kwargs.pop("timeout", aiohttp.ClientTimeout(total=10))

        try:
            resp = await session.request(
                method, url, allow_redirects=False, timeout=timeout, **kwargs
            )
            if resp.status in (302, 401, 403):
                _LOGGER.debug("Session expired, re-authenticating")
                await self.login()
                resp = await session.request(
                    method, url, allow_redirects=False, timeout=timeout, **kwargs
                )
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
