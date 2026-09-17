# decompiler-android-plugins

A public Codex Marketplace containing a Skill-guided Android APK static-analysis CLI. It combines focused DroidASC queries, full JADX source generation, baksmali disassembly, and an explicit DEX call-edge index.

The plugin reads only APK paths supplied by the user. APKs, paths, generated sources, and usage data stay on the local machine. The plugin has no telemetry and does not upload analysis material.

## Requirements

- macOS or Linux
- Python 3.10 or newer, with `venv`
- Java 17 or newer
- HTTPS access on first use to PyPI, GitHub Releases, Google Maven, and Maven Central
- Optional: Android SDK Build Tools (`aapt2`) discoverable from `ANDROID_HOME`, `ANDROID_SDK_ROOT`, or `PATH`

The first CLI invocation creates a private virtual environment in the plugin cache. The first JADX or smali request downloads the exact versions and files recorded in `tool-manifest.json`, verifies every SHA-256, and atomically installs them. Later tasks reuse these files offline.

## Install

```bash
git clone https://github.com/inexistence/decompiler-android-plugins.git
codex plugin marketplace add <clone-path>/.agents/plugins
codex plugin add decompiler-android-plugins@decompiler-android
```

Start a new Codex task after installation and ask Codex to inspect a local APK. The bundled Skill starts with the `check_environment` CLI command and chooses narrower commands as analysis proceeds.

## Upgrade

Check out the desired release tag, refresh the local Marketplace, reinstall the plugin, and start a new task:

```bash
git -C <clone-path> fetch --tags
git -C <clone-path> checkout v0.1.0
codex plugin remove decompiler-android-plugins@decompiler-android
codex plugin add decompiler-android-plugins@decompiler-android
```

The cache key includes schema and tool versions. Changing a tool version naturally creates a separate cache entry; compatible cached results remain reusable.

## Uninstall

```bash
codex plugin remove decompiler-android-plugins@decompiler-android
codex plugin marketplace remove decompiler-android
```

Uninstalling does not delete analysis caches. See cache management below.

## CLI commands

| Area | Commands |
| --- | --- |
| Environment and APK | `check_environment`, `inspect_apk` |
| DroidASC | `search_references`, `decompile_class` |
| JADX | `jadx_prepare`, `jadx_search`, `jadx_read_source` |
| Smali | `smali_prepare`, `smali_search`, `smali_read_method` |
| Direct calls | `find_direct_callers`, `find_direct_callees` |
| Artifacts and cache | `read_artifact`, `cache_stats` |

The entry point is inside the installed plugin at `scripts/decompiler-android`. For development from a clone:

```bash
.agents/plugins/plugins/decompiler-android-plugins/scripts/decompiler-android check_environment
.agents/plugins/plugins/decompiler-android-plugins/scripts/decompiler-android inspect_apk ./app.apk
.agents/plugins/plugins/decompiler-android-plugins/scripts/decompiler-android search_references ./app.apk string token
.agents/plugins/plugins/decompiler-android-plugins/scripts/decompiler-android jadx_search ./app.apk Authorization
.agents/plugins/plugins/decompiler-android-plugins/scripts/decompiler-android find_direct_callers ./app.apk 'Lcom/example/Main;->run()V'
```

Run `decompiler-android <command> --help` for command-specific options. Commands write one structured JSON object to stdout. Errors use a JSON object on stderr and a nonzero exit status.

Every analysis result includes the APK SHA-256, relevant tool versions, whether reusable work was found in cache, a short summary, and an artifact locator when output is large. Use `read_artifact` with byte offsets to page through artifacts.

The direct call tools record only concrete targets present in DEX `invoke-*` instructions. They do not resolve virtual or interface dispatch and do not infer reflection, JNI, or dynamically loaded DEX behavior.

## Cache management

The default cache follows the operating system through Python `platformdirs`:

- macOS: `~/Library/Caches/decompiler-android`
- Linux: `${XDG_CACHE_HOME:-~/.cache}/decompiler-android`

Set `DECOMPILER_ANDROID_CACHE_DIR` before starting Codex to use another location. `cache_stats` reports the active directory and its size. Close Codex tasks using the plugin before deleting the cache directory. The next use recreates it and downloads required tools again.

The cache contains downloaded tools, decompiled source, smali, query artifacts, and a SQLite index. Files are keyed by APK content and tool/schema versions. Downloads and expensive preparation steps use cross-process locks, temporary files, and atomic renames.

## Network and offline use

First use requires the network for the Python environment and whichever analysis engines are requested. After the runtime and engines have been prepared, cached APK analyses work offline. A new Python version, plugin runtime version, or previously unused engine can require another download.

All executable downloads use fixed URLs. JADX and baksmali files are checked against the SHA-256 values in [`tool-manifest.json`](.agents/plugins/plugins/decompiler-android-plugins/tool-manifest.json). A mismatch deletes the partial file and fails with the expected and actual hashes.

## Troubleshooting

- **Python is too old:** set `DECOMPILER_ANDROID_PYTHON` to a Python 3.10+ executable before launching Codex.
- **`venv` is unavailable on Ubuntu:** install the matching `python3-venv` package.
- **Java is missing or old:** install a Java 17 JRE/JDK and ensure `java` is on `PATH`.
- **The first launch is slow:** the private environment includes Androguard and its dependencies. It is reused after successful setup.
- **A download was interrupted:** retry. `.part` files are never treated as installed, and verified downloads use atomic replacement.
- **AAPT2 is absent:** manifest decoding automatically falls back to DroidASC/Androguard.
- **Decompiler output looks incomplete:** obfuscation, unsupported bytecode, native libraries, reflection, and dynamic loading limit static decompilation. Check smali before drawing a strong conclusion.
- **A source name is ambiguous:** pass the path returned by `jadx_search` to `jadx_read_source`.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q .agents/plugins/plugins/decompiler-android-plugins/server
```

CI also checks the Marketplace and plugin manifests, Skill frontmatter, CLI command list, synthetic multidex fixture, smali output, and direct call graph.

The canonical Marketplace file is `.agents/plugins/marketplace.json`. The nested symlink at `.agents/plugins/.agents/plugins/marketplace.json` is a discovery shim for Codex CLI versions that treat the path passed to `marketplace add` as a repository root. It keeps the documented `<clone-path>/.agents/plugins` installation command working while maintaining one manifest source.

## License

Repository code is licensed under Apache-2.0. Downloaded tools and Python dependencies keep their own licenses; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
