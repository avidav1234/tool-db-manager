"""
cimatron_parser.py
==================
Parser dedicato per il formato nativo Cimatron XLS/CHL.

Il file XLS di Cimatron ha una struttura specifica:
  - Foglio "Cutters" con i dati utensili
  - Riga 5 (indice 5): ID numerici delle colonne (es. 1101.0 = Cutter Name)
  - Riga 6 (indice 6): nomi colonne in inglese
  - Riga 7+: dati utensili

Questo parser riconosce la struttura automaticamente senza configurazione.
Funziona con qualsiasi versione di Cimatron che usa questo formato.
"""

import os
import pandas as pd

# Mappatura ID Cimatron -> campo master ISO 13399
# Basata sull'analisi del file reale Cimatron 2025 SP5
CIMATRON_ID_MAP = {
    '1101': ('codice_interno',      'string'),
    '1102': ('descrizione',          'string'),
    '2103': ('codice_catalogo',      'string'),
    '2102': ('tipo',                 'categoria'),
    '2105': ('diametro_mm',          'float'),
    '2106': ('raggio_punta_mm',      'float'),
    '2108': ('lunghezza_totale_mm',  'float'),
    '2109': ('lunghezza_tagl_mm',    'float'),
    '2115': ('num_taglienti',        'int'),
    '2118': ('angolo_punta_gradi',   'float'),
    '2117': ('angolo_elica_gradi',   'float'),
    '2129': ('passo_mm',             'float'),
}

# Mappatura valori Tip/Type Cimatron -> tipo master
CIMATRON_TIPO_MAP = {
    'Flat':          'FLAT',
    'Ball':          'BALL',
    'Bull':          'BULL',
    'Drilling':      'DRILL',
    'Ream':          'REAM',
    'Tap':           'TAP',
    'Center':        'SPOT',
    'Corner Radius': 'BULL',
    'Full Radius':   'BALL',
    'Cylinder':      'FLAT',
    'Thread mill':   'THREAD',
    # Valori numerici (export CSV classico Cimatron)
    '1': 'FLAT', '2': 'BALL', '3': 'BULL',
    '4': 'DRILL', '5': 'TAP', '6': 'REAM',
    '7': 'SPOT',  '8': 'TAPER',
}

# Mappatura materiali Cimatron -> materiale master
CIMATRON_MAT_MAP = {
    '1': 'HM', '2': 'HSS', '3': 'HSCo', '4': 'CBN', '5': 'PCD', '6': 'CER',
    'Carbide': 'HM', 'HSS': 'HSS', 'CBN': 'CBN', 'PCD': 'PCD',
}


def is_cimatron_xls(filepath: str) -> bool:
    """Ritorna True se il file e' un XLS nativo di Cimatron."""
    if not filepath.lower().endswith('.xls'):
        return False
    try:
        import xlrd
        wb = xlrd.open_workbook(filepath)
        return 'Cutters' in wb.sheet_names()
    except Exception:
        return False


def leggi_cimatron_xls(filepath: str) -> dict:
    """
    Legge un file XLS nativo di Cimatron.
    Ritorna un dict compatibile con il risultato di analizza_file():
      - df: DataFrame con i dati utensili
      - mapping: mappatura colonne -> campi master
      - valori_categoria: mappatura valori categorici
      - colonne_originali, num_righe, num_colonne, anteprima
      - software_rilevato: 'cimatron'
      - versione_rilevata: es. 'CimatronE2024.00'
    """
    import xlrd
    wb   = xlrd.open_workbook(filepath)
    ws   = wb.sheet_by_name('Cutters')

    # Trova versione Cimatron dall'header
    versione = ''
    for i in range(min(7, ws.nrows)):
        for j in range(min(3, ws.ncols)):
            v = str(ws.cell_value(i, j))
            if 'Cimatron' in v or 'cimatron' in v.lower():
                versione = v.split()[0] if v else ''
                break

    # Riga ID (5) e riga nomi (6)
    ID_ROW   = 5
    NAME_ROW = 6
    DATA_ROW = 7

    # Costruisci mappatura colonna_indice -> {id, name}
    col_info = {}
    for j in range(ws.ncols):
        raw_id = str(ws.cell_value(ID_ROW, j)).strip()
        name   = str(ws.cell_value(NAME_ROW, j)).strip()
        # Normalizza ID: "1101.0" -> "1101"
        cid = raw_id.split('.')[0] if '.' in raw_id else raw_id
        if cid and name and cid not in ('', 'nan') and name not in ('', 'nan'):
            col_info[j] = {'id': cid, 'name': name}

    # Leggi righe dati
    rows = []
    for i in range(DATA_ROW, ws.nrows):
        row = {}
        for j, info in col_info.items():
            val = ws.cell_value(i, j)
            if str(val).strip() not in ('', 'nan'):
                row[info['name']] = val
        if row.get('Cutter Name', '').strip():
            rows.append(row)

    if not rows:
        raise ValueError(
            "Nessun utensile trovato nel file Cimatron.\n"
            "Il file sembra un template vuoto oppure il formato non e' supportato.\n"
            "Esporta gli utensili da Cimatron tramite: NC-Process -> Cutters -> Export -> CSV"
        )

    df = pd.DataFrame(rows)

    # Costruisci mapping verso campi master
    mapping = {}
    for j, info in col_info.items():
        cid  = info['id']
        name = info['name']
        if cid in CIMATRON_ID_MAP:
            campo, tipo = CIMATRON_ID_MAP[cid]
            if name in df.columns:
                mapping[campo] = {
                    'colonna_file': name,
                    'score':        10.0,
                    'tipo':         tipo,
                    'label':        name,
                    'confidenza':   'alta',
                }

    # Valori categoria
    valori_categoria = {}
    if 'Tip/Type' in df.columns:
        valori_categoria['tipo'] = {}
        for v in df['Tip/Type'].dropna().unique():
            k = str(v).strip()
            valori_categoria['tipo'][k] = CIMATRON_TIPO_MAP.get(k, '?')

    # Colonne non mappate (per info)
    id_map_names = {info['name'] for info in col_info.values() if info['id'] in CIMATRON_ID_MAP}
    colonne_non_mappate = [c for c in df.columns if c not in id_map_names]

    return {
        'filepath':           filepath,
        'num_righe':          len(df),
        'num_colonne':        len(df.columns),
        'colonne_originali':  list(df.columns),
        'mapping':            mapping,
        'valori_categoria':   valori_categoria,
        'colonne_non_mappate': colonne_non_mappate,
        'anteprima':          df.head(5).to_dict(orient='records'),
        'df':                 df,
        'software_rilevato':  'cimatron',
        'versione_rilevata':  versione,
        'parser_usato':       'cimatron_nativo',
    }


def leggi_cimatron_csv(filepath: str) -> dict:
    """
    Legge un file CSV pipe-separato esportato da Cimatron NC.
    Formato: separatore |, righe commento con //, ID colonne nella 4a riga.
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()

    lines = raw.splitlines()
    versione = ''
    data_lines = []
    id_line = None
    col_names = []

    for line in lines:
        if line.startswith('//CimatronE') or line.startswith('//cimatron'):
            versione = line.replace('//', '').strip()
        elif line.startswith('//'):
            continue
        elif not id_line and all(p.strip().replace('.', '').isdigit()
                                  for p in line.split('|') if p.strip()):
            id_line = line
        else:
            data_lines.append(line)

    if not id_line or not data_lines:
        raise ValueError("File CSV Cimatron non valido o vuoto")

    # Prima riga dati = nomi colonne localizzati (opzionale) oppure dati
    # Cimatron mette i nomi nella prima riga non-// non-ID
    # Se la prima riga data_lines contiene numeri -> e' data, altrimenti e' header
    first = data_lines[0].split('|')
    has_header = not any(p.strip().replace('.','').replace('-','').replace(',','').isdigit()
                         for p in first[:3] if p.strip())
    if has_header:
        col_names = [p.strip() for p in first]
        data_lines = data_lines[1:]
    else:
        # Usa ID come nomi colonne
        col_names = [p.strip() for p in id_line.split('|')]

    ids = [p.strip().split('.')[0] for p in id_line.split('|')]

    rows = []
    for line in data_lines:
        if not line.strip():
            continue
        parts = line.split('|')
        row = {}
        for i, val in enumerate(parts):
            if i < len(col_names):
                row[col_names[i]] = val.strip()
        if row:
            rows.append(row)

    if not rows:
        raise ValueError("Nessun utensile trovato nel CSV Cimatron")

    df = pd.DataFrame(rows)

    # Mapping tramite ID
    mapping = {}
    for i, cid in enumerate(ids):
        if i < len(col_names) and cid in CIMATRON_ID_MAP:
            campo, tipo = CIMATRON_ID_MAP[cid]
            name = col_names[i]
            if name in df.columns:
                mapping[campo] = {
                    'colonna_file': name, 'score': 10.0,
                    'tipo': tipo, 'label': name, 'confidenza': 'alta',
                }

    valori_categoria = {}
    tipo_col = mapping.get('tipo', {}).get('colonna_file')
    if tipo_col and tipo_col in df.columns:
        valori_categoria['tipo'] = {
            str(v): CIMATRON_TIPO_MAP.get(str(v), '?')
            for v in df[tipo_col].dropna().unique()
        }

    id_map_names = {v['colonna_file'] for v in mapping.values()}
    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': valori_categoria,
        'colonne_non_mappate': [c for c in df.columns if c not in id_map_names],
        'anteprima': df.head(5).to_dict(orient='records'),
        'df': df, 'software_rilevato': 'cimatron',
        'versione_rilevata': versione, 'parser_usato': 'cimatron_csv',
    }
