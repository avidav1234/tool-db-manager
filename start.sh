#!/bin/bash
# Tool DB Manager — start.sh
# Avvia App principale (porta 5000) + Format Learner (porta 5001)
cd "$(dirname "$0")"

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export LANG=it_IT.UTF-8
export LC_ALL=it_IT.UTF-8

mkdir -p logs

# ── Libera porte ──────────────────────────────────────────────
for PORT in 5000 5001; do
  PIDS=$(lsof -ti :$PORT 2>/dev/null) || true
  if [ -n "$PIDS" ]; then
    echo "Porto $PORT: termino PID $PIDS"
    kill -9 $PIDS 2>/dev/null || true
  fi
done
sleep 1

# ── App principale (porta 5000) ──────────────────────────────
if command -v gunicorn &>/dev/null; then
  echo "App principale: Gunicorn (timeout 600s) -> http://localhost:5000"
  nohup gunicorn --workers=2 --timeout=600 --bind=0.0.0.0:5000 \
    --pythonpath "$(pwd):$(pwd)/ui" "ui.app:app" > logs/app_main.log 2>&1 &
  echo $! > .pid_main
else
  echo "App principale: Flask dev -> http://localhost:5000"
  nohup python3 ui/app.py > logs/app_main.log 2>&1 &
  echo $! > .pid_main
fi

# ── Format Learner (porta 5001) ──────────────────────────────
echo "Format Learner: Flask -> http://localhost:5001"
nohup python3 learner/app_learner_prod.py > logs/app_learner.log 2>&1 &
echo $! > .pid_learner

# ── Verifica ─────────────────────────────────────────────────
sleep 2
MAIN_OK=false; LEARNER_OK=false
for i in 1 2 3 4 5; do
  curl -s http://localhost:5000 > /dev/null 2>&1 && MAIN_OK=true
  curl -s http://localhost:5001 > /dev/null 2>&1 && LEARNER_OK=true
  $MAIN_OK && $LEARNER_OK && break
  sleep 1
done

echo ""
$MAIN_OK   && echo "  OK App principale  -> http://localhost:5000" \
           || echo "  XX App principale non risponde (vedi logs/app_main.log)"
$LEARNER_OK && echo "  OK Format Learner  -> http://localhost:5001" \
            || echo "  XX Format Learner non risponde (vedi logs/app_learner.log)"
echo ""
echo "  PID main=$(cat .pid_main) learner=$(cat .pid_learner)"
echo "  Per fermare: bash stop.sh"
echo ""
