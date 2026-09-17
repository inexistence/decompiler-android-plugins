from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from .artifacts import ArtifactStore
from .cache import Cache, sha256_file, stable_key
from .downloads import ToolManager
from .process import run


def apk_context(apk_path: str) -> tuple[Path, str]:
    path = Path(apk_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"APK does not exist: {path}")
    return path, sha256_file(path)


def envelope(summary: str, *, apk_sha256: str | None = None, cache_hit: bool = False,
             artifact: dict | None = None, data: object | None = None,
             tool_versions: dict | None = None) -> dict:
    result = {
        "apk_sha256": apk_sha256,
        "tool_versions": tool_versions or {},
        "cache_hit": cache_hit,
        "summary": summary,
        "artifact": artifact,
    }
    if data is not None:
        result["data"] = data
    return result


def find_aapt2() -> str | None:
    direct = shutil.which("aapt2")
    if direct:
        return direct
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(variable)
        if not root:
            continue
        build_tools = Path(root).expanduser() / "build-tools"
        if build_tools.is_dir():
            candidates = sorted(build_tools.glob("*/aapt2"), reverse=True)
            if candidates:
                return str(candidates[0])
    return None


def inspect(cache: Cache, apk_path: str) -> dict:
    apk, digest = apk_context(apk_path)
    store = ArtifactStore(cache)
    key = stable_key("inspect", digest, "droidasc-0.1.0")
    found = cache.cached_result(key)
    if found:
        locator, summary = found
        return envelope(summary, apk_sha256=digest, cache_hit=True, artifact=store.describe(cache.root / locator), tool_versions={"droidasc": "0.1.0"})
    with cache.lock(key):
        found = cache.cached_result(key)
        if found:
            locator, summary = found
            return envelope(summary, apk_sha256=digest, cache_hit=True, artifact=store.describe(cache.root / locator), tool_versions={"droidasc": "0.1.0"})
        with zipfile.ZipFile(apk) as archive:
            dex_entries = sorted(n for n in archive.namelist() if re.fullmatch(r"classes(?:\d+)?\.dex", Path(n).name))
            native_entries = sorted(n for n in archive.namelist() if n.startswith("lib/") and n.endswith(".so"))
            zip_data = {"entries": len(archive.infolist()), "dex_entries": dex_entries, "native_libraries": native_entries}
        aapt2 = find_aapt2()
        if aapt2:
            manifest_text = run([aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", apk]).stdout
            manifest_source = "aapt2"
        else:
            manifest_text = run(["droidasc", "getmanifest", apk]).stdout
            manifest_source = "droidasc/androguard"
        payload = json.dumps({"apk": str(apk), "sha256": digest, "manifest_source": manifest_source, **zip_data}, indent=2) + "\n\n" + manifest_text
        artifact = store.write(payload, ".txt")
        summary = f"Inspected APK with {len(dex_entries)} DEX file(s), {len(native_entries)} native library file(s); manifest decoded by {manifest_source}."
        cache.put_result(key, artifact["locator"], summary)
        return envelope(summary, apk_sha256=digest, artifact=artifact, data=zip_data | {"manifest_source": manifest_source}, tool_versions={"droidasc": "0.1.0"})


def droidasc_search(cache: Cache, apk_path: str, kind: str, value: str, class_name: str | None = None,
                    fuzzy_class: bool = False) -> dict:
    if kind not in {"string", "type", "method", "field"}:
        raise ValueError("kind must be string, type, method, or field")
    apk, digest = apk_context(apk_path)
    params = {"kind": kind, "value": value, "class_name": class_name, "fuzzy_class": fuzzy_class}
    key = stable_key("droidasc-search", digest, "0.1.0", params)
    store = ArtifactStore(cache)
    found = cache.cached_result(key)
    if found:
        locator, summary = found
        return envelope(summary, apk_sha256=digest, cache_hit=True, artifact=store.describe(cache.root / locator), tool_versions={"droidasc": "0.1.0"})
    args: list[str | Path] = ["droidasc", "findrefs", apk, kind, value]
    if class_name and kind in {"method", "field"}:
        args += ["--class", class_name]
        if fuzzy_class:
            args.append("--fuzzy-class")
    output = run(args).stdout
    artifact = store.write(output)
    count = sum(1 for line in output.splitlines() if line.strip())
    summary = f"DroidASC reference search completed; artifact contains {count} non-empty output line(s)."
    cache.put_result(key, artifact["locator"], summary)
    return envelope(summary, apk_sha256=digest, artifact=artifact, tool_versions={"droidasc": "0.1.0"})


def droidasc_class(cache: Cache, apk_path: str, class_name: str) -> dict:
    apk, digest = apk_context(apk_path)
    key = stable_key("droidasc-class", digest, "0.1.0", class_name)
    store = ArtifactStore(cache)
    found = cache.cached_result(key)
    if found:
        locator, summary = found
        return envelope(summary, apk_sha256=digest, cache_hit=True, artifact=store.describe(cache.root / locator), tool_versions={"droidasc": "0.1.0"})
    output = run(["droidasc", "getclass", apk, class_name]).stdout
    artifact = store.write(output, ".java")
    summary = f"Decompiled {class_name} with DroidASC."
    cache.put_result(key, artifact["locator"], summary)
    return envelope(summary, apk_sha256=digest, artifact=artifact, tool_versions={"droidasc": "0.1.0"})


def prepare_jadx(cache: Cache, apk_path: str) -> tuple[Path, str, bool, bool]:
    apk, digest = apk_context(apk_path)
    manager = ToolManager(cache)
    executable, tool_hit = manager.prepare_jadx()
    version = manager.versions()["jadx"]
    output = cache.work / "jadx" / digest / f"{version}-full-v1"
    marker = output / ".complete"
    if marker.is_file():
        return output, digest, True, tool_hit
    key = stable_key("jadx-prepare", digest, version)
    with cache.lock(key):
        if marker.is_file():
            return output, digest, True, tool_hit
        temp = output.with_name(output.name + ".tmp")
        if temp.exists():
            shutil.rmtree(temp)
        temp.parent.mkdir(parents=True, exist_ok=True)
        run([executable, "--quiet", "-d", temp, apk])
        (temp / ".complete").write_text("complete\n", encoding="utf-8")
        if output.exists():
            shutil.rmtree(output)
        os.replace(temp, output)
    return output, digest, False, tool_hit


def jadx_search_sources(cache: Cache, apk_path: str, query: str, regex: bool = False, max_results: int = 500) -> dict:
    if max_results < 1 or max_results > 5000:
        raise ValueError("max_results must be between 1 and 5000")
    root, digest, prepare_hit, _ = prepare_jadx(cache, apk_path)
    key = stable_key("jadx-search", digest, "1.5.0", "full-v1", query, regex, max_results)
    store = ArtifactStore(cache)
    found = cache.cached_result(key)
    if found:
        locator, summary = found
        return envelope(summary, apk_sha256=digest, cache_hit=True, artifact=store.describe(cache.root / locator), tool_versions={"jadx": "1.5.0"})
    pattern = re.compile(query) if regex else None
    matches: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".java", ".kt", ".xml"}:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if (pattern.search(line) if pattern else query in line):
                matches.append({"file": path.relative_to(root).as_posix(), "line": number, "text": line[:1000]})
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break
    artifact = store.write("\n".join(json.dumps(m, ensure_ascii=False) for m in matches) + ("\n" if matches else ""), ".jsonl")
    summary = f"JADX search found {len(matches)} match(es){' (limit reached)' if len(matches) == max_results else ''}."
    cache.put_result(key, artifact["locator"], summary)
    return envelope(summary, apk_sha256=digest, cache_hit=False, artifact=artifact, data={"matches": len(matches)}, tool_versions={"jadx": "1.5.0"})


def jadx_read(cache: Cache, apk_path: str, source: str) -> dict:
    root, digest, prepare_hit, _ = prepare_jadx(cache, apk_path)
    candidate = source.replace(".", "/") if "/" not in source and not source.endswith((".java", ".kt")) else source
    options: list[Path] = []
    supplied = (root / candidate).resolve()
    try:
        supplied.relative_to(root.resolve())
        if supplied.is_file():
            options.append(supplied)
    except ValueError:
        pass
    if not options:
        stem = candidate.removesuffix(".java").removesuffix(".kt")
        for suffix in (".java", ".kt"):
            options.extend(root.rglob(Path(stem).name + suffix))
        options = [p for p in options if p.as_posix().endswith(stem + p.suffix)] or options
    if not options:
        raise FileNotFoundError(f"No JADX source matched: {source}")
    if len(options) > 1:
        raise ValueError("Source is ambiguous; use one of: " + ", ".join(p.relative_to(root).as_posix() for p in options[:20]))
    store = ArtifactStore(cache)
    artifact = store.write(options[0].read_bytes(), options[0].suffix)
    return envelope(f"Read JADX source {options[0].relative_to(root).as_posix()}.", apk_sha256=digest, cache_hit=prepare_hit, artifact=artifact, tool_versions={"jadx": "1.5.0"})
