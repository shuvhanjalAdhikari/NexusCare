# ================================================================
# NexusCare — app/middleware/cors.py
# CORS middleware registration.
#
# A browser blocks a frontend served from a different origin (e.g. the
# Vite dev server on http://localhost:5173) from calling this API
# unless the API answers CORS preflight requests with the right
# headers. This module wires FastAPI's CORSMiddleware from the
# CORS_ALLOWED_ORIGINS setting.
#
# allow_credentials=True lets the browser send cookies / the
# Authorization header on cross-origin requests. The CORS spec forbids
# pairing credentialed requests with a wildcard origin ("*"), so the
# allowed origins MUST be an explicit list — never "*".
#
# Production: CORS_ALLOWED_ORIGINS must be a strict whitelist of the
# real frontend hostnames (e.g. https://app.nexuscare.com). The
# localhost defaults in config.py are dev-only; set the env var
# explicitly in every non-dev deployment.
# ================================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


def add_cors_middleware(app: FastAPI) -> None:
    """
    Register CORS on the FastAPI app. Call this before any other
    middleware so the CORS layer is outermost and handles browser
    preflight (OPTIONS) requests first.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
