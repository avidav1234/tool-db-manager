"""
app_learner_prod.py - Avvio del Format Learner senza debug mode
Usato da start.sh per avvio in background
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app_learner import app

if __name__ == '__main__':
    print('Format Learner -> http://localhost:5001')
    app.run(debug=False, port=5001, host='127.0.0.1')
