#!/bin/bash
# stop.sh - Ferma tutti i servizi
cd "$(dirname "$0")"
echo "  Fermo i servizi..."

# Usa i PID salvati
for PID_FILE in .pid_main .pid_learner; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        kill -9 "$PID" 2>/dev/null && echo "  ✓ Fermato PID $PID"
        rm -f "$PID_FILE"
    fi
done

# Forza pulizia porte per sicurezza
for PORT in 5000 5001; do
    PIDS=$(lsof -ti :$PORT 2>/dev/null) || true
    if [ -n "$PIDS" ]; then
        kill -9 $PIDS 2>/dev/null || true
    fi
done

echo "  Fermato."
