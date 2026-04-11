#!/bin/bash
# ============================================================
# start.sh - Avvio completo Tool DB Manager
# Esegue: git pull, libera le porte, avvia i servizi
# ============================================================

set -e
cd "$(dirname "$0")"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║      Tool DB Manager - Avvio         ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. Aggiorna dal repository ─────────────────────────────
echo "  [1/4] Aggiornamento dal repository..."
git fetch origin main1 --quiet
git reset --hard origin/main1 --quiet
echo "  ✓ Codice aggiornato"

# ── 2. Carica variabili ambiente ───────────────────────────
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs) 2>/dev/null
fi

# ── 3. Libera le porte 5000 e 5001 ────────────────────────
echo "  [2/4] Libero le porte..."
for PORT in 5000 5001; do
    PIDS=$(lsof -ti :$PORT 2>/dev/null) || true
    if [ -n "$PIDS" ]; then
        echo "  ✓ Porto $PORT: termino PID $PIDS"
        kill -9 $PIDS 2>/dev/null || true
        sleep 0.5
    fi
done
echo "  ✓ Porte libere"

# ── 4. Trova Python ────────────────────────────────────────
echo "  [3/4] Cerco Python..."
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
echo "  ✓ Python: $PYTHON"

# ── 5. Assicura che il DB esista ───────────────────────────
mkdir -p database
if [ ! -f database/tool_master.db ]; then
    echo "  [3/4] DB non trovato, lo creo..."
    $PYTHON -c "
import sqlite3
with open('database/schema.sql', encoding='utf-8') as f: sql = f.read()
conn = sqlite3.connect('database/tool_master.db')
conn.executescript(sql)
conn.commit()
conn.close()
print('  ✓ Database creato')
"
fi

# ── 6. Avvia i servizi ─────────────────────────────────────
echo "  [4/4] Avvio servizi..."
mkdir -p logs

# App principale (porta 5000)
nohup $PYTHON ui/app.py > logs/app_main.log 2>&1 &
PID_MAIN=$!

# Format Learner (porta 5001) - avviato direttamente come modulo
LEARNER_SCRIPT=$(cat <<'PYEOF'
import sys, os
_base = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
sys.path.insert(0, os.path.join(_base, 'learner'))
from learner.app_learner import app
app.run(debug=False, port=5001, host='127.0.0.1')
PYEOF
)
nohup $PYTHON learner/app_learner_prod.py > logs/app_learner.log 2>&1 &
PID_LEARNER=$!

# Salva i PID per stop.sh
echo $PID_MAIN > .pid_main
echo $PID_LEARNER > .pid_learner

# Aspetta che i servizi partano
sleep 3

# Verifica
MAIN_OK=false
LEARNER_OK=false
for i in 1 2 3 4 5; do
    if curl -s http://localhost:5000 > /dev/null 2>&1; then MAIN_OK=true; fi
    if curl -s http://localhost:5001 > /dev/null 2>&1; then LEARNER_OK=true; fi
    if $MAIN_OK && $LEARNER_OK; then break; fi
    sleep 1
done

echo ""
if $MAIN_OK; then
    echo "  ✓ App principale  ->  http://localhost:5000"
else
    echo "  ✗ App principale non risponde (vedi logs/app_main.log)"
fi
if $LEARNER_OK; then
    echo "  ✓ Format Learner  ->  http://localhost:5001"
else
    echo "  ✗ Format Learner non risponde (vedi logs/app_learner.log)"
fi
echo ""
echo "  Per fermare: bash stop.sh"
echo ""
