"""
app_learner_prod.py - Avvio del Format Learner senza debug mode
Usato da start.sh per avvio in background
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app_learner import app

@app.route('/debug_orche')
def debug_orche():
    import importlib, traceback, json, pandas as pd
    out = []
    try:
        import orchestrator_agent as oa
        importlib.reload(oa)
        out.append(f'File: {oa.__file__}')
        out.append(f'BATCH_SIZE: {"BATCH_SIZE" in open(oa.__file__).read()}')
        out.append(f'disponibile: {oa.disponibile()}')
        
        # Carica CSV Cutters dal ZIP Cimatron
        import zipfile
        zip_path = '/Users/iondodon/Documents/Cimatron_2025.zip'
        with zipfile.ZipFile(zip_path) as z:
            cutters = next(n for n in z.namelist() if 'Cutters' in n)
            with z.open(cutters) as zf:
                content = zf.read().decode('utf-16')
        lines = content.splitlines()
        nome_riga = id_riga = -1
        for i, line in enumerate(lines):
            s = line.strip().lstrip('"')
            if s.startswith('//') or s == '' or s.startswith('Cimatron'): continue
            if nome_riga == -1: nome_riga = i; continue
            if id_riga == -1: id_riga = i; break
        col_names = [c.strip() for c in lines[nome_riga].split('|')]
        dati = [l for l in lines[id_riga+1:] if l.strip() and not l.strip().startswith('//')]
        rows = []
        for line in dati:
            parts = line.split('|')
            rows.append({col_names[j]: parts[j].strip() if j < len(parts) else '' for j in range(len(col_names))})
        df = pd.DataFrame(rows)
        out.append(f'DataFrame: {len(df)} righe x {len(df.columns)} colonne')
        out.append(f'Prime 5 colonne: {list(df.columns[:5])}')

        # Test L2a
        struttura = oa._l2a_struttura(df, oa._get_api_key(), lambda lv,msg: out.append(f'[{lv}] {msg}'))
        out.append(f'L2a OK: software={struttura.get("software_cam")}')

        # Test L2b su 3 colonne campione
        for col in ['Nome Utensile', 'Diametro', 'Lungh. Libera']:
            if col in df.columns:
                res = oa._l2b_colonna(col, df[col], struttura, oa._get_api_key())
                out.append(f'L2b "{col}" -> {res.get("campo_master_suggerito")} [{res.get("confidenza")}]')

        # Test L3 batch con prime 30 colonne
        analisi = {}
        for col in list(df.columns)[:30]:
            analisi[col] = oa._l2b_colonna(col, df[col], struttura, oa._get_api_key())
        mapping_result = oa._l3_mapping(analisi, struttura, oa._get_api_key(), lambda lv,msg: out.append(f'[{lv}] {msg}'))
        n_mappati = sum(1 for v in mapping_result.get('mapping',{}).values() if v.get('campo_master','ignora')!='ignora')
        out.append(f'L3 batch OK: {n_mappati} campi mappati su 30')
        for col, info in list(mapping_result.get('mapping',{}).items())[:10]:
            out.append(f'  {col} -> {info.get("campo_master")} [{info.get("confidenza")}]')

    except Exception as e:
        out.append(f'ERRORE: {traceback.format_exc()}')
    return '<br>'.join(out)

if __name__ == '__main__':
    print('Format Learner -> http://localhost:5001')
    app.run(debug=False, port=5001, host='127.0.0.1')
