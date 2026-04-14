#!/bin/bash
# ============================================================
# import_database.sh - Importa database.js (WorkNC) nel DB
# ============================================================
set -e
cd "$(dirname "$0")"

JS_PATH="${1:-./database.js}"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║  Import database.js (WorkNC) → DB    ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

if [ ! -f "$JS_PATH" ]; then
    echo "  ✗ File non trovato: $JS_PATH"
    echo "  Uso: bash import_database.sh [path/database.js]"
    exit 1
fi

# Trova Python
PYTHON=""
for p in "venv/bin/python3" "venv/bin/python" "python3" "python"; do
    if command -v $p &>/dev/null 2>&1 || [ -f "$p" ]; then
        PYTHON=$p
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "  ✗ Python non trovato"
    exit 1
fi

echo "  Python : $PYTHON"
echo "  Sorgente: $JS_PATH"
echo ""

$PYTHON importers/import_from_database_js.py "$JS_PATH"

echo ""
echo "  ✓ Import completato"
echo ""
