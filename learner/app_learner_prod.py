"""
app_learner_prod.py - Avvio del Format Learner senza debug mode
Usato da start.sh per avvio in background
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app_learner import app

@app.route('/debug_orche')
def debug_orche():
    """Mostra versione orchestratore in memoria e forza reload."""
    import importlib
    try:
        import orchestrator_agent as oa
        importlib.reload(oa)
        has_batch = hasattr(oa, '_l3_mapping') and 'BATCH_SIZE' in open(oa.__file__).read()
        return f'orchestrator_agent: {oa.__file__}<br>BATCH_SIZE: {has_batch}<br>Reloaded OK'
    except Exception as e:
        return f'Errore: {e}'

if __name__ == '__main__':
    print('Format Learner -> http://localhost:5001')
    app.run(debug=False, port=5001, host='127.0.0.1')
