---
name: android-decompiler
description: Analyze a user-provided local Android APK by orchestrating the bundled decompiler-android CLI with cached DroidASC, JADX, smali, and explicit DEX call edges.
---

# Android Decompiler

Use the bundled CLI only for APK paths the user explicitly provides or authorizes. Resolve it from this Skill directory as `../../scripts/decompiler-android`, convert that path to an absolute path, and quote both the executable and user-provided paths.

Run `decompiler-android check_environment` first, then `decompiler-android inspect_apk <apk-path>`. Every successful command prints one JSON object. Large output is stored under `artifact.locator`; page it with `decompiler-android read_artifact <locator> --offset <n> --limit <n>`.

Prefer the smallest command that answers the question:

- `search_references <apk> <string|type|method|field> <value>` and `decompile_class <apk> <class>` handle focused questions.
- `jadx_prepare <apk>`, `jadx_search <apk> <query>`, and `jadx_read_source <apk> <source>` handle broader readable-source exploration.
- `smali_prepare <apk>`, `smali_search <apk> <query>`, and `smali_read_method <apk> <class> <method>` provide exact bytecode evidence.
- `find_direct_callers <apk> <method>` and `find_direct_callees <apk> <method>` report explicit `invoke-*` edges.
- `cache_stats` reports cache use. Do not rerun expensive preparation merely to retrieve a large result.

Read command-specific options with `decompiler-android <command> --help`. Check the process exit status. On failure, parse the JSON object written to stderr and explain the actionable error instead of guessing.

Treat decompiler output as evidence that may be incomplete or syntactically imperfect. Report obfuscation and native code when they limit a conclusion. A direct call edge does not prove runtime dispatch: do not infer interface implementations, reflective calls, JNI targets, or dynamically loaded code from it.

The CLI keeps APKs and generated artifacts on the local machine. Do not upload them or paste large decompiled bodies unless the user requests that content.
