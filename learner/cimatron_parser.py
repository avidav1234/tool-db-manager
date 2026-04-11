"""
cimatron_parser.py
==================
Parser dedicato per tutti i formati di export Cimatron.

Formati supportati:
  - XLS nativo  (foglio 'Cutters', header multi-riga con ID numerici)
  - CSV singolo (UTF-16, separatore |, righe // commento, nomi in italiano o inglese)
  - ZIP         (contiene: Cutters_*.csv, Holders_*.csv, Material_*.csv, ecc.)

Rilevamento automatico:
  - Nessuna configurazione richiesta dall'utente
  - Funziona con qualsiasi versione di Cimatron (2024, 2025, ...)
  - Riconosce nomi colonne in italiano E in inglese
  - Legge anche i dati di taglio dal file Material_*.csv (se presente)
"""

import os
import io
import zipfile
import pandas as pd

# ---------------------------------------------------------------
# Mappatura ID Cimatron -> campo master ISO 13399
# Basata su analisi reale file Cimatron 2025 SP5
# ---------------------------------------------------------------
CIMATRON_ID_MAP = {
    '1101': ('codice_interno',      'string'),   # Nome Utensile / Cutter Name
    '1102': ('descrizione',          'string'),   # Commento / Comment
    '2103': ('codice_catalogo',      'string'),   # Nome Catalogo / Catalog Name
    '2102': ('tipo',                 'categoria'),# Punta/Tipo / Tip/Type
    '2105': ('diametro_mm',          'float'),    # Diametro / Diameter
    '2106': ('raggio_punta_mm',      'float'),    # Raggio / Corner Radius
    '2108': ('lunghezza_totale_mm',  'float'),    # Lunghezza Tagliente / Full Cutter Length
    '2109': ('lunghezza_tagl_mm',    'float'),    # Lunghezza Libera / Clear Length
    '2115': ('num_taglienti',        'int'),      # Numero Taglienti / Num. of Flutes (da verifica)
    '2113': ('angolo_punta_gradi',   'float'),    # Angolo Punta / Tip Angle
    '2112': ('angolo_elica_gradi',   'float'),    # Angolo Elica / Helix Angle (da verifica)
    '2129': ('passo_mm',             'float'),    # Passo / Pitch
}

# Valori Punta/Tipo -> tipo master
# ID numerici (formato CSV pipe)
TIPO_ID_MAP = {
    '210201': 'FLAT',   # Piana / Flat
    '210202': 'BALL',   # Sferica / Ball
    '210203': 'BULL',   # Torica / Bull nose
    '210204': 'DRILL',  # Foratura / Drilling
    '210205': 'REAM',   # Alesatura / Ream
    '210206': 'TAP',    # Filettatura / Tap
    '210207': 'SPOT',   # Centratura / Center
    '210208': 'BALL',   # Raggio Pieno / Full Radius
    '210209': 'BULL',   # Raggio Angolare / Corner Radius
}

# Valori stringa (formato XLS e nomi inglesi)
TIPO_STR_MAP = {
    'flat':          'FLAT',  'piana':      'FLAT',
    'ball':          'BALL',  'sferica':    'BALL',   'sfera': 'BALL',
    'bull':          'BULL',  'torica':     'BULL',   'bull nose': 'BULL',
    'drilling':      'DRILL', 'foratura':   'DRILL',  'punta': 'DRILL',
    'ream':          'REAM',  'alesatura':  'REAM',
    'tap':           'TAP',   'filettatura':'TAP',    'maschio': 'TAP',
    'center':        'SPOT',  'centratura': 'SPOT',
    'full radius':   'BALL',  'raggio pieno': 'BALL',
    'corner radius': 'BULL',  'raggio angolare': 'BULL',
    'thread mill':   'THREAD','fresa filetto': 'THREAD',
}


def _decodifica_tipo(val: str) -> str:
    """Converte un valore Cimatron (ID numerico o stringa) in tipo master."""
    v = str(val).strip()
    if v in TIPO_ID_MAP:
        return TIPO_ID_MAP[v]
    return TIPO_STR_MAP.get(v.lower(), '?')


def _leggi_csv_cimatron(content_bytes: bytes, nome_file: str = '') -> pd.DataFrame:
    """
    Legge il contenuto binario di un CSV Cimatron (UTF-16, pipe-separato).
    Gestisce automaticamente:
      - Encoding UTF-16 (usato da Cimatron 2025)
      - Righe commento // da saltare
      - Riga versione CimatronE...
      - Riga nomi colonne (localizzati)
      - Riga ID colonne numerici
      - Righe dati utensili
    Ritorna DataFrame con nomi colonne = nomi localizzati.
    """
    # Prova UTF-16, poi UTF-8
    for enc in ('utf-16', 'utf-8-sig', 'utf-8', 'latin-1'):
        try:
            text = content_bytes.decode(enc)
            if 'CimatronE' in text or '1101' in text:
                break
        except Exception:
            continue

    lines = text.splitlines()

    # Struttura attesa:
    #  righe 0-4:  // commenti
    #  riga 5:     CimatronE2025.00|1000|96|...
    #  riga 6:     (vuota)
    #  riga 7:     Nomi colonne localizzati
    #  riga 8:     ID colonne numerici
    #  riga 9+:    Dati utensili

    nome_riga = -1
    id_riga   = -1
    dati_start = -1
    versione = ''

    for i, line in enumerate(lines):
        stripped = line.strip().lstrip('"')
        if stripped.startswith('CimatronE') and not stripped.startswith('//'):
            versione = stripped.split('|')[0]
            continue
        if stripped.startswith('//') or stripped == '':
            continue
        # Prima riga non-commento non-versione = nomi colonne
        if nome_riga == -1:
            nome_riga = i
            continue
        # Seconda riga = ID
        if id_riga == -1:
            id_riga = i
            dati_start = i + 1
            break

    if nome_riga == -1 or id_riga == -1:
        raise ValueError(f"Struttura CSV Cimatron non riconosciuta in {nome_file}")

    col_names = [c.strip() for c in lines[nome_riga].split('|')]
    col_ids   = [c.strip() for c in lines[id_riga].split('|')]

    # Leggi righe dati
    rows = []
    for line in lines[dati_start:]:
        if not line.strip() or line.strip().startswith('//'):
            continue
        parts = line.split('|')
        row = {}
        for j, val in enumerate(parts):
            if j < len(col_names) and col_names[j]:
                row[col_names[j]] = val.strip()
        # Un utensile deve avere almeno il nome
        first_col = col_names[0] if col_names else ''
        if first_col and row.get(first_col, '').strip():
            row['_cimatron_ids'] = col_ids   # conserva gli ID per il mapping
            rows.append(row)

    if not rows:
        # Messaggio chiaro invece di eccezione tecnica
        raise ValueError(
            f"Nessun utensile trovato in {nome_file}.\n"
            "Verifica che il file sia un export con utensili selezionati e non un template vuoto."
        )

    return pd.DataFrame(rows), col_names, col_ids, versione


def _mapping_da_ids(col_names: list, col_ids: list) -> dict:
    """Costruisce la mappatura campo_master -> info colonna usando gli ID numerici."""
    mapping = {}
    for j, cid_raw in enumerate(col_ids):
        if j >= len(col_names):
            break
        cid = cid_raw.split('.')[0].strip()
        nome = col_names[j]
        if cid in CIMATRON_ID_MAP and nome:
            campo, tipo = CIMATRON_ID_MAP[cid]
            mapping[campo] = {
                'colonna_file': nome,
                'score': 10.0,
                'tipo': tipo,
                'label': nome,
                'confidenza': 'alta',
                'id_cimatron': cid,
            }
    return mapping


def _valori_categoria(df: pd.DataFrame, mapping: dict) -> dict:
    """Crea mappatura valori per colonne categoriche."""
    valori = {}
    if 'tipo' in mapping:
        col = mapping['tipo']['colonna_file']
        if col in df.columns:
            valori['tipo'] = {
                str(v): _decodifica_tipo(str(v))
                for v in df[col].dropna().unique()
            }
    return valori


# ---------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------

def is_cimatron_file(filepath: str) -> bool:
    """Ritorna True se il file e' un export Cimatron (XLS, CSV, ZIP)."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.xls':
        try:
            import xlrd
            wb = xlrd.open_workbook(filepath)
            return 'Cutters' in wb.sheet_names()
        except Exception:
            return False
    if ext == '.csv':
        try:
            with open(filepath, 'rb') as f:
                raw = f.read(500)
            text = raw.decode('utf-16', errors='ignore') or raw.decode('utf-8', errors='ignore')
            return 'CimatronE' in text or ('1101' in text and '//' in text)
        except Exception:
            return False
    if ext == '.zip':
        try:
            with zipfile.ZipFile(filepath, 'r') as z:
                return any('Cutters' in n and n.endswith('.csv') for n in z.namelist())
        except Exception:
            return False
    return False


def leggi_cimatron_xls(filepath: str) -> dict:
    """Legge un file XLS nativo Cimatron."""
    import xlrd
    wb  = xlrd.open_workbook(filepath)
    ws  = wb.sheet_by_name('Cutters')

    versione = ''
    for i in range(min(7, ws.nrows)):
        for j in range(min(3, ws.ncols)):
            v = str(ws.cell_value(i, j))
            if 'Cimatron' in v:
                versione = v.strip()
                break

    ID_ROW, NAME_ROW, DATA_ROW = 5, 6, 7

    col_ids   = [str(ws.cell_value(ID_ROW, j)).split('.')[0].strip() for j in range(ws.ncols)]
    col_names = [str(ws.cell_value(NAME_ROW, j)).strip() for j in range(ws.ncols)]

    rows = []
    for i in range(DATA_ROW, ws.nrows):
        row = {}
        for j in range(ws.ncols):
            val = ws.cell_value(i, j)
            if col_names[j] and str(val).strip() not in ('', 'nan'):
                row[col_names[j]] = val
        if row.get(col_names[0], ''):
            rows.append(row)

    if not rows:
        raise ValueError(
            "Nessun utensile trovato nel file XLS Cimatron.\n"
            "Il file sembra un template vuoto. Esporta gli utensili da:\n"
            "NC-Process -> Utensili -> seleziona tutto -> Export -> XLS"
        )

    df = pd.DataFrame(rows)
    mapping = _mapping_da_ids(col_names, col_ids)
    val_cat = _valori_categoria(df, mapping)
    mapped_cols = {v['colonna_file'] for v in mapping.values()}

    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': val_cat,
        'colonne_non_mappate': [c for c in df.columns if c not in mapped_cols],
        'anteprima': df.head(5).to_dict(orient='records'),
        'df': df, 'software_rilevato': 'cimatron',
        'versione_rilevata': versione, 'parser_usato': 'cimatron_xls',
    }


def leggi_cimatron_csv(filepath: str) -> dict:
    """Legge un file CSV Cimatron (UTF-16, pipe-separato)."""
    with open(filepath, 'rb') as f:
        content = f.read()

    df, col_names, col_ids, versione = _leggi_csv_cimatron(content, os.path.basename(filepath))
    mapping = _mapping_da_ids(col_names, col_ids)
    val_cat = _valori_categoria(df, mapping)
    mapped_cols = {v['colonna_file'] for v in mapping.values()}

    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': val_cat,
        'colonne_non_mappate': [c for c in df.columns if c not in mapped_cols],
        'anteprima': df.head(5).to_dict(orient='records'),
        'df': df, 'software_rilevato': 'cimatron',
        'versione_rilevata': versione, 'parser_usato': 'cimatron_csv',
    }


def leggi_cimatron_zip(filepath: str) -> dict:
    """
    Legge un ZIP Cimatron (Cutters + Material opzionale).
    Struttura ZIP attesa:
      NomeCartella/Cutters_*.csv    <- utensili principali
      NomeCartella/Material_*.csv   <- dati di taglio per materiale (opzionale)
      NomeCartella/Holders_*.csv    <- portautensili (per uso futuro)
    """
    with zipfile.ZipFile(filepath, 'r') as z:
        nomi = z.namelist()

        # Trova Cutters_*.csv
        cutters_file = next(
            (n for n in nomi if 'Cutters' in os.path.basename(n) and n.endswith('.csv')), None
        )
        if not cutters_file:
            raise ValueError("ZIP Cimatron: file Cutters_*.csv non trovato")

        with z.open(cutters_file) as f:
            content_cutters = f.read()

        # Trova Material_*.csv (dati di taglio, opzionale)
        material_file = next(
            (n for n in nomi if 'Material' in os.path.basename(n) and n.endswith('.csv')), None
        )
        df_material = None
        if material_file:
            with z.open(material_file) as f:
                content_mat = f.read()
            try:
                df_material, mn, mi, _ = _leggi_csv_cimatron(content_mat, 'Material')
            except Exception:
                df_material = None

    df, col_names, col_ids, versione = _leggi_csv_cimatron(content_cutters, 'Cutters')
    mapping = _mapping_da_ids(col_names, col_ids)
    val_cat = _valori_categoria(df, mapping)
    mapped_cols = {v['colonna_file'] for v in mapping.values()}

    # Aggiungi dati di taglio come info extra (non mappati nel master ora)
    extra_info = {}
    if df_material is not None:
        extra_info['dati_taglio'] = f"{len(df_material)} combinazioni utensile/materiale nel file Material"

    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': val_cat,
        'colonne_non_mappate': [c for c in df.columns if c not in mapped_cols],
        'anteprima': df.head(5).to_dict(orient='records'),
        'df': df, 'software_rilevato': 'cimatron',
        'versione_rilevata': versione, 'parser_usato': 'cimatron_zip',
        'extra_info': extra_info,
        'df_material': df_material,
    }
