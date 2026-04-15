#!/bin/bash
# Tool DB Manager — start.sh
# Avvia con Gunicorn (timeout 600s) se disponibile, altrimenti Flask dev
cd "$(dirname "$0")"

lsof -ti:5000 | xargs kill -9 2>/dev/null
sleep 1

if command -v gunicorn &>/dev/null; then
  echo "Avvio con Gunicorn (timeout 600s)..."
  gunicorn --workers=2 --timeout=600 --bind=0.0.0.0:5000 \
    --pythonpath "$(pwd):$(pwd)/ui" "ui.app:app"
else
  echo "Gunicorn non trovato, avvio Flask dev server..."
  python3 ui/app.py
fi
