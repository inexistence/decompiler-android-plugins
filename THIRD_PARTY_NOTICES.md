# Third-party notices

This repository does not redistribute the analysis engines in Git. At runtime it downloads or installs the following fixed direct dependencies. Each project remains under its own license.

| Component | Version | Source | License |
| --- | --- | --- | --- |
| DroidASC | 0.1.0 | <https://pypi.org/project/droidasc/0.1.0/> | Apache-2.0 |
| JADX | 1.5.0 | <https://github.com/skylot/jadx/releases/tag/v1.5.0> | Apache-2.0 |
| smali / baksmali / dexlib2 / smali-util | 3.0.9 | <https://github.com/google/smali/tree/3.0.9> | BSD-3-Clause |
| Androguard | 4.1.3 | <https://pypi.org/project/androguard/4.1.3/> | Apache-2.0 |
| platformdirs | 4.11.9 | <https://pypi.org/project/platformdirs/4.11.9/> | MIT |
| filelock | 3.32.7 | <https://pypi.org/project/filelock/3.32.7/> | Unlicense |
| Guava and helper artifacts | 31.1-android | <https://github.com/google/guava> | Apache-2.0 |
| JCommander | 1.64 | <https://jcommander.org/> | Apache-2.0 |
| JSR-305 annotations | 3.0.2 | <https://github.com/amaembo/jsr-305> | BSD-3-Clause |
| Checker Framework annotations | 3.12.0 | <https://checkerframework.org/> | MIT |
| Error Prone annotations | 2.11.0 | <https://errorprone.info/> | Apache-2.0 |
| J2ObjC annotations | 1.3 | <https://github.com/google/j2objc> | Apache-2.0 |

Androguard installs additional transitive Python packages. Their metadata and license texts are available in the plugin-managed virtual environment through `pip show <package>` and the respective package distributions. The authoritative download URLs, versions, hashes, and per-artifact licenses for Java tools are in `tool-manifest.json`.
