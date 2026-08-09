#!/usr/bin/env bash
# Run all CI pipeline checks locally.
# Mirrors .github/workflows/pythonpackage.yml
set -euo pipefail

cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
VENV_DIR=".venv"
VENV_PY="$VENV_DIR/bin/python"

if [ -x "$VENV_PY" ]; then
    PY="$VENV_PY"
fi

echo "Using: $($PY --version) at $PY"
echo

missing=0
for tool in black pytest bandit mypy; do
    if ! "$PY" -m "$tool" --help >/dev/null 2>&1; then
        echo "Missing '$tool'. Installing from requirements_test.txt..."
        "$PY" -m pip install -r requirements_test.txt
        missing=1
        break
    fi
done

if [ "$missing" -eq 1 ]; then
    for tool in black pytest bandit mypy; do
        if ! "$PY" -m "$tool" --help >/dev/null 2>&1; then
            echo "ERROR: '$tool' still not available after install." >&2
            exit 1
        fi
    done
fi

status=0

echo "==> black --check ."
if "$PY" -m black --check .; then
    echo "[ok] black"
else
    echo "[fail] black"
    status=1
fi
echo

echo "==> pytest --cov=custom_components/lissy --cov-report=term-missing"
if "$PY" -m pytest --cov=custom_components/lissy --cov-report=term-missing; then
    echo "[ok] pytest"
else
    echo "[fail] pytest"
    status=1
fi
echo

echo "==> bandit -r custom_components/ -ll"
if "$PY" -m bandit -r custom_components/ -ll; then
    echo "[ok] bandit"
else
    echo "[fail] bandit"
    status=1
fi
echo

echo "==> mypy custom_components/lissy --ignore-missing-imports"
if "$PY" -m mypy custom_components/lissy --ignore-missing-imports; then
    echo "[ok] mypy"
else
    echo "[fail] mypy"
    status=1
fi
echo

if [ "$status" -eq 0 ]; then
    echo "All checks passed."
else
    echo "One or more checks failed." >&2
fi
exit "$status"