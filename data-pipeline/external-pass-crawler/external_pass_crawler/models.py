from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    external_id: str
    company: str
    role: str


@dataclass(frozen=True)
class PublicMaterial:
    external_id: str
    company: str
    role: str
    content: str  # Parser value: never log; only daily collection stores cleaned prose separately.


@dataclass(frozen=True)
class SearchPage:
    candidates: tuple[Candidate, ...]
    total: int


@dataclass(frozen=True)
class StoredMaterial:
    external_id: str
    role: str
    content: str
    body_text: str | None = None
