from fastapi import APIRouter

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "version": __version__, "llm_provider": settings.llm_provider}
