"""
format_learner.py
=================
Analizza automaticamente un file esportato da un CAM (CSV, XLS, XLSX, ZIP)
e propone una mappatura verso i campi ISO 13399 del DB master.

Uso standalone:
    python format_learner.py --file export_hypermill.csv
    python format_learner.py --file export_cimatron.zip
"""

import os
import json
import zipfile
import pandas as pd
from typing import Optional

# ---------------------------------------------------------------
# Campi del DB master (ISO 13399) con metadati per il rilevamento
# ---------------------------------------------------------------
MASTER_FIELDS = {
    'codice_interno': {
        'label': 'Codice interno / Nome utensile',
        'tipo': 'string',
        'keywords': ['name', 'nome', 'codice', 'code', 'id', 'number', 'nummer', 'bezeichnung'],
        'esempio': 'FP-D10-R0-L50'
    },
    'codice_catalogo': {
        'label': 'Codice catalogo fornitore',
        'tipo': 'string',
        'keywords': ['catalog', 'catalogo', 'article', 'articolo', 'part', 'sku', 'ref'],
        'esempio': 'R216.34-10030-AC10G'
    },
    'descrizione': {
        'label': 'Descrizione utensile',
        'tipo': 'string',
        'keywords': ['descri', 'comment', 'commento', 'note', 'bemerkung', 'remark'],
        'esempio': 'Fresa piatta D10 Z3'
    },
    'tipo': {
        'label': 'Tipo utensile',
        'tipo': 'categoria',
        'keywords': ['type', 'tipo', 'art', 'cutter', 'tool_type', 'tooltype', 'typ'],
        'valori_attesi': ['FLAT', 'BALL', 'BULL', 'DRILL', 'TAP', 'REAM', 'SPOT', 'TAPER'],
        'esempio': 'BALL'
    },
    'diametro_mm': {
        'label': 'Diametro [mm]',
        'tipo': 'float',
        'keywords': ['diam', 'diameter', 'durchmesser', 'dc', 'd1', 'd '],
        'range': (0.1, 500.0),
        'esempio': 10.0
    },
    'raggio_punta_mm': {
        'label': 'Raggio punta / corner radius [mm]',
        'tipo': 'float',
        'keywords': ['corner', 'radius', 'raggio', 'rn', 're', 'r_', 'nose'],
        'range': (0.0, 50.0),
        'esempio': 1.0
    },
    'angolo_punta_gradi': {
        'label': 'Angolo punta [gradi]',
        'tipo': 'float',
        'keywords': ['angle', 'angolo', 'point', 'spitze', 'tip'],
        'range': (0.0, 180.0),
        'esempio': 118.0
    },
    'lunghezza_totale_mm': {
        'label': 'Lunghezza totale [mm]',
        'tipo': 'float',
        'keywords': ['overall', 'total', 'length', 'lunghezza', 'gesamtlaenge', 'oal', 'lt', 'l '],
        'range': (1.0, 500.0),
        'esempio': 75.0
    },
    'lunghezza_tagl_mm': {
        'label': 'Lunghezza tagliente [mm]',
        'tipo': 'float',
        'keywords': ['flute', 'cutting', 'tagliente', 'schneiden', 'lc', 'lf', 'fl'],
        'range': (1.0, 300.0),
        'esempio': 22.0
    },
    'num_taglienti': {
        'label': 'Numero taglienti',
        'tipo': 'int',
        'keywords': ['flute', 'zahn', 'denti', 'teeth', 'taglienti', 'num_fl', 'nf', 'z '],
        'range': (1, 20),
        'esempio': 4
    },
    'angolo_elica_gradi': {
        'label': 'Angolo elica [gradi]',
        'tipo': 'float',
        'keywords': ['helix', 'elica', 'spiral', 'drall'],
        'range': (0.0, 90.0),
        'esempio': 30.0
    },
    'materiale': {
        'label': 'Materiale tagliente',
        'tipo': 'categoria',
        'keywords': ['material', 'materiale', 'werkstoff', 'substrate'],
        'valori_attesi': ['HM', 'HSS', 'HSCo', 'CBN', 'PCD', 'CER'],
        'esempio': 'HM'
    },
}

TIPO_GUESS = {
    '1': 'FLAT', '2': 'BALL', '3': 'BULL', '4': 'DRILL', '5': 'TAP', '6': 'REAM',
    'flat': 'FLAT', 'mill': 'FLAT', 'endmill': 'FLAT', 'end_mill': 'FLAT',
    'ball': 'BALL', 'ballnose': 'BALL', 'ball_nose': 'BALL', 'sphere': 'BALL',
    'bull': 'BULL', 'bullnose': 'BULL', 'toroid': 'BULL', 'corner': 'BULL',
    'drill': 'DRILL', 'punta': 'DRILL', 'twist': 'DRILL',
    'tap': 'TAP', 'maschio': 'TAP', 'thread': 'TAP',
    'ream': 'REAM', 'alesatore': 'REAM',
    'spot': 'SPOT', 'center': 'SPOT',
    'chamfer': 'TAPER', 'taper': 'TAPER',
}

MAT_GUESS = {
    '1': 'HM', '2': 'HSS', '3': 'HSCo', '4': 'CBN', '5': 'PCD',
    'hm': 'HM', 'carbide': 'HM', 'widia': 'HM', 'vhm': 'HM',
    'hss': 'HSS', 'hsco': 'HSCo', 'cbn': 'CBN', 'pcd': 'PCD', 'ceramic': 'CER',
}


def _score_column(col_name: str, series: pd.Series, field_key: str, field_meta: dict) -> float:
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
        numeric_ratio = pd.to_numeric(non_null, errors='coerce').notna().mean()
        if numeric_ratio > 0.8:
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


def _rileva_mappatura(df: pd.DataFrame) -> dict:
    mapping = {}
    used_cols = set()
    priority = ['codice_interno', 'diametro_mm', 'tipo', 'materiale',
                'lunghezza_totale_mm', 'lunghezza_tagl_mm', 'raggio_punta_mm',
                'num_taglienti', 'angolo_punta_gradi', 'angolo_elica_gradi',
                'codice_catalogo', 'descrizione']
    for field_key in priority:
        field_meta = MASTER_FIELDS[field_key]
        best_col, best_score = None, 0.0
        for col in df.columns:
            if col in used_cols:
                continue
            score = _score_column(col, df[col], field_key, field_meta)
            if score > best_score:
                best_score = score
                best_col = col
        if best_col and best_score >= 2.0:
            mapping[field_key] = {
                'colonna_file': best_col, 'score': round(best_score, 1),
                'tipo': field_meta['tipo'], 'label': field_meta['label'],
                'confidenza': 'alta' if best_score >= 5 else 'media' if best_score >= 3 else 'bassa'
            }
            used_cols.add(best_col)
    return mapping


def _rileva_valori_categoria(df: pd.DataFrame, colonna: str, campo_master: str) -> dict:
    guess_map = TIPO_GUESS if campo_master == 'tipo' else MAT_GUESS
    valori = {}
    for v in df[colonna].dropna().unique():
        key = str(v).strip().lower()
        valori[str(v)] = guess_map.get(key, '?')
    return valori


def analizza_file(filepath: str) -> dict:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.zip':
        with zipfile.ZipFile(filepath, 'r') as z:
            csv_files = [f for f in z.namelist() if f.endswith('.csv')]
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

    mapping = _rileva_mappatura(df)
    valori_categoria = {}
    for campo, info in mapping.items():
        if info['tipo'] == 'categoria':
            valori_categoria[campo] = _rileva_valori_categoria(df, info['colonna_file'], campo)

    colonne_mappate = {v['colonna_file'] for v in mapping.values()}
    return {
        'filepath': filepath,
        'num_righe': len(df),
        'num_colonne': len(df.columns),
        'colonne_originali': list(df.columns),
        'mapping': mapping,
        'valori_categoria': valori_categoria,
        'colonne_non_mappate': [c for c in df.columns if c not in colonne_mappate],
        'anteprima': df.head(5).to_dict(orient='records'),
        'df': df,
    }


if __name__ == '__main__':
    import argparse, sys
    parser = argparse.ArgumentParser(description='Analizza un file CAM e propone mappatura')
    parser.add_argument('--file', required=True)
    args = parser.parse_args()
    if not os.path.exists(args.file):
        print(f"File non trovato: {args.file}"); sys.exit(1)
    r = analizza_file(args.file)
    print(f"\nFile: {r['filepath']} | Righe: {r['num_righe']} | Colonne: {r['num_colonne']}")
    print(f"\nMappatura ({len(r['mapping'])} campi):")
    for campo, info in r['mapping'].items():
        print(f"  {info['colonna_file']:25} -> {campo:25} [{info['confidenza']}]")
    if r['colonne_non_mappate']:
        print(f"\nNon mappate: {r['colonne_non_mappate']}")
