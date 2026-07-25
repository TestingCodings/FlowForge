"""
Shared safety + templating for outbound calls (webhooks and action hooks).

Two concerns both features need (docs/HOOKS.md Part 2):

1. SSRF guard — the server makes requests to user-defined URLs, so a URL must
   be validated before it is called: only http/https, and no host that
   resolves to a private / loopback / link-local / reserved address (which
   would let a caller probe the VPS's own network or cloud metadata).

2. Config templating — resolve `{{secret.NAME}}`, `{{metadata.key}}`, and
   `{{instance.reference_number}}` in hook URLs/headers/bodies, with secrets
   pulled from the encrypted store and never logged.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit

from django.conf import settings


class UnsafeURLError(ValueError):
    """Raised when an outbound URL fails the SSRF guard."""


def assert_safe_url(url: str) -> None:
    """Raise UnsafeURLError unless `url` is a public http(s) endpoint.

    An optional allow-list (settings.OUTBOUND_ALLOWED_HOSTS) restricts calls
    further — when set, only those hostnames are permitted (used in the demo
    deployment). When empty, any public host is allowed.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError(f"URL scheme must be http or https, got '{parts.scheme}'.")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("URL has no host.")

    allow = [h.strip().lower() for h in getattr(settings, "OUTBOUND_ALLOWED_HOSTS", []) if h.strip()]
    if allow and host.lower() not in allow:
        raise UnsafeURLError(f"Host '{host}' is not in the outbound allow-list.")

    # Resolve every address the host maps to; reject if ANY is non-public, so a
    # DNS name that resolves to a private IP can't slip through.
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve host '{host}'.") from exc

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UnsafeURLError(f"Host '{host}' resolves to a non-public address ({addr}).")


_TEMPLATE_RE = re.compile(r"\{\{\s*(secret|metadata|instance)\.([\w.-]+)\s*\}\}")


def render_template(text: str, *, instance=None, secret_values: dict | None = None) -> str:
    """Resolve {{secret.X}} / {{metadata.X}} / {{instance.X}} placeholders.

    `secret_values` is a pre-resolved {name: plaintext} map (fetched from the
    store by the caller, held only in memory). Unknown placeholders are left
    intact so a typo is visible rather than silently blanked.
    """
    if not text:
        return text
    secret_values = secret_values or {}
    meta = (getattr(instance, "metadata_json", None) or {}) if instance is not None else {}

    def repl(m: re.Match) -> str:
        kind, key = m.group(1), m.group(2)
        if kind == "secret":
            return secret_values.get(key, m.group(0))
        if kind == "metadata":
            val = meta.get(key)
            return "" if val is None else str(val)
        if kind == "instance":
            val = getattr(instance, key, None) if instance is not None else None
            return "" if val is None else str(val)
        return m.group(0)

    return _TEMPLATE_RE.sub(repl, text)


def referenced_secret_names(*texts: str) -> set[str]:
    """Collect the secret names referenced across some template strings."""
    names: set[str] = set()
    for text in texts:
        if not text:
            continue
        for m in _TEMPLATE_RE.finditer(text):
            if m.group(1) == "secret":
                names.add(m.group(2))
    return names
