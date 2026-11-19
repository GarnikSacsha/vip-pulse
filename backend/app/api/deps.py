"""Request-scoped dependencies taken from app.state (set by create_app)."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.llm import LLMProvider
from app.policy.config import PolicyConfig


def get_session(request: Request) -> Iterator[Session]:
    factory = sessionmaker(bind=request.app.state.engine, expire_on_commit=False)
    with factory() as session:
        yield session


def get_provider(request: Request) -> LLMProvider:
    return request.app.state.provider


def get_policy(request: Request) -> PolicyConfig:
    return request.app.state.policy
