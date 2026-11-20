"""Request-scoped dependencies taken from app.state (set by create_app)."""

from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException, Request
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
    """Thresholds from the file, re-read when it changes: a live edit needs no API restart.

    A policy passed to create_app (tests) has no file and is used as is.
    """
    state = request.app.state
    path: Path | None = state.policy_path
    if path is not None:
        mtime = path.stat().st_mtime_ns
        if mtime != state.policy_mtime:
            try:
                state.policy = PolicyConfig.load(path)
            except Exception as exc:  # a broken edit must be visible, not silently ignored
                raise HTTPException(
                    status_code=500, detail=f"thresholds.yaml не читается: {type(exc).__name__}"
                ) from None
            state.policy_mtime = mtime
    return state.policy


def require_json(request: Request) -> None:
    """Writes that cost money accept JSON only.

    A form post from another site cannot send this content type without a CORS preflight,
    which this API does not answer, so a page open in the same browser cannot start a run.
    """
    kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if kind != "application/json":
        raise HTTPException(status_code=415, detail="Нужен запрос с Content-Type: application/json")
