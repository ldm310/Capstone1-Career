from typing import Protocol
from ..models import SearchPage, PublicMaterial


class PlatformAdapter(Protocol):
    def search(self, company: str, page: int) -> SearchPage: ...
    def detail(self, external_id: str) -> PublicMaterial: ...
