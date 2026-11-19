"""Registry of source format adapters."""

from app.ingestion.adapters.sample_v1 import SampleV1Adapter
from app.ingestion.base import SourceAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    SampleV1Adapter.name: SampleV1Adapter,
}


def get_adapter(name: str) -> SourceAdapter:
    try:
        return ADAPTERS[name]()
    except KeyError:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"unknown adapter {name!r}; known: {known}") from None
