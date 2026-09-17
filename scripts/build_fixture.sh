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
mkdir -p "$WORK/src/com/example" "$WORK/classes/a" "$WORK/classes/b" "$WORK/dex/a" "$WORK/dex/b" "$WORK/res/values" "$WORK/res/layout" "$WORK/gen" "$(dirname "$OUTPUT")"
cat > "$WORK/AndroidManifest.xml" <<'EOF'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.fixture">
  <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="35" />
  <application android:label="@string/app_name" android:hasCode="true" />
</manifest>
EOF
cat > "$WORK/res/values/strings.xml" <<'EOF'
<resources>
  <string name="app_name">Decompiler Fixture</string>
  <string name="fixture_label">fixture-resource-token</string>
</resources>
EOF
cat > "$WORK/res/layout/activity_main.xml" <<'EOF'
<TextView xmlns:android="http://schemas.android.com/apk/res/android"
  android:layout_width="match_parent"
  android:layout_height="wrap_content"
  android:text="@string/fixture_label" />
EOF
cat > "$WORK/src/com/example/Target.java" <<'EOF'
package com.example;
public final class Target { public static String hit() { return "fixture-token"; } }
EOF
cat > "$WORK/src/com/example/Caller.java" <<'EOF'
package com.example;
public final class Caller { public static String run() { return Target.hit(); } }
EOF
cat > "$WORK/src/com/example/ResourceUser.java" <<'EOF'
package com.example;
public final class ResourceUser { public static int label() { return com.example.fixture.R.string.fixture_label; } }
EOF
"$BUILD_TOOLS/aapt2" compile --dir "$WORK/res" -o "$WORK/compiled.zip"
"$BUILD_TOOLS/aapt2" link -o "$OUTPUT" -I "$ANDROID_JAR" --manifest "$WORK/AndroidManifest.xml" --min-sdk-version 21 --target-sdk-version 35 --java "$WORK/gen" "$WORK/compiled.zip"
javac --release 8 -classpath "$ANDROID_JAR" -d "$WORK/classes/a" "$WORK/src/com/example/Target.java" "$WORK/src/com/example/ResourceUser.java" "$WORK/gen/com/example/fixture/R.java"
javac --release 8 -classpath "$ANDROID_JAR:$WORK/classes/a" -d "$WORK/classes/b" "$WORK/src/com/example/Caller.java"
jar cf "$WORK/classes-a.jar" -C "$WORK/classes/a" .
"$BUILD_TOOLS/d8" --lib "$ANDROID_JAR" --output "$WORK/dex/a" "$WORK/classes-a.jar"
"$BUILD_TOOLS/d8" --lib "$ANDROID_JAR" --classpath "$WORK/classes-a.jar" --output "$WORK/dex/b" "$WORK/classes/b/com/example/Caller.class"
python3 - "$OUTPUT" "$WORK/dex/a/classes.dex" "$WORK/dex/b/classes.dex" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "a") as archive:
    archive.write(sys.argv[2], "classes.dex")
    archive.write(sys.argv[3], "classes2.dex")
PY
echo "$OUTPUT"
