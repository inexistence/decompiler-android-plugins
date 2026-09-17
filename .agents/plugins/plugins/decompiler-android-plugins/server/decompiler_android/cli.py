from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable

from .analysis import (
    droidasc_class,
    droidasc_search,
    envelope,
    find_aapt2,
    inspect,
    jadx_read,
    jadx_search_sources,
    prepare_jadx,
)
from .artifacts import ArtifactStore
from .cache import Cache
from .downloads import ToolManager
from .resources import (
    find_resource_references,
    prepare_resources,
    read_resource,
    resolve_resource,
    resource_inventory,
    search_resources,
)
from .smali import prepare_smali, query_calls, read_method, smali_search_files

Handler = Callable[[argparse.Namespace], dict]


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(json.dumps({"error": "ArgumentError", "message": message}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


def check_environment(_: argparse.Namespace) -> dict:
    cache = Cache()
    java = shutil.which("java")
    java_version = None
    if java:
        result = subprocess.run([java, "-version"], capture_output=True, text=True)
        output = result.stderr or result.stdout
        java_version = output.splitlines()[0] if output else "unknown"
    java_match = re.search(r'version "(?:1\.)?(\d+)', java_version or "")
    java_supported = bool(java_match and int(java_match.group(1)) >= 17)
    versions = ToolManager(cache).versions()
    ready = sys.version_info >= (3, 10) and java_supported and shutil.which("droidasc") is not None
    data = {
        "ready": ready,
        "python": sys.version.split()[0],
        "python_supported": sys.version_info >= (3, 10),
        "java": java,
        "java_version": java_version,
        "java_supported": java_supported,
        "aapt2": find_aapt2(),
        "droidasc": shutil.which("droidasc"),
        "cache": str(cache.root),
        "platforms": ["macOS", "Linux"],
    }
    summary = "Environment is ready." if ready else "Environment is missing Python 3.10+, Java 17+, or DroidASC; inspect the data fields."
    return envelope(summary, data=data, tool_versions=versions)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="decompiler-android", description="Local cached Android APK static analysis")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    commands = parser.add_subparsers(dest="command", required=True)

    _command(commands, "check_environment", "Check Python, Java, AAPT2, DroidASC, and cache readiness", check_environment)

    command = _command(commands, "inspect_apk", "Inspect APK structure and decode its manifest", lambda a: inspect(Cache(), a.apk_path))
    command.add_argument("apk_path")

    command = _command(commands, "search_references", "Find references with DroidASC", lambda a: droidasc_search(Cache(), a.apk_path, a.kind, a.value, a.class_name, a.fuzzy_class))
    command.add_argument("apk_path")
    command.add_argument("kind", choices=("string", "type", "method", "field"))
    command.add_argument("value")
    command.add_argument("--class-name")
    command.add_argument("--fuzzy-class", action="store_true")

    command = _command(commands, "decompile_class", "Decompile one class with DroidASC", lambda a: droidasc_class(Cache(), a.apk_path, a.class_name))
    command.add_argument("apk_path")
    command.add_argument("class_name")

    command = _command(commands, "jadx_prepare", "Prepare and cache a full JADX source tree", _jadx_prepare)
    command.add_argument("apk_path")

    command = _command(commands, "jadx_search", "Search cached JADX source", lambda a: jadx_search_sources(Cache(), a.apk_path, a.query, a.regex, a.max_results))
    _search_arguments(command)

    command = _command(commands, "jadx_read_source", "Read JADX source into an artifact", lambda a: jadx_read(Cache(), a.apk_path, a.source))
    command.add_argument("apk_path")
    command.add_argument("source")

    command = _command(commands, "resources_prepare", "Prepare and cache decoded APK resources", _resources_prepare)
    command.add_argument("apk_path")

    command = _command(commands, "resources_list", "List decoded resource files", lambda a: resource_inventory(Cache(), a.apk_path, a.prefix, a.max_results))
    command.add_argument("apk_path")
    command.add_argument("--prefix", default="")
    command.add_argument("--max-results", type=int, default=2000)

    command = _command(commands, "resources_search", "Search resource paths and decoded text", lambda a: search_resources(Cache(), a.apk_path, a.query, a.regex, a.max_results))
    _search_arguments(command)

    command = _command(commands, "resources_read", "Read a decoded or binary resource into an artifact", lambda a: read_resource(Cache(), a.apk_path, a.resource_path))
    command.add_argument("apk_path")
    command.add_argument("resource_path")

    command = _command(commands, "resolve_resource_id", "Resolve a resource name or numeric ID", lambda a: resolve_resource(Cache(), a.apk_path, a.resource, a.max_results))
    command.add_argument("apk_path")
    command.add_argument("resource")
    command.add_argument("--max-results", type=int, default=500)

    command = _command(commands, "find_resource_references", "Find JADX source references to a resource", lambda a: find_resource_references(Cache(), a.apk_path, a.resource, a.max_results))
    command.add_argument("apk_path")
    command.add_argument("resource")
    command.add_argument("--max-results", type=int, default=500)

    command = _command(commands, "smali_prepare", "Disassemble and cache every DEX with baksmali", _smali_prepare)
    command.add_argument("apk_path")

    command = _command(commands, "smali_search", "Search cached smali source", lambda a: smali_search_files(Cache(), a.apk_path, a.query, a.regex, a.max_results))
    _search_arguments(command)

    command = _command(commands, "smali_read_method", "Extract method blocks from smali", lambda a: read_method(Cache(), a.apk_path, a.class_name, a.method))
    command.add_argument("apk_path")
    command.add_argument("class_name")
    command.add_argument("method")

    command = _command(commands, "find_direct_callers", "Find explicit invoke instructions targeting a method", lambda a: query_calls(Cache(), a.apk_path, a.method, "callers", a.max_results))
    _call_arguments(command)

    command = _command(commands, "find_direct_callees", "Find explicit invoke targets in matching caller methods", lambda a: query_calls(Cache(), a.apk_path, a.method, "callees", a.max_results))
    _call_arguments(command)

    command = _command(commands, "read_artifact", "Read a byte range from a result artifact", _read_artifact)
    command.add_argument("locator")
    command.add_argument("--offset", type=int, default=0)
    command.add_argument("--limit", type=int, default=65536)

    _command(commands, "cache_stats", "Report shared-cache statistics", _cache_stats)
    return parser


def _command(commands: argparse._SubParsersAction, name: str, help_text: str, handler: Handler) -> argparse.ArgumentParser:
    command = commands.add_parser(name, help=help_text, description=help_text)
    command.set_defaults(handler=handler)
    return command


def _search_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("apk_path")
    command.add_argument("query")
    command.add_argument("--regex", action="store_true")
    command.add_argument("--max-results", type=int, default=500)


def _call_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("apk_path")
    command.add_argument("method")
    command.add_argument("--max-results", type=int, default=500)


def _jadx_prepare(args: argparse.Namespace) -> dict:
    cache = Cache()
    root, digest, output_hit, tool_hit = prepare_jadx(cache, args.apk_path)
    return envelope("JADX source tree is ready.", apk_sha256=digest, cache_hit=output_hit,
                    data={"source_root": str(root), "tool_cache_hit": tool_hit}, tool_versions={"jadx": "1.5.0"})


def _smali_prepare(args: argparse.Namespace) -> dict:
    cache = Cache()
    root, digest, output_hit, tool_hit = prepare_smali(cache, args.apk_path)
    return envelope("Smali trees are ready.", apk_sha256=digest, cache_hit=output_hit,
                    data={"smali_root": str(root), "tool_cache_hit": tool_hit}, tool_versions={"baksmali": "3.0.9"})


def _resources_prepare(args: argparse.Namespace) -> dict:
    cache = Cache()
    root, digest, cache_hit = prepare_resources(cache, args.apk_path)
    file_count = sum(1 for path in root.rglob("*") if path.is_file() and not (path.parent == root and re.fullmatch(r"classes(?:\d+)?\.dex", path.name)))
    return envelope("Decoded resource tree is ready.", apk_sha256=digest, cache_hit=cache_hit,
                    data={"resource_root": str(root), "files": file_count},
                    tool_versions={"jadx": "1.5.0", "resource_schema": "full-v1"})


def _read_artifact(args: argparse.Namespace) -> dict:
    cache = Cache()
    data = ArtifactStore(cache).read(args.locator, args.offset, args.limit)
    return envelope(f"Read {len(data['content'].encode('utf-8'))} decoded byte(s) from artifact.", cache_hit=True, data=data)


def _cache_stats(_: argparse.Namespace) -> dict:
    cache = Cache()
    return envelope("Collected cache statistics.", cache_hit=True, data=cache.stats(), tool_versions=ToolManager(cache).versions())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except Exception as error:
        payload = {"error": type(error).__name__, "message": str(error), "command": args.command}
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
