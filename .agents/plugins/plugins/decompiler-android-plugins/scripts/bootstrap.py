#!/usr/bin/env python3
"""Create the private runtime under a process-safe macOS/Linux file lock."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import venv
from pathlib import Path


def download_verified(url: str, destination: Path, expected: str) -> None:
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    for stale in destination.parent.glob(f".{destination.name}.*.part"):
        stale.unlink(missing_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "decompiler-android-plugins/0.1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch for {url}: expected {expected}, got {actual}")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: bootstrap.py PLUGIN_ROOT CACHE_ROOT")
    plugin_root = Path(sys.argv[1]).resolve()
    cache_root = Path(sys.argv[2]).expanduser().resolve()
    tag = f"py{sys.version_info.major}.{sys.version_info.minor}"
    runtime_root = cache_root / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    environment = runtime_root / tag
    ready = environment / ".ready-0.1.0-cli2"
    with (runtime_root / ".bootstrap.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if ready.is_file():
            return
        manifest = json.loads((plugin_root / "tool-manifest.json").read_text(encoding="utf-8"))
        droidasc = manifest["tools"]["droidasc"]
        wheel = cache_root / "tools" / "downloads" / droidasc["filename"]
        download_verified(droidasc["url"], wheel, droidasc["sha256"])
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = environment / "bin" / "python"
        subprocess.run(
            [python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", plugin_root / "requirements.txt", wheel],
            check=True,
            stdout=sys.stderr,
        )
        temporary = ready.with_name(f".{ready.name}.{os.getpid()}.tmp")
        temporary.write_text("ready\n", encoding="utf-8")
        os.replace(temporary, ready)


if __name__ == "__main__":
    main()
