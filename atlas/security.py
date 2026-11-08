"""Browser hardening for the local Atlas service.

Atlas is typically opened on loopback, but it still renders user-controlled data
and exposes state-changing endpoints. These headers and origin checks are cheap
defense in depth; they do not replace the SQL sandbox.
"""
from __future__ import annotations

import hmac
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import Response

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
AUTH_COOKIE = "atlas_token"

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        # The report uses inline style blocks and the UI uses style attributes.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        # The report preview is an iframe on the same origin.
        "frame-src 'self'",
        "frame-ancestors 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "manifest-src 'self'",
        "worker-src 'none'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class OriginRejected(RuntimeError):
    """Raised when a browser request comes from another origin."""


class AuthRejected(RuntimeError):
    """Raised when a non-loopback request does not carry the local token."""


def is_loopback_request(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host.strip("[]").lower() in LOOPBACK_HOSTS


def supplied_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    token = request.headers.get("x-atlas-token") or ""
    return token.strip() or (request.cookies.get(AUTH_COOKIE) or "")


def token_matches(token: str | None, expected: str | None) -> bool:
    if not token or not expected:
        return False
    return hmac.compare_digest(token, expected)


def check_request_auth(request: Request, expected: str | None) -> None:
    """Require a bearer token when the service is bound beyond loopback."""
    if not expected or is_loopback_request(request):
        return
    supplied = supplied_token(request)
    if supplied and hmac.compare_digest(supplied, expected):
        return
    raise AuthRejected("A bearer token is required. Open the URL with ?token=... once.")


def _normalise_netloc(scheme: str, netloc: str) -> str:
    netloc = (netloc or "").lower()
    if scheme == "http" and netloc.endswith(":80"):
        return netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        return netloc[:-4]
    return netloc


def _is_loopback(netloc: str) -> bool:
    host = netloc.rsplit(":", 1)[0] if netloc.count(":") == 1 else netloc
    return host.strip("[]").lower() in LOOPBACK_HOSTS


def check_request_origin(request: Request) -> None:
    """Reject cross-site state changes, while allowing CLI and test clients.

    Browsers send ``Origin`` on CORS-relevant requests and ``Sec-Fetch-Site`` on
    modern ones. Non-browser clients such as curl send neither, so they remain
    usable for local automation.
    """
    if request.method.upper() not in MUTATING_METHODS:
        return

    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    if fetch_site and fetch_site not in {"same-origin", "none"}:
        raise OriginRejected("Cross-site requests are not allowed.")

    origin = request.headers.get("origin")
    if not origin:
        return
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OriginRejected("Invalid request origin.")

    host = request.headers.get("host") or request.url.netloc
    request_scheme = request.url.scheme
    origin_netloc = _normalise_netloc(parsed.scheme, parsed.netloc)
    host_netloc = _normalise_netloc(request_scheme, host)

    if origin_netloc == host_netloc:
        return
    # Developers often mix localhost and 127.0.0.1. Treat loopback aliases with
    # the same port as the same local origin.
    if (
        parsed.scheme == request_scheme
        and _is_loopback(origin_netloc)
        and _is_loopback(host_netloc)
        and _port(origin_netloc) == _port(host_netloc)
    ):
        return
    raise OriginRejected("Cross-site requests are not allowed.")


def _port(netloc: str) -> str:
    if netloc.startswith("["):
        return netloc.rsplit(":", 1)[1] if "]:" in netloc else ""
    return netloc.rsplit(":", 1)[1] if netloc.count(":") == 1 else ""


def apply_security_headers(response: Response) -> None:
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers.setdefault("Cache-Control", "no-store")
