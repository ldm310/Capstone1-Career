from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import CaseManifest


ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".log", ".json", ".jsonl", ".toml", ".yaml", ".yml"}


@dataclass
class ReadOnlyCaseTools:
    case_root: Path
    allowed_files: set[str]
    calls: list[dict[str, str]] = field(default_factory=list)
    read_paths: set[str] = field(default_factory=set)

    def _resolve(self, relative: str) -> Path:
        candidate = (self.case_root / relative).resolve()
        root = self.case_root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("path escapes case root")
        if relative not in self.allowed_files:
            raise ValueError(f"file is outside manifest: {relative}")
        if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError("unsupported file type")
        return candidate

    def list_files(self) -> list[str]:
        self.calls.append({"tool": "list_files", "argument": "."})
        return sorted(self.allowed_files)

    def read_file(self, relative: str) -> str:
        path = self._resolve(relative)
        self.calls.append({"tool": "read_file", "argument": relative})
        self.read_paths.add(relative)
        return path.read_text(encoding="utf-8")

    def search_text(self, query: str) -> list[dict[str, object]]:
        self.calls.append({"tool": "search_text", "argument": query})
        pattern = re.compile(query, re.IGNORECASE)
        hits: list[dict[str, object]] = []
        for relative in sorted(self.allowed_files):
            text = self._resolve(relative).read_text(encoding="utf-8")
            self.read_paths.add(relative)
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append({"path": relative, "line": number, "text": line[:300]})
        return hits


def load_case(case_dir: Path) -> tuple[CaseManifest, ReadOnlyCaseTools]:
    manifest = CaseManifest.model_validate_json(
        (case_dir / "manifest.json").read_text(encoding="utf-8")
    )
    return manifest, ReadOnlyCaseTools(case_dir, set(manifest.files))


def materialize_all(tools: ReadOnlyCaseTools) -> dict[str, str]:
    return {path: tools.read_file(path) for path in tools.list_files()}


def serialized_materials(materials: dict[str, str]) -> str:
    return json.dumps(materials, ensure_ascii=False, sort_keys=True)


def case_fingerprint(case_root: Path, manifest: CaseManifest) -> str:
    digest = hashlib.sha256()
    digest.update((case_root / "manifest.json").read_bytes())
    for relative in sorted(manifest.files):
        digest.update(relative.encode("utf-8"))
        digest.update((case_root / relative).read_bytes())
    return f"sha256:{digest.hexdigest()}"
