"""
format_learner.py
=================
Punto di ingresso unico per l'analisi di qualsiasi file CAM.

Logica di rilevamento automatico (in ordine di priorita'):
  1. Cimatron ZIP  -> cimatron_parser.leggi_cimatron_zip()
  2. Cimatron XLS  -> cimatron_parser.leggi_cimatron_xls()
  3. Cimatron CSV  -> cimatron_parser.leggi_cimatron_csv()
  4. ZIP generico  -> parsing euristico CSV interno
  5. CSV generico  -> parsing euristico
  6. XLSX/XLS      -> parsing euristico

Nessuna configurazione richiesta: il sistema riconosce il formato
dal contenuto del file, non dall'estensione o dal nome.
"""

import os
import zipfile
import pandas as pd

# ---------------------------------------------------------------
# Campi del DB master (ISO 13399)
# ---------------------------------------------------------------
MASTER_FIELDS = {
    'codice_interno':     {'label': 'Codice interno / Nome utensile',   'tipo': 'string',
                           'keywords': ['name','nome','codice','code','id','number','nummer','bezeichnung'], 'esempio': 'FP-D10-R0-L50'},
    'codice_catalogo':    {'label': 'Codice catalogo fornitore',        'tipo': 'string',
                           'keywords': ['catalog','catalogo','article','articolo','part','sku','ref'], 'esempio': 'R216.34-10030'},
    'descrizione':        {'label': 'Descrizione utensile',             'tipo': 'string',
                           'keywords': ['descri','comment','commento','note','bemerkung','remark'], 'esempio': 'Fresa piatta D10 Z3'},
    'tipo':               {'label': 'Tipo utensile',                    'tipo': 'categoria',
                           'keywords': ['type','tipo','art','cutter','tool_type','tooltype','tip','typ'],
                           'valori_attesi': ['FLAT','BALL','BULL','DRILL','TAP','REAM','SPOT','TAPER'], 'esempio': 'BALL'},
    'diametro_mm':        {'label': 'Diametro [mm]',                    'tipo': 'float',
                           'keywords': ['diam','diameter','durchmesser','dc','d1','d '], 'range': (0.1,500.0), 'esempio': 10.0},
    'raggio_punta_mm':    {'label': 'Raggio punta / corner radius [mm]','tipo': 'float',
                           'keywords': ['corner','radius','raggio','rn','re','r_','nose'], 'range': (0.0,50.0), 'esempio': 1.0},
    'angolo_punta_gradi': {'label': 'Angolo punta [gradi]',             'tipo': 'float',
                           'keywords': ['angle','angolo','point','spitze','tip'], 'range': (0.0,180.0), 'esempio': 118.0},
    'lunghezza_totale_mm':{'label': 'Lunghezza totale [mm]',            'tipo': 'float',
                           'keywords': ['overall','total','length','lunghezza','oal','lt','l '], 'range': (1.0,500.0), 'esempio': 75.0},
    'lunghezza_tagl_mm':  {'label': 'Lunghezza tagliente [mm]',         'tipo': 'float',
                           'keywords': ['flute','cutting','tagliente','schneiden','lc','lf','fl'], 'range': (1.0,300.0), 'esempio': 22.0},
    'num_taglienti':      {'label': 'Numero taglienti',                 'tipo': 'int',
                           'keywords': ['flute','zahn','denti','teeth','taglienti','nf','z '], 'range': (1,20), 'esempio': 4},
    'angolo_elica_gradi': {'label': 'Angolo elica [gradi]',             'tipo': 'float',
                           'keywords': ['helix','elica','spiral','drall'], 'range': (0.0,90.0), 'esempio': 30.0},
    'materiale':          {'label': 'Materiale tagliente',              'tipo': 'categoria',
                           'keywords': ['material','materiale','werkstoff','substrate'],
                           'valori_attesi': ['HM','HSS','HSCo','CBN','PCD','CER'], 'esempio': 'HM'},
}

TIPO_GUESS = {
    '1':'FLAT','2':'BALL','3':'BULL','4':'DRILL','5':'TAP','6':'REAM',
    'flat':'FLAT','mill':'FLAT','endmill':'FLAT','piana':'FLAT',
    'ball':'BALL','ballnose':'BALL','sferica':'BALL','sfera':'BALL',
    'bull':'BULL','bullnose':'BULL','torica':'BULL',
    'drill':'DRILL','punta':'DRILL','foratura':'DRILL',
    'tap':'TAP','maschio':'TAP','filettatura':'TAP',
    'ream':'REAM','alesatura':'REAM',
    'spot':'SPOT','center':'SPOT','centratura':'SPOT',
    'chamfer':'TAPER','taper':'TAPER',
}
MAT_GUESS = {
    '1':'HM','2':'HSS','3':'HSCo','4':'CBN','5':'PCD',
    'hm':'HM','carbide':'HM','widia':'HM','vhm':'HM',
    'hss':'HSS','hsco':'HSCo','cbn':'CBN','pcd':'PCD','ceramic':'CER',
}


def _score_column(col_name, series, field_key, field_meta):
    score = 0.0
    col_lower = col_name.lower().strip()
    for kw in field_meta.get('keywords', []):
        if kw.lower() in col_lower:
            score += 3.0
            if col_lower.startswith(kw.lower()):
                score += 1.0
    tipo = field_meta.get('tipo')
    non_null = series.dropna()
    if len(non_null) == 0:
        return score
    if tipo in ('float', 'int'):
        nr = pd.to_numeric(non_null, errors='coerce').notna().mean()
        if nr > 0.8:
            score += 2.0
            rng = field_meta.get('range')
            if rng:
                vals = pd.to_numeric(non_null, errors='coerce').dropna()
                if len(vals) > 0 and rng[0] <= vals.mean() <= rng[1]:
                    score += 2.0
    elif tipo == 'string':
        if non_null.apply(lambda x: isinstance(x, str)).mean() > 0.7:
            score += 1.0
    elif tipo == 'categoria':
        if 2 <= non_null.nunique() <= 20 and non_null.nunique() < len(non_null) * 0.5:
            score += 2.0
    return score


def _rileva_mappatura(df):
    mapping = {}
    used_cols = set()
    priority = ['codice_interno','diametro_mm','tipo','materiale',
                'lunghezza_totale_mm','lunghezza_tagl_mm','raggio_punta_mm',
                'num_taglienti','angolo_punta_gradi','angolo_elica_gradi',
                'codice_catalogo','descrizione']
    for fk in priority:
        fm = MASTER_FIELDS[fk]
        best_col, best_score = None, 0.0
        for col in df.columns:
            if col in used_cols:
                continue
            sc = _score_column(col, df[col], fk, fm)
            if sc > best_score:
                best_score = sc
                best_col = col
        if best_col and best_score >= 2.0:
            mapping[fk] = {
                'colonna_file': best_col, 'score': round(best_score,1),
                'tipo': fm['tipo'], 'label': fm['label'],
                'confidenza': 'alta' if best_score >= 5 else 'media' if best_score >= 3 else 'bassa'
            }
            used_cols.add(best_col)
    return mapping


def _rileva_valori_categoria(df, colonna, campo_master):
    guess_map = TIPO_GUESS if campo_master == 'tipo' else MAT_GUESS
    return {str(v): guess_map.get(str(v).strip().lower(), '?')
            for v in df[colonna].dropna().unique()}


def analizza_file(filepath: str) -> dict:
    """
    Analizza qualsiasi file CAM e ritorna la mappatura verso i campi master.
    Rilevamento formato completamente automatico.
    """
    ext = os.path.splitext(filepath)[1].lower()

    # --- Importa il parser Cimatron ---
    try:
        from cimatron_parser import is_cimatron_file, leggi_cimatron_xls, leggi_cimatron_csv, leggi_cimatron_zip
        _cimatron_available = True
    except ImportError:
        _cimatron_available = False

    # 1. ZIP Cimatron (contiene Cutters_*.csv)
    if ext == '.zip' and _cimatron_available and is_cimatron_file(filepath):
        return leggi_cimatron_zip(filepath)

    # 2. XLS Cimatron (foglio 'Cutters')
    if ext == '.xls' and _cimatron_available and is_cimatron_file(filepath):
        return leggi_cimatron_xls(filepath)

    # 3. CSV Cimatron (UTF-16, pipe, righe //)
    if ext == '.csv' and _cimatron_available and is_cimatron_file(filepath):
        return leggi_cimatron_csv(filepath)

    # 4. ZIP generico
    if ext == '.zip' or zipfile.is_zipfile(filepath):
        with zipfile.ZipFile(filepath, 'r') as z:
            csv_files = [f for f in z.namelist() if f.lower().endswith('.csv')]
            if not csv_files:
                raise ValueError("Nessun CSV nel ZIP")
            target = next((f for f in csv_files if 'cutter' in f.lower()), csv_files[0])
            with z.open(target) as f:
                content = f.read().decode('utf-8', errors='replace')
        sep = '|' if content.count('|') > content.count(',') else ','
        lines = [l for l in content.splitlines() if not l.startswith('//')]
        from io import StringIO
        df = pd.read_csv(StringIO('\n'.join(lines)), sep=sep, on_bad_lines='skip')

    elif ext == '.csv':
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            raw = f.read()
        sep = '|' if raw.count('|') > raw.count(',') else ','
        lines = [l for l in raw.splitlines() if not l.startswith('//')]
        from io import StringIO
        df = pd.read_csv(StringIO('\n'.join(lines)), sep=sep, on_bad_lines='skip')

    elif ext in ('.xls', '.xlsx'):
        df = pd.read_excel(filepath)
    else:
        raise ValueError(f"Formato non supportato: {ext}")

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how='all').reset_index(drop=True)

    if len(df) == 0:
        raise ValueError(
            "Il file non contiene dati utensili riconoscibili.\n"
            "Assicurati di esportare con utensili selezionati e non un template vuoto."
        )

    mapping = _rileva_mappatura(df)
    valori_categoria = {}
    for campo, info in mapping.items():
        if info['tipo'] == 'categoria':
            valori_categoria[campo] = _rileva_valori_categoria(df, info['colonna_file'], campo)

    colonne_mappate = {v['colonna_file'] for v in mapping.values()}
    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': valori_categoria,
        'colonne_non_mappate': [c for c in df.columns if c not in colonne_mappate],
        'anteprima': df.head(5).to_dict(orient='records'),
        'df': df, 'software_rilevato': 'sconosciuto',
        'versione_rilevata': '', 'parser_usato': 'generico',
    }


if __name__ == '__main__':
    import argparse, sys
    parser = argparse.ArgumentParser(description='Analizza file CAM - rileva formato automaticamente')
    parser.add_argument('--file', required=True)
    args = parser.parse_args()
    if not os.path.exists(args.file):
        print(f"File non trovato: {args.file}"); sys.exit(1)
    r = analizza_file(args.file)
    sw  = r.get('software_rilevato','?')
    ver = r.get('versione_rilevata','?')
    par = r.get('parser_usato','?')
    print(f"\nFile:     {os.path.basename(r['filepath'])}")
    print(f"Software: {sw} {ver}  (parser: {par})")
    print(f"Utensili: {r['num_righe']}  |  Colonne: {r['num_colonne']}")
    if r.get('extra_info'):
        for k,v in r['extra_info'].items():
            print(f"Extra:    {v}")
    print(f"\nMappatura ({len(r['mapping'])} campi su 12 possibili):")
    for campo, info in r['mapping'].items():
        print(f"  {info['colonna_file']:35} -> {campo:25} [{info['confidenza']}]")
    if r['valori_categoria']:
        print("\nValori tipo utensile rilevati:")
        for campo, vals in r['valori_categoria'].items():
            for vf, vm in list(vals.items())[:8]:
                print(f"  {vf:15} -> {vm}")
