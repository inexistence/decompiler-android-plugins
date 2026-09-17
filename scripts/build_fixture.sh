#!/bin/sh
set -eu

OUTPUT=${1:-tests/fixtures/synthetic.apk}
SDK_ROOT=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}
if [ -z "$SDK_ROOT" ]; then
  echo "ANDROID_HOME or ANDROID_SDK_ROOT is required" >&2
  exit 1
fi
BUILD_TOOLS=$(find "$SDK_ROOT/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -r | head -1)
ANDROID_JAR=$(find "$SDK_ROOT/platforms" -mindepth 2 -maxdepth 2 -name android.jar | sort -r | head -1)
WORK=${TMPDIR:-/tmp}/decompiler-android-fixture-$$
mkdir -p "$WORK/src/com/example" "$WORK/classes/a" "$WORK/classes/b" "$WORK/dex/a" "$WORK/dex/b" "$(dirname "$OUTPUT")"
cat > "$WORK/AndroidManifest.xml" <<'EOF'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.fixture">
  <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="35" />
  <application android:label="Decompiler Fixture" android:hasCode="true" />
</manifest>
EOF
cat > "$WORK/src/com/example/Target.java" <<'EOF'
package com.example;
public final class Target { public static String hit() { return "fixture-token"; } }
EOF
cat > "$WORK/src/com/example/Caller.java" <<'EOF'
package com.example;
public final class Caller { public static String run() { return Target.hit(); } }
EOF
javac --release 8 -classpath "$ANDROID_JAR" -d "$WORK/classes/a" "$WORK/src/com/example/Target.java"
javac --release 8 -classpath "$ANDROID_JAR:$WORK/classes/a" -d "$WORK/classes/b" "$WORK/src/com/example/Caller.java"
"$BUILD_TOOLS/d8" --lib "$ANDROID_JAR" --output "$WORK/dex/a" "$WORK/classes/a/com/example/Target.class"
"$BUILD_TOOLS/d8" --lib "$ANDROID_JAR" --classpath "$WORK/classes/a" --output "$WORK/dex/b" "$WORK/classes/b/com/example/Caller.class"
"$BUILD_TOOLS/aapt2" link -o "$OUTPUT" -I "$ANDROID_JAR" --manifest "$WORK/AndroidManifest.xml" --min-sdk-version 21 --target-sdk-version 35
python3 - "$OUTPUT" "$WORK/dex/a/classes.dex" "$WORK/dex/b/classes.dex" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "a") as archive:
    archive.write(sys.argv[2], "classes.dex")
    archive.write(sys.argv[3], "classes2.dex")
PY
echo "$OUTPUT"
