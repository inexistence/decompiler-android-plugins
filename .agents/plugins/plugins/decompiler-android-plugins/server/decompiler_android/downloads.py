from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .cache import Cache
from .config import tool_manifest


class DownloadError(RuntimeError):
    pass


def _download(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    for stale in destination.parent.glob(f".{destination.name}.*.part"):
        stale.unlink(missing_ok=True)
    temp = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "decompiler-android-plugins/0.1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise DownloadError(f"SHA-256 mismatch for {url}: expected {expected_sha256}, got {actual}")
        os.replace(temp, destination)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


class ToolManager:
    def __init__(self, cache: Cache):
        self.cache = cache
        self.manifest = tool_manifest()

    def versions(self) -> dict[str, str]:
        return {name: entry["version"] for name, entry in self.manifest["tools"].items()}

    def prepare_jadx(self) -> tuple[Path, bool]:
        spec = self.manifest["tools"]["jadx"]
        base = self.cache.tools / "jadx" / spec["version"]
        executable = base / spec["executable"]
        if executable.is_file():
            return executable, True
        with self.cache.lock(f"tool-jadx-{spec['version']}"):
            if executable.is_file():
                return executable, True
            archive = self.cache.tools / "downloads" / spec["filename"]
            if not archive.is_file() or _sha256(archive) != spec["sha256"]:
                archive.unlink(missing_ok=True)
                _download(spec["url"], archive, spec["sha256"])
            temp = base.with_name(base.name + ".tmp")
            if temp.exists():
                shutil.rmtree(temp)
            temp.mkdir(parents=True)
            with zipfile.ZipFile(archive) as zf:
                for member in zf.infolist():
                    target = (temp / member.filename).resolve()
                    target.relative_to(temp.resolve())
                    zf.extract(member, temp)
            executable_in_temp = temp / spec["executable"]
            executable_in_temp.chmod(executable_in_temp.stat().st_mode | 0o111)
            base.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp, base)
        return executable, False

    def prepare_baksmali(self) -> tuple[list[Path], bool]:
        spec = self.manifest["tools"]["baksmali"]
        base = self.cache.tools / "baksmali" / spec["version"]
        paths = [base / item["filename"] for item in spec["artifacts"]]
        if all(p.is_file() and _sha256(p) == item["sha256"] for p, item in zip(paths, spec["artifacts"])):
            return paths, True
        with self.cache.lock(f"tool-baksmali-{spec['version']}"):
            cache_hit = True
            for path, item in zip(paths, spec["artifacts"]):
                if not path.is_file() or _sha256(path) != item["sha256"]:
                    cache_hit = False
                    path.unlink(missing_ok=True)
                    _download(item["url"], path, item["sha256"])
        return paths, cache_hit


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
