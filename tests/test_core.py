from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / ".agents/plugins/plugins/decompiler-android-plugins"
sys.path.insert(0, str(PLUGIN / "server"))

from decompiler_android.analysis import inspect
from decompiler_android.artifacts import ArtifactStore
from decompiler_android.cache import Cache, stable_key
from decompiler_android.cli import build_parser
from decompiler_android.downloads import DownloadError, _download
from decompiler_android.smali import query_calls


class CacheTests(unittest.TestCase):
    def test_stable_key_is_order_independent_for_dicts(self):
        self.assertEqual(stable_key({"a": 1, "b": 2}), stable_key({"b": 2, "a": 1}))

    def test_lock_serializes_threads(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Cache(Path(directory))
            active = 0
            maximum = 0

            def worker():
                nonlocal active, maximum
                with cache.lock("same"):
                    active += 1
                    maximum = max(maximum, active)
                    threading.Event().wait(0.03)
                    active -= 1

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(maximum, 1)

    def test_cli_exposes_all_analysis_commands(self):
        import argparse

        parser = build_parser()
        subcommands = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        self.assertEqual(len(subcommands.choices), 14)
        self.assertIn("inspect_apk", subcommands.choices)
        self.assertIn("find_direct_callers", subcommands.choices)
        self.assertIn("read_artifact", subcommands.choices)


class ArtifactTests(unittest.TestCase):
    def test_round_trip_and_range(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Cache(Path(directory)))
            artifact = store.write("abcdef")
            result = store.read(artifact["locator"], 2, 3)
            self.assertEqual(result["content"], "cde")
            self.assertEqual(result["next_offset"], 5)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Cache(Path(directory)))
            with self.assertRaises(ValueError):
                store.read("../secret", 0, 1)


class DownloadTests(unittest.TestCase):
    def test_hash_failure_deletes_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            destination = root / "out" / "tool.bin"
            source.write_bytes(b"payload")
            with self.assertRaises(DownloadError):
                _download(source.as_uri(), destination, "0" * 64)
            self.assertFalse(destination.exists())
            self.assertEqual(list(destination.parent.glob("*.part")), [])

    def test_verified_download_is_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            destination = root / "out" / "tool.bin"
            source.write_bytes(b"payload")
            destination.parent.mkdir(parents=True)
            stale = destination.parent / f".{destination.name}.old.part"
            stale.write_bytes(b"interrupted")
            digest = hashlib.sha256(b"payload").hexdigest()
            _download(source.as_uri(), destination, digest)
            self.assertEqual(destination.read_bytes(), b"payload")
            self.assertFalse(stale.exists())


class AnalysisTests(unittest.TestCase):
    def test_inspect_multidex_and_cache_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "fixture.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("AndroidManifest.xml", "manifest")
                archive.writestr("classes.dex", b"dex1")
                archive.writestr("classes2.dex", b"dex2")
                archive.writestr("lib/arm64-v8a/libsample.so", b"elf")
            cache = Cache(root / "cache")
            completed = type("Completed", (), {"stdout": "decoded manifest"})()
            with patch("decompiler_android.analysis.find_aapt2", return_value=None), patch("decompiler_android.analysis.run", return_value=completed):
                first = inspect(cache, str(apk))
                second = inspect(cache, str(apk))
            self.assertEqual(first["data"]["dex_entries"], ["classes.dex", "classes2.dex"])
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])

    def test_call_graph_records_only_explicit_invokes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = Cache(root / "cache")
            smali_root = root / "smali"
            source = smali_root / "sources/classes/com/example/Caller.smali"
            source.parent.mkdir(parents=True)
            source.write_text(""".class public Lcom/example/Caller;
.super Ljava/lang/Object;
.method public run()V
    invoke-static {}, Lcom/example/Target;->hit()V
    const-string v0, \"reflective name\"
    return-void
.end method
""", encoding="utf-8")
            fake_apk = root / "fixture.apk"
            fake_apk.write_bytes(b"apk")
            with patch("decompiler_android.smali.prepare_smali", return_value=(smali_root, "abc", False, True)):
                result = query_calls(cache, str(fake_apk), "Target;->hit()V", "callers")
            artifact = ArtifactStore(cache).read(result["artifact"]["locator"])
            lines = [json.loads(line) for line in artifact["content"].splitlines()]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["caller"], "Lcom/example/Caller;->run()V")
            self.assertEqual(lines[0]["callee"], "Lcom/example/Target;->hit()V")


if __name__ == "__main__":
    unittest.main()
