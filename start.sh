#!/bin/bash
# ============================================================
# start.sh - Avvia Tool DB Manager completo
# Uso: bash start.sh
# ============================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "  Tool DB Manager"
echo "  ==============="
echo ""

find_python() {
  for cmd in python3.13 python3.12 python3.11 python3.10              /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12              /opt/homebrew/bin/python3.11 /usr/local/bin/python3.12; do
    if command -v "$cmd" &>/dev/null; then
      version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
      minor=$(echo $version | cut -d. -f2)
      if [ "$minor" -ge 10 ] && [ "$minor" -le 13 ]; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
  echo "ERRORE: Python 3.10-3.13 non trovato."
  echo "Installa con: brew install python@3.12"
  exit 1
fi
echo "  Python: $($PYTHON --version)"

if [ ! -f "venv/bin/activate" ]; then
  echo "  Creo ambiente virtuale..."
  "$PYTHON" -m venv venv
fi
# Carica variabili d'ambiente da .env se esiste (contiene ANTHROPIC_API_KEY, ecc.)
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
  echo "  Variabili .env caricate"
fi

source venv/bin/activate

if ! python -c "import flask, pandas, openpyxl" &>/dev/null; then
  echo "  Installo dipendenze (un momento)..."
  pip install -q flask pandas openpyxl schedule
fi
echo "  Dipendenze OK"

if [ ! -f "database/tool_master.db" ]; then
  echo "  Inizializzo database..."
  python -c "
import sqlite3, os
os.makedirs('database', exist_ok=True)
with open('database/schema.sql', encoding='utf-8') as f:
    sql = f.read()
conn = sqlite3.connect('database/tool_master.db')
conn.executescript(sql)
conn.commit()
conn.close()
print('  DB creato.')
"
fi
echo "  Database OK"

mkdir -p output/auto output/manual logs
lsof -ti:5000 | xargs kill -9 2>/dev/null || true
lsof -ti:5001 | xargs kill -9 2>/dev/null || true
sleep 0.5

echo ""
echo "  Avvio servizi..."

python ui/app.py > logs/app_main.log 2>&1 &
MAIN_PID=$!
python learner/app_learner.py > logs/app_learner.log 2>&1 &
LEARNER_PID=$!
sleep 2

MAIN_OK=false
LEARNER_OK=false
kill -0 $MAIN_PID 2>/dev/null && MAIN_OK=true
kill -0 $LEARNER_PID 2>/dev/null && LEARNER_OK=true

if $MAIN_OK && $LEARNER_OK; then
  echo ""
  echo "  Avviato con successo!"
  echo ""
  echo "  App principale  ->  http://localhost:5000"
  echo "  Format Learner  ->  http://localhost:5001"
  echo ""
  echo "  Log: logs/app_main.log"
  echo "  Per fermare: bash stop.sh  oppure Ctrl+C"
  echo ""
  open http://localhost:5000 2>/dev/null || true
  trap "echo ''; echo '  Fermo i servizi...'; kill $MAIN_PID $LEARNER_PID 2>/dev/null; echo '  Fermato.'; exit 0" INT
  wait $MAIN_PID
else
  echo ""
  echo "  ERRORE nell'avvio. Dettagli:"
  echo ""
  cat logs/app_main.log 2>/dev/null | tail -30
  echo ""
  cat logs/app_learner.log 2>/dev/null | tail -10
  exit 1
fi