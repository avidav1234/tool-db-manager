#!/bin/bash
# ============================================================
# start.sh — Avvio Tool DB Manager
# Uso: ./start.sh
# ============================================================

# Vai sempre nella cartella del progetto, qualunque sia la CWD
cd "$(dirname "$0")"
ROOT="$(pwd)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║       Tool DB Manager v0.1           ║"
echo "╚══════════════════════════════════════╝"
echo ""

# --- Verifica Python ---
if command -v python3.12 &>/dev/null; then
    PY="python3.12"
elif command -v python3.11 &>/dev/null; then
    PY="python3.11"
elif command -v python3 &>/dev/null; then
    PY="python3"
else
    echo "❌  Python 3 non trovato. Installa con: brew install python@3.12"
    exit 1
fi
echo "✓  Python: $($PY --version)"

# --- Crea venv se non esiste ---
if [ ! -d "$ROOT/venv" ]; then
    echo "→  Creo ambiente virtuale..."
    $PY -m venv "$ROOT/venv"
fi

# --- Attiva venv ---
source "$ROOT/venv/bin/activate"

# --- Installa dipendenze se necessario ---
if ! python -c "import flask" &>/dev/null; then
    echo "→  Installo dipendenze..."
    pip install -q flask pandas openpyxl schedule
fi

# --- Inizializza DB se non esiste ---
if [ ! -f "$ROOT/database/tool_master.db" ]; then
    echo "→  Inizializzo database..."
    python - <<'PYEOF'
import sqlite3, os, sys
root = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv[0] != '-' else os.getcwd()
schema = os.path.join(root, 'database', 'schema.sql')
db     = os.path.join(root, 'database', 'tool_master.db')
os.makedirs(os.path.dirname(db), exist_ok=True)
with open(schema) as f:
    sql = f.read()
conn = sqlite3.connect(db)
conn.executescript(sql)
conn.commit()
print("  DB creato:", db)
PYEOF
fi

echo ""
echo "┌─────────────────────────────────────────┐"
echo "│  App principale → http://localhost:5000  │"
echo "│  Format Learner → http://localhost:5001  │"
echo "└─────────────────────────────────────────┘"
echo ""
echo "  Premi Ctrl+C per fermare entrambi"
echo ""

# --- Avvia Format Learner in background ---
python "$ROOT/learner/app_learner.py" &
LEARNER_PID=$!

# --- Avvia app principale in foreground ---
python "$ROOT/ui/app.py"

# --- Cleanup al Ctrl+C ---
kill $LEARNER_PID 2>/dev/null
echo ""
echo "Applicazioni fermate."
