# Changelog

All notable changes follow semantic versioning.

## 0.1.0 - 2026-09-17

- Add the public `decompiler-android` Marketplace and `decompiler-android-plugins` plugin.
- Add 20 CLI commands for APK inspection, DroidASC, JADX, decoded resources, smali, direct DEX call edges, artifacts, and cache statistics.
- Decode and cache APK resources, including resource listing, text search, binary extraction, ID resolution, and source-reference search.
- Pin DroidASC 0.1.0, JADX 1.5.0, and baksmali 3.0.9 with verified downloads.
- Add a content-addressed, cross-task cache with versioned keys and SQLite indexes.
- Support macOS and Linux with Python 3.10+ and Java 17+.

Cache schema: `1`. There are no earlier cache formats.
