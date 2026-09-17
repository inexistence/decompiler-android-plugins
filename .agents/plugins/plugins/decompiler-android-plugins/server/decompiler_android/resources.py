from __future__ import annotations

import json
import mimetypes
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .analysis import envelope, prepare_jadx
from .artifacts import ArtifactStore
from .cache import Cache, stable_key

TEXT_SUFFIXES = {".xml", ".svg", ".txt", ".json", ".html", ".htm", ".css", ".js", ".properties", ".csv", ".md"}
JADX_RESOURCE_SCHEMA = "full-v1"


def prepare_resources(cache: Cache, apk_path: str) -> tuple[Path, str, bool]:
    root, digest, cache_hit, _ = prepare_jadx(cache, apk_path)
    resources = (root / "resources").resolve()
    if not resources.is_dir():
        raise FileNotFoundError("JADX produced no resources directory for this APK")
    return resources, digest, cache_hit


def resource_inventory(cache: Cache, apk_path: str, prefix: str = "", max_results: int = 2000) -> dict:
    _validate_limit(max_results)
    root, digest, prepare_hit = prepare_resources(cache, apk_path)
    normalized_prefix = prefix.lstrip("/")
    values = []
    total_files = 0
    total_bytes = 0
    matched_files = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or _is_dex_copy(path, root):
            continue
        relative = path.relative_to(root).as_posix()
        total_files += 1
        total_bytes += path.stat().st_size
        if normalized_prefix and not relative.startswith(normalized_prefix):
            continue
        matched_files += 1
        if len(values) < max_results:
            values.append(_file_metadata(path, root))
    artifact = ArtifactStore(cache).write("\n".join(json.dumps(value, ensure_ascii=False) for value in values) + ("\n" if values else ""), ".jsonl")
    summary = f"Listed {len(values)} resource file(s) from {total_files} total resource files."
    return envelope(summary, apk_sha256=digest, cache_hit=prepare_hit, artifact=artifact,
                    data={"matches": len(values), "matched_files": matched_files, "total_files": total_files, "total_bytes": total_bytes, "limit_reached": matched_files > len(values)},
                    tool_versions={"jadx": "1.5.0", "resource_schema": JADX_RESOURCE_SCHEMA})


def search_resources(cache: Cache, apk_path: str, query: str, regex: bool = False, max_results: int = 500) -> dict:
    _validate_limit(max_results)
    if not query:
        raise ValueError("query must not be empty")
    root, digest, _ = prepare_resources(cache, apk_path)
    key = stable_key("resources-search", digest, JADX_RESOURCE_SCHEMA, query, regex, max_results)
    store = ArtifactStore(cache)
    found = cache.cached_result(key)
    if found:
        locator, summary = found
        return envelope(summary, apk_sha256=digest, cache_hit=True, artifact=store.describe(cache.root / locator),
                        tool_versions={"jadx": "1.5.0", "resource_schema": JADX_RESOURCE_SCHEMA})
    pattern = re.compile(query) if regex else None
    matches = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or _is_dex_copy(path, root):
            continue
        relative = path.relative_to(root).as_posix()
        if _matches(relative, query, pattern):
            matches.append({"file": relative, "line": None, "text": relative, "match": "path"})
        if len(matches) >= max_results:
            break
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 16 * 1024 * 1024:
            continue
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for number, line in enumerate(stream, 1):
                if _matches(line, query, pattern):
                    matches.append({"file": relative, "line": number, "text": line.rstrip()[:1000], "match": "content"})
                    if len(matches) >= max_results:
                        break
        if len(matches) >= max_results:
            break
    artifact = store.write("\n".join(json.dumps(value, ensure_ascii=False) for value in matches) + ("\n" if matches else ""), ".jsonl")
    summary = f"Resource search found {len(matches)} match(es){' (limit reached)' if len(matches) == max_results else ''}."
    cache.put_result(key, artifact["locator"], summary)
    return envelope(summary, apk_sha256=digest, artifact=artifact, data={"matches": len(matches)},
                    tool_versions={"jadx": "1.5.0", "resource_schema": JADX_RESOURCE_SCHEMA})


def read_resource(cache: Cache, apk_path: str, resource_path: str) -> dict:
    root, digest, prepare_hit = prepare_resources(cache, apk_path)
    candidate = resource_path.removeprefix("resources/").lstrip("/")
    path = (root / candidate).resolve()
    path.relative_to(root.resolve())
    if not path.is_file() or _is_dex_copy(path, root):
        raise FileNotFoundError(f"Resource does not exist: {resource_path}")
    artifact = ArtifactStore(cache).write_file(path)
    metadata = _file_metadata(path, root)
    metadata["local_artifact_path"] = str((cache.root / artifact["locator"]).resolve())
    return envelope(f"Read resource {metadata['path']} ({metadata['size']} bytes).", apk_sha256=digest,
                    cache_hit=prepare_hit, artifact=artifact, data=metadata,
                    tool_versions={"jadx": "1.5.0", "resource_schema": JADX_RESOURCE_SCHEMA})


def resolve_resource(cache: Cache, apk_path: str, resource: str, max_results: int = 500) -> dict:
    _validate_limit(max_results)
    root, digest, prepare_hit = prepare_resources(cache, apk_path)
    records = _public_resources(root)
    terms = _resource_terms(resource)
    matches = [record for record in records if _record_matches(record, terms)][:max_results]
    artifact = ArtifactStore(cache).write("\n".join(json.dumps(value, ensure_ascii=False) for value in matches) + ("\n" if matches else ""), ".jsonl")
    summary = f"Resolved {len(matches)} resource table entr{'y' if len(matches) == 1 else 'ies'} for {resource!r}."
    return envelope(summary, apk_sha256=digest, cache_hit=prepare_hit, artifact=artifact,
                    data={"matches": len(matches), "resources": matches[:50]},
                    tool_versions={"jadx": "1.5.0", "resource_schema": JADX_RESOURCE_SCHEMA})


def find_resource_references(cache: Cache, apk_path: str, resource: str, max_results: int = 500) -> dict:
    _validate_limit(max_results)
    jadx_root, digest, prepare_hit, _ = prepare_jadx(cache, apk_path)
    records = [record for record in _public_resources(jadx_root / "resources") if _record_matches(record, _resource_terms(resource))]
    terms = {resource, resource.removeprefix("@")}
    for record in records:
        terms.update({record["id"], str(int(record["id"], 16)), record["name"], f"R.{record['type']}.{record['name']}"})
    terms.discard("")
    matches = []
    sources = jadx_root / "sources"
    for path in sorted(path for path in sources.rglob("*") if path.suffix.lower() in {".java", ".kt"}):
        if path.name == "R.java":
            continue
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for number, line in enumerate(stream, 1):
                matched = sorted(term for term in terms if term in line)
                if matched:
                    matches.append({"file": path.relative_to(jadx_root).as_posix(), "line": number, "text": line.rstrip()[:1000], "terms": matched})
                    if len(matches) >= max_results:
                        break
        if len(matches) >= max_results:
            break
    artifact = ArtifactStore(cache).write("\n".join(json.dumps(value, ensure_ascii=False) for value in matches) + ("\n" if matches else ""), ".jsonl")
    summary = f"Found {len(matches)} JADX source reference(s) for resource {resource!r}."
    return envelope(summary, apk_sha256=digest, cache_hit=prepare_hit, artifact=artifact,
                    data={"matches": len(matches), "resolved_resources": records[:50]},
                    tool_versions={"jadx": "1.5.0", "resource_schema": JADX_RESOURCE_SCHEMA})


def _public_resources(root: Path) -> list[dict]:
    public_xml = root / "res" / "values" / "public.xml"
    if not public_xml.is_file():
        return []
    records = []
    for element in ET.parse(public_xml).getroot().findall("public"):
        if all(element.get(key) for key in ("type", "name", "id")):
            records.append({"type": element.get("type"), "name": element.get("name"), "id": element.get("id")})
    return records


def _resource_terms(value: str) -> set[str]:
    normalized = value.strip().removeprefix("@").lower()
    if not normalized:
        raise ValueError("resource must not be empty")
    terms = {normalized}
    try:
        number = int(normalized, 0)
        terms.update({str(number), f"0x{number:08x}"})
    except ValueError:
        pass
    if "/" in normalized:
        terms.add(normalized.split("/", 1)[1])
    return terms


def _record_matches(record: dict, terms: set[str]) -> bool:
    values = {record["id"].lower(), record["name"].lower(), f"{record['type']}/{record['name']}".lower()}
    try:
        values.add(str(int(record["id"], 16)))
    except ValueError:
        pass
    return bool(values & terms)


def _file_metadata(path: Path, root: Path) -> dict:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "media_type": media_type, "text": path.suffix.lower() in TEXT_SUFFIXES}


def _matches(value: str, query: str, pattern: re.Pattern | None) -> bool:
    return bool(pattern.search(value)) if pattern else query in value


def _is_dex_copy(path: Path, root: Path) -> bool:
    return path.parent == root and re.fullmatch(r"classes(?:\d+)?\.dex", path.name) is not None


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > 5000:
        raise ValueError("max_results must be between 1 and 5000")
