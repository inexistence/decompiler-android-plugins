#!/usr/bin/env python3
from __future__ import annotations

import argparse

from decompiler_android.cli import build_parser

EXPECTED = {
    "check_environment", "inspect_apk", "search_references", "decompile_class",
    "jadx_prepare", "jadx_search", "jadx_read_source", "smali_prepare",
    "smali_search", "smali_read_method", "find_direct_callers",
    "find_direct_callees", "read_artifact", "cache_stats", "resources_prepare",
    "resources_list", "resources_search", "resources_read", "resolve_resource_id",
    "find_resource_references",
}

parser = build_parser()
subcommands = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
names = set(subcommands.choices)
if names != EXPECTED:
    raise SystemExit(f"CLI command mismatch: expected {sorted(EXPECTED)}, got {sorted(names)}")
print("\n".join(sorted(names)))
