"""
Security Module for DriveGuard APIs.

Provides:
- API Key authentication via X-API-Key header
- Rate limiting via slowapi
- Security headers middleware
- CORS origin management from environment

Usage in any FastAPI app:
    from security import apply_security

    apply_security(app)
"""

import os
import logging
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    HAS_SLOWAPI = True
except ImportError:
    HAS_SLOWAPI = False

logger = logging.getLogger("dg.security")

# ─── Constants ────────────────────────────────────────────────────────────

# Paths that never require an API key
PUBLIC_PATHS = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}

# Prefixes that never require an API key
PUBLIC_PREFIXES = (
    "/api/health",
    "/dashboard",
    "/assets",
    "/ws",
)

# ─── API Key Middleware ───────────────────────────────────────────────────

class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Validates X-API-Key header on non-public endpoints.
    If DG_API_KEY is not set, auth is disabled (dev mode).
    """

    def __init__(self, app, api_key: Optional[str] = None):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        # Skip auth if no key configured (dev mode)
        if not self.api_key:
            return await call_next(request)

        path = request.url.path

        # Allow public paths
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # Allow public prefixes
        for prefix in PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Allow OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Validate API key
        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != self.api_key:
            logger.warning(f"Rejected request to {path} — invalid API key")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"}
            )

        return await call_next(request)


# ─── Security Headers Middleware ──────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        return response


# ─── Rate Limiter ─────────────────────────────────────────────────────────

def create_limiter() -> Optional[object]:
    """Create a slowapi rate limiter if available."""
    if not HAS_SLOWAPI:
        logger.info("slowapi not installed — rate limiting disabled")
        return None

    default_limit = os.getenv("DG_RATE_LIMIT", "200/minute")
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[default_limit]
    )
    return limiter


# ─── Main Apply Function ─────────────────────────────────────────────────

def apply_security(app: FastAPI, module_name: str = "api"):
    """
    Apply all security middleware to a FastAPI app.

    Args:
        app: The FastAPI application instance
        module_name: Name for logging (e.g. 'fusion', 'dz', 'tsr')
    """
    # 1. Load API key from environment
    api_key = os.getenv("DG_API_KEY", "")

    if api_key:
        logger.info(f"[{module_name}] API key authentication ENABLED")
    else:
        logger.warning(f"[{module_name}] No DG_API_KEY set — auth DISABLED (dev mode)")

    # 2. CORS — restricted origins from env, fallback to permissive for dev
    raw_origins = os.getenv("DG_CORS_ORIGINS", "")
    if raw_origins:
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        logger.info(f"[{module_name}] CORS restricted to: {origins}")
    else:
        origins = ["*"]
        logger.warning(f"[{module_name}] CORS open to all origins (dev mode)")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-API-Key"],
    )

    # 3. Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 4. API key middleware
    app.add_middleware(APIKeyMiddleware, api_key=api_key if api_key else None)

    # 5. Rate limiting
    if HAS_SLOWAPI:
        limiter = create_limiter()
        if limiter:
            app.state.limiter = limiter
            app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
            logger.info(f"[{module_name}] Rate limiting ENABLED ({os.getenv('DG_RATE_LIMIT', '60/minute')})")
    else:
        logger.info(f"[{module_name}] Rate limiting DISABLED (install slowapi)")

    return app


async def _rate_limit_handler(request: Request, exc: Exception):
    """Handle rate limit exceeded."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down.",
            "retry_after": getattr(exc, "retry_after", 60)
        }
    )
