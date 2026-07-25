"""
Thin FlowForge REST client for the MCP server.

Authenticates with the seeded/service credentials, caches the JWT, and
re-logs-in transparently on a 401 (JWTs expire). All the hard logic —
engine, rules, auth, versioning — lives in the FlowForge API; this is a
mapping layer only.
"""
from __future__ import annotations

import os

import httpx


class FlowForgeError(RuntimeError):
    pass


class FlowForgeClient:
    def __init__(self, base_url: str | None = None, email: str | None = None,
                 password: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.environ.get("FLOWFORGE_API_URL", "http://localhost:8000/api")).rstrip("/")
        self.email = email or os.environ.get("FLOWFORGE_EMAIL", "")
        self.password = password or os.environ.get("FLOWFORGE_PASSWORD", "")
        self._token = token or os.environ.get("FLOWFORGE_TOKEN", "")
        self._http = httpx.Client(timeout=15)

    # ── auth ──
    def _login(self) -> None:
        if not (self.email and self.password):
            raise FlowForgeError(
                "No valid token and no FLOWFORGE_EMAIL/FLOWFORGE_PASSWORD to log in with."
            )
        r = self._http.post(f"{self.base_url}/auth/login/",
                            json={"email": self.email, "password": self.password})
        if r.status_code != 200:
            raise FlowForgeError(f"Login failed ({r.status_code}): {r.text[:200]}")
        self._token = r.json()["access"]

    def _headers(self) -> dict:
        if not self._token:
            self._login()
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, path: str, **kw):
        url = f"{self.base_url}{path}"
        r = self._http.request(method, url, headers=self._headers(), **kw)
        if r.status_code == 401:  # token expired — one retry after re-login
            self._login()
            r = self._http.request(method, url, headers=self._headers(), **kw)
        if r.status_code >= 400:
            raise FlowForgeError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    def get(self, path, **kw):
        return self._request("GET", path, **kw)

    def post(self, path, **kw):
        return self._request("POST", path, **kw)

    def put(self, path, **kw):
        return self._request("PUT", path, **kw)

    @staticmethod
    def _list(payload):
        """DRF list endpoints are paginated ({results:[...]}) or bare lists."""
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
        return payload or []
