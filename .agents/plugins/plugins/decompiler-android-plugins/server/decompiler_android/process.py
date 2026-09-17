from __future__ import annotations

import os
import subprocess
from pathlib import Path


class ProcessError(RuntimeError):
    pass


def run(args: list[str | Path], timeout: int = 3600, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    command = [str(arg) for arg in args]
    clean_env = os.environ.copy()
    if env:
        clean_env.update(env)
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, env=clean_env)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-4000:]
        raise ProcessError(f"Command failed ({result.returncode}): {command[0]}\n{detail}")
    return result
