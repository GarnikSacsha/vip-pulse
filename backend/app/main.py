"""FastAPI entrypoint: `uvicorn app.main:app --reload`."""

from fastapi import FastAPI

from app import __version__
from app.api import health


def create_app() -> FastAPI:
    app = FastAPI(title="VIP Pulse AI", version=__version__)
    app.include_router(health.router)
    return app


app = create_app()
