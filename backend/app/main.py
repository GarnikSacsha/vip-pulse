"""FastAPI application factory.

Run with `uvicorn app.main:create_app --factory --reload`. A factory (instead of a module-level
app) keeps imports free of side effects: no database file is created just by importing.
"""

from fastapi import FastAPI
from sqlalchemy import Engine

from app import __version__
from app.analysis.llm import LLMProvider, get_provider
from app.api import health, queue
from app.config import get_settings
from app.db import init_db, make_engine
from app.policy.config import PolicyConfig


def create_app(
    engine: Engine | None = None,
    provider: LLMProvider | None = None,
    policy: PolicyConfig | None = None,
) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="VIP Pulse AI", version=__version__)
    app.state.engine = engine or make_engine()
    app.state.provider = provider or get_provider(settings)
    app.state.policy = policy or PolicyConfig.load(settings.policy_path)
    init_db(app.state.engine)
    app.include_router(health.router)
    app.include_router(queue.router)
    return app
