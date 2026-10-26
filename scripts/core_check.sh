#!/usr/bin/env bash
# Exports the integration into a Home Assistant core checkout and runs core's own checks on it: ruff, hassfest,
# pylint (with core's plugins), mypy and the tests. The checkout needs core's dev requirements in its venv.
set -euo pipefail

core="${1:?usage: core_check.sh <home-assistant core checkout>}"
core="$(cd "$core" && pwd)"
here="$(cd "$(dirname "$0")/.." && pwd)"

python3 "$here/scripts/core_export.py" "$core"
cd "$core"
export PATH="$core/venv/bin:$PATH"
paths=(homeassistant/components/hearth tests/components/hearth)

for _ in 1 2; do
  ruff check "${paths[@]}" --fix --quiet >/dev/null 2>&1 || true
  ruff format "${paths[@]}" --quiet
done

echo "== ruff"
ruff check "${paths[@]}"
ruff format --check "${paths[@]}"
python - <<'PY'
from pathlib import Path

path, entry = Path(".strict-typing"), "homeassistant.components.hearth.*"
lines = path.read_text().splitlines()
if entry not in lines:
    after = max(i for i, line in enumerate(lines) if line.startswith("homeassistant.components.") and line < entry)
    lines.insert(after + 1, entry)
    path.write_text("\n".join(lines) + "\n")
PY
echo "== hassfest"
python -m script.hassfest --integration-path homeassistant/components/hearth
echo "== pylint"
pylint "${paths[@]}"
echo "== mypy"
# Only the integration's own errors count: mypy follows imports into components this venv lacks dependencies for.
mypy_out="$(mktemp)"
mypy homeassistant/components/hearth > "$mypy_out" || true
cat "$mypy_out"
if grep -q "^homeassistant/components/hearth/" "$mypy_out"; then
  exit 1
fi
echo "== pytest"
python -m script.translations develop --all >/dev/null
pytest tests/components/hearth --cov=homeassistant.components.hearth --cov-report=term-missing -q -p no:cacheprovider
