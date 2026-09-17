from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from .analysis import apk_context, envelope
from .artifacts import ArtifactStore
from .cache import Cache, stable_key
from .downloads import ToolManager
from .process import run

CLASS_RE = re.compile(r"^\.class\s+.*?\s+(L[^;]+;)")
METHOD_RE = re.compile(r"^\.method\s+.*?([^\s(]+\([^\s]*)$")
INVOKE_RE = re.compile(r"^\s*(invoke-[^\s]+).*?,\s*(L[^;]+;->[^\s]+)")


def prepare_smali(cache: Cache, apk_path: str) -> tuple[Path, str, bool, bool]:
    apk, digest = apk_context(apk_path)
    manager = ToolManager(cache)
    jars, tool_hit = manager.prepare_baksmali()
    version = manager.versions()["baksmali"]
    output = cache.work / "smali" / digest / version
    marker = output / ".complete"
    if marker.is_file():
        return output, digest, True, tool_hit
    key = stable_key("smali-prepare", digest, version)
    with cache.lock(key):
        if marker.is_file():
            return output, digest, True, tool_hit
        temp = output.with_name(output.name + ".tmp")
        if temp.exists():
            shutil.rmtree(temp)
        temp.mkdir(parents=True, exist_ok=True)
        dex_root = temp / "dex"
        dex_root.mkdir()
        with zipfile.ZipFile(apk) as archive:
            dex_names = sorted(n for n in archive.namelist() if re.fullmatch(r"classes(?:\d+)?\.dex", Path(n).name))
            if not dex_names:
                raise ValueError("APK contains no classes*.dex entries")
            for name in dex_names:
                destination = dex_root / Path(name).name
                destination.write_bytes(archive.read(name))
                target = temp / "sources" / destination.stem
                run(["java", "-cp", os.pathsep.join(map(str, jars)), "com.android.tools.smali.baksmali.Main", "disassemble", destination, "-o", target])
        (temp / ".complete").write_text("complete\n", encoding="utf-8")
        if output.exists():
            shutil.rmtree(output)
        os.replace(temp, output)
    return output, digest, False, tool_hit


def smali_search_files(cache: Cache, apk_path: str, query: str, regex: bool = False, max_results: int = 500) -> dict:
    if max_results < 1 or max_results > 5000:
        raise ValueError("max_results must be between 1 and 5000")
    root, digest, prepare_hit, _ = prepare_smali(cache, apk_path)
    key = stable_key("smali-search", digest, "3.0.9", query, regex, max_results)
    store = ArtifactStore(cache)
    found = cache.cached_result(key)
    if found:
        locator, summary = found
        return envelope(summary, apk_sha256=digest, cache_hit=True, artifact=store.describe(cache.root / locator), tool_versions={"baksmali": "3.0.9"})
    pattern = re.compile(query) if regex else None
    matches = []
    for path in sorted((root / "sources").rglob("*.smali")):
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if (pattern.search(line) if pattern else query in line):
                matches.append({"file": path.relative_to(root).as_posix(), "line": number, "text": line[:1000]})
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break
    artifact = store.write("\n".join(json.dumps(m, ensure_ascii=False) for m in matches) + ("\n" if matches else ""), ".jsonl")
    summary = f"Smali search found {len(matches)} match(es){' (limit reached)' if len(matches) == max_results else ''}."
    cache.put_result(key, artifact["locator"], summary)
    return envelope(summary, apk_sha256=digest, cache_hit=False, artifact=artifact, data={"matches": len(matches)}, tool_versions={"baksmali": "3.0.9"})


def read_method(cache: Cache, apk_path: str, class_name: str, method: str) -> dict:
    root, digest, prepare_hit, _ = prepare_smali(cache, apk_path)
    descriptor = class_name if class_name.startswith("L") else "L" + class_name.replace(".", "/")
    descriptor = descriptor if descriptor.endswith(";") else descriptor + ";"
    relative = descriptor[1:-1] + ".smali"
    candidates = list((root / "sources").glob(f"*/{relative}"))
    if not candidates:
        raise FileNotFoundError(f"Smali class not found: {descriptor}")
    text = candidates[0].read_text(encoding="utf-8", errors="replace").splitlines()
    blocks: list[str] = []
    current: list[str] | None = None
    for line in text:
        if line.startswith(".method "):
            current = [line]
        elif current is not None:
            current.append(line)
            if line.startswith(".end method"):
                header = current[0]
                if method in header:
                    blocks.append("\n".join(current))
                current = None
    if not blocks:
        raise FileNotFoundError(f"Method {method!r} not found in {descriptor}")
    artifact = ArtifactStore(cache).write("\n\n".join(blocks) + "\n", ".smali")
    return envelope(f"Read {len(blocks)} matching smali method block(s) from {descriptor}.", apk_sha256=digest, cache_hit=prepare_hit, artifact=artifact, tool_versions={"baksmali": "3.0.9"})


def ensure_call_index(cache: Cache, apk_path: str) -> tuple[str, bool]:
    root, digest, prepare_hit, _ = prepare_smali(cache, apk_path)
    marker = root / ".callgraph-1-complete"
    if marker.is_file():
        return digest, True
    key = stable_key("callgraph", digest, "baksmali-3.0.9", "explicit-invoke-v1")
    with cache.lock(key):
        if marker.is_file():
            return digest, True
        rows: list[tuple[str, str, str, str, str, str]] = []
        for path in sorted((root / "sources").rglob("*.smali")):
            current_class = None
            current_method = None
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if match := CLASS_RE.match(line):
                    current_class = match.group(1)
                elif line.startswith(".method "):
                    match = METHOD_RE.match(line)
                    current_method = f"{current_class}->{match.group(1)}" if current_class and match else None
                elif line.startswith(".end method"):
                    current_method = None
                elif current_method and (match := INVOKE_RE.match(line)):
                    rows.append((digest, "3.0.9", current_method, match.group(2), match.group(1), path.relative_to(root).as_posix()))
        with cache._connect() as db:
            db.execute("DELETE FROM call_edges WHERE apk_sha256=? AND tool_version=?", (digest, "3.0.9"))
            db.executemany("INSERT OR IGNORE INTO call_edges(apk_sha256,tool_version,caller,callee,instruction,source_file) VALUES(?,?,?,?,?,?)", rows)
        marker.write_text(f"{len(rows)}\n", encoding="utf-8")
    return digest, False


def query_calls(cache: Cache, apk_path: str, method: str, direction: str, max_results: int = 500) -> dict:
    if direction not in {"callers", "callees"}:
        raise ValueError("direction must be callers or callees")
    if max_results < 1 or max_results > 5000:
        raise ValueError("max_results must be between 1 and 5000")
    digest, index_hit = ensure_call_index(cache, apk_path)
    column = "callee" if direction == "callers" else "caller"
    with cache._connect() as db:
        rows = db.execute(
            f"SELECT caller,callee,instruction,source_file FROM call_edges WHERE apk_sha256=? AND tool_version=? AND {column} LIKE ? ORDER BY caller,callee LIMIT ?",
            (digest, "3.0.9", f"%{method}%", max_results),
        ).fetchall()
    values = [{"caller": r[0], "callee": r[1], "instruction": r[2], "source_file": r[3]} for r in rows]
    artifact = ArtifactStore(cache).write("\n".join(json.dumps(v) for v in values) + ("\n" if values else ""), ".jsonl")
    summary = f"Found {len(values)} explicit invoke edge(s) for {direction} query. Virtual dispatch, reflection, JNI, and dynamic loading are not inferred."
    return envelope(summary, apk_sha256=digest, cache_hit=index_hit, artifact=artifact, data={"edges": len(values), "semantics": "explicit DEX invoke targets only"}, tool_versions={"baksmali": "3.0.9", "callgraph_schema": "1"})
