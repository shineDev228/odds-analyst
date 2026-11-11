"""Middlewares transverses : identifiant de requête et en-têtes de sécurité."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import request_id_context

logger = logging.getLogger("odds_analyst.http")

_REQUETE_LENTE_MS = 2_000

# `/docs` (Swagger UI) charge ses ressources depuis un CDN public.
_CSP_DOCS = (
    "default-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'; base-uri 'self'"
)

_CSP_API = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
_CSP_SIMPLE = "default-src 'none'; frame-ancestors 'none'"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attribue un identifiant à chaque requête et journalise sa durée."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "requete_echec",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": int((time.perf_counter() - started_at) * 1000),
                },
            )
            raise
        else:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            response.headers["X-Request-ID"] = request_id
            if elapsed_ms >= _REQUETE_LENTE_MS:
                logger.warning(
                    "requete_lente method=%s path=%s status=%s duration_ms=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    elapsed_ms,
                )
            else:
                logger.info(
                    "requete method=%s path=%s status=%s duration_ms=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    elapsed_ms,
                )
            return response
        finally:
            request_id_context.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute les en-têtes de sécurité à toutes les réponses de l'API."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        headers = response.headers

        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        headers.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), microphone=(), "
            "payment=(), usb=()",
        )

        path = request.url.path
        if path.startswith("/api/"):
            headers.setdefault("Content-Security-Policy", _CSP_API)
            headers.setdefault("Cache-Control", "no-store")
        elif path == "/docs" or path.startswith("/docs/") or path == "/openapi.json":
            headers.setdefault("Content-Security-Policy", _CSP_DOCS)
        else:
            headers.setdefault("Content-Security-Policy", _CSP_SIMPLE)

        if settings.cookie_secure:
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age_seconds}; includeSubDomains",
            )

        return response
