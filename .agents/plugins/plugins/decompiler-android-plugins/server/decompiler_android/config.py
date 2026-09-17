from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_cache_path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "1"


def cache_root() -> Path:
    override = os.environ.get("DECOMPILER_ANDROID_CACHE_DIR")
    root = Path(override).expanduser() if override else user_cache_path("decompiler-android", appauthor=False)
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def tool_manifest() -> dict:
    return json.loads((PLUGIN_ROOT / "tool-manifest.json").read_text(encoding="utf-8"))
