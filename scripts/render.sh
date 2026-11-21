#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

for tool in python3 java dot curl; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Не найден инструмент: %s. Требования указаны в README.md.\n' "$tool" >&2
        exit 1
    fi
done

version=1.2025.10
expected_sha=4a01ea09b317180fb8e7eef712dfdca725409d2ee1919e4b5adfe9d8362b6fe5
mkdir -p .tools
jar_path="${PLANTUML_JAR:-$PWD/.tools/plantuml-$version.jar}"
if [ ! -f "$jar_path" ]; then
    curl --fail --location --retry 2 --connect-timeout 15 \
        "https://repo.maven.apache.org/maven2/net/sourceforge/plantuml/plantuml/$version/plantuml-$version.jar" \
        --output "$jar_path.part"
    mv "$jar_path.part" "$jar_path"
fi
python3 - "$jar_path" "$expected_sha" <<'PY'
import hashlib, pathlib, sys
actual = hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()
if actual != sys.argv[2]:
    raise SystemExit('SHA-256 PlantUML не совпал с закрепленной версией.')
PY

python3 scripts/export_bpmn.py
python3 - <<'PY'
from pathlib import Path
import subprocess
source = Path('diagrams/01-process.puml').read_text(encoding='utf-8')
dot = source.removeprefix('@startdot\n').removesuffix('@enddot\n')
for fmt in ('svg', 'png'):
    subprocess.run(['dot', '-T' + fmt, '-o', 'diagrams/01-process.' + fmt], input=dot, text=True, check=True)
PY
java -Djava.awt.headless=true -DPLANTUML_LIMIT_SIZE=8192 -jar "$jar_path" \
    -charset UTF-8 -failfast2 -tsvg \
    diagrams/02-context.puml diagrams/03-containers.puml diagrams/04-ml-components.puml
java -Djava.awt.headless=true -DPLANTUML_LIMIT_SIZE=8192 -jar "$jar_path" \
    -charset UTF-8 -failfast2 -tpng \
    diagrams/02-context.puml diagrams/03-containers.puml diagrams/04-ml-components.puml
python3 scripts/check.py --record
