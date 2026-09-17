from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from filelock import FileLock

from .config import SCHEMA_VERSION, cache_root


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_key(*parts: object) -> str:
    encoded = json.dumps([SCHEMA_VERSION, *parts], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


class Cache:
    def __init__(self, root: Path | None = None):
        self.root = (root or cache_root()).resolve()
        self.artifacts = self.root / "artifacts"
        self.work = self.root / "work"
        self.tools = self.root / "tools"
        self.locks = self.root / "locks"
        for path in (self.artifacts, self.work, self.tools, self.locks):
            path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "index.sqlite3"
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=60)
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cached_results (
                    cache_key TEXT PRIMARY KEY, locator TEXT NOT NULL, summary TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS call_edges (
                    apk_sha256 TEXT NOT NULL, tool_version TEXT NOT NULL,
                    caller TEXT NOT NULL, callee TEXT NOT NULL,
                    instruction TEXT NOT NULL, source_file TEXT NOT NULL,
                    PRIMARY KEY (apk_sha256, tool_version, caller, callee, instruction, source_file)
                );
                CREATE INDEX IF NOT EXISTS idx_edges_caller ON call_edges(apk_sha256, tool_version, caller);
                CREATE INDEX IF NOT EXISTS idx_edges_callee ON call_edges(apk_sha256, tool_version, callee);
            """)

    @contextmanager
    def lock(self, key: str) -> Iterator[None]:
        with FileLock(str(self.locks / f"{key}.lock"), timeout=3600):
            yield

    def cached_result(self, key: str) -> tuple[str, str] | None:
        with self._connect() as db:
            row = db.execute("SELECT locator, summary FROM cached_results WHERE cache_key=?", (key,)).fetchone()
        if row and (self.root / row[0]).is_file():
            return row[0], row[1]
        return None

    def put_result(self, key: str, locator: str, summary: str) -> None:
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO cached_results(cache_key, locator, summary) VALUES(?,?,?)", (key, locator, summary))

    def stats(self) -> dict:
        files = [p for p in self.root.rglob("*") if p.is_file()]
        with self._connect() as db:
            result_count = db.execute("SELECT COUNT(*) FROM cached_results").fetchone()[0]
            edge_count = db.execute("SELECT COUNT(*) FROM call_edges").fetchone()[0]
        return {"root": str(self.root), "files": len(files), "bytes": sum(p.stat().st_size for p in files), "cached_results": result_count, "call_edges": edge_count}
