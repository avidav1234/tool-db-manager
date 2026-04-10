#!/bin/bash
echo "Fermo Tool DB Manager..."
lsof -ti:5000 | xargs kill -9 2>/dev/null && echo "  App principale fermata" || echo "  App principale non attiva"
lsof -ti:5001 | xargs kill -9 2>/dev/null && echo "  Format Learner fermato"  || echo "  Format Learner non attivo"
echo "Fatto."