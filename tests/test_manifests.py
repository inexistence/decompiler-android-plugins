from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / ".agents/plugins/plugins/decompiler-android-plugins"


class ManifestTests(unittest.TestCase):
    def test_marketplace_contract(self):
        data = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual(data["name"], "decompiler-android")
        entry = data["plugins"][0]
        self.assertEqual(entry["source"]["path"], "./plugins/decompiler-android-plugins")
        self.assertEqual(entry["policy"], {"installation": "AVAILABLE", "authentication": "ON_INSTALL"})
        self.assertEqual(entry["category"], "Engineering")
        discovery_manifest = ROOT / ".agents/plugins/.agents/plugins/marketplace.json"
        self.assertTrue(discovery_manifest.is_symlink())
        self.assertEqual(discovery_manifest.resolve(), (ROOT / ".agents/plugins/marketplace.json").resolve())

    def test_plugin_contract(self):
        data = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(data["name"], PLUGIN.name)
        self.assertEqual(data["version"], "0.1.0")
        self.assertNotIn("mcpServers", data)
        self.assertFalse((PLUGIN / ".mcp.json").exists())

    def test_skill_contract(self):
        skill = (PLUGIN / "skills/android-decompiler/SKILL.md").read_text()
        self.assertTrue(skill.startswith("---\nname: android-decompiler\n"))
        self.assertIn("description:", skill.split("---", 2)[1])

    def test_downloads_are_fixed_and_hashed(self):
        data = json.loads((PLUGIN / "tool-manifest.json").read_text())
        serialized = json.dumps(data)
        self.assertNotIn("/latest", serialized)
        for name, tool in data["tools"].items():
            artifacts = tool.get("artifacts", [tool])
            for artifact in artifacts:
                if "url" in artifact:
                    self.assertTrue(artifact["url"].startswith("https://"), name)
                    self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
