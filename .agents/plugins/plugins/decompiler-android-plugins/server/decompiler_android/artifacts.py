from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .cache import Cache


class ArtifactStore:
    def __init__(self, cache: Cache):
        self.cache = cache

    def write(self, content: str | bytes, suffix: str = ".txt") -> dict:
        data = content.encode("utf-8") if isinstance(content, str) else content
        digest = hashlib.sha256(data).hexdigest()
        path = self.cache.artifacts / digest[:2] / f"{digest}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temp.write_bytes(data)
            os.replace(temp, path)
        return self.describe(path)

    def describe(self, path: Path) -> dict:
        resolved = path.resolve()
        resolved.relative_to(self.cache.root)
        return {"locator": resolved.relative_to(self.cache.root).as_posix(), "size": resolved.stat().st_size}

    def read(self, locator: str, offset: int = 0, limit: int = 65536) -> dict:
        if offset < 0 or limit < 1 or limit > 1_048_576:
            raise ValueError("offset must be >= 0 and limit must be between 1 and 1048576")
        path = (self.cache.root / locator).resolve()
        path.relative_to(self.cache.artifacts.resolve())
        size = path.stat().st_size
        with path.open("rb") as stream:
            stream.seek(offset)
            data = stream.read(limit)
        return {"locator": locator, "offset": offset, "limit": limit, "size": size, "next_offset": offset + len(data) if offset + len(data) < size else None, "content": data.decode("utf-8", errors="replace")}
