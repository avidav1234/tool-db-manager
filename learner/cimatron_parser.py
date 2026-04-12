"""
cimatron_parser.py
==================
Parser dedicato per tutti i formati di export Cimatron.

Formati supportati:
  - XLS nativo  (foglio 'Cutters', header multi-riga con ID numerici)
  - CSV singolo (UTF-16, separatore |, righe // commento)
  - ZIP         (Cutters_*.csv + Material_*.csv + Holders_*.csv)

Mappatura COMPLETA di tutti gli ID Cimatron noti (157 colonne possibili).
Le colonne non mappate vengono passate all'agente AI.
"""

import os
import io
import zipfile
import pandas as pd

# ---------------------------------------------------------------
# MAPPATURA COMPLETA ID Cimatron -> campo master
# Fonte: analisi reale file Cimatron 2025 SP5 (157 colonne)
# ---------------------------------------------------------------
CIMATRON_ID_MAP = {
    # --- IDENTIFICAZIONE ---
    '1101': ('codice_interno',       'string'),   # Nome Utensile
    '1102': ('descrizione',           'string'),   # Commento
    '1103': ('sito_web',              'string'),   # Sito web
    '2103': ('codice_catalogo',       'string'),   # Nome Catalogo

    # --- TIPO E TECNOLOGIA ---
    '2101': ('tecnologia',            'categoria'),# Tecnologia (Fresatura/Foratura)
    '2102': ('tipo',                  'categoria'),# Punta/Tipo (FLAT/BALL/BULL...)
    '2104': ('tipo_filetto',          'string'),   # Tipo Filetto

    # --- GEOMETRIA PRINCIPALE ---
    '2105': ('diametro_mm',           'float'),    # Diametro
    '2106': ('raggio_punta_mm',       'float'),    # Raggio Base (corner radius)
    '2107': ('usa_lunghezza_totale',  'int'),      # Usa Lunghezza Totale (flag)
    '2108': ('lunghezza_totale_mm',   'float'),    # Lunghezza Totale Ut.
    '2109': ('lunghezza_tagl_mm',     'float'),    # Lunghezza Utile (clear length)
    '2110': ('lunghezza_tagl2_mm',    'float'),    # Lunghezza Taglio secondaria
    '2111': ('conico',                'int'),      # Conico (flag)
    '2112': ('angolo_conico_gradi',   'float'),, 'float'),    # Angolo Conicità (helix/taper)
    '2113': ('angolo_punta_gradi',    'float'),    # Angolo Punta
    '2114': ('diam_libero_mm',        'float'),    # Diametro Libero (stylus)
    '2115': ('altezza_cilindro_mm',   'float'),    # Altezza Cilindro
    '2116': ('diam_base_piatta_mm',   'float'),    # Diametro Base Piatta
    '2117': ('centro_arco_y_mm',      'float'),    # Centro Arco Y (profilo)
    '2118': ('diam_stelo_mm',         'float'),    # Diametro Gambo/Stelo
    '2119': ('usa_base_piatta',       'int'),      # Usa Base Piatta (flag)
    '2120': ('usa_lunghezza_taglio',  'int'),      # Usa Lunghezza Taglio (flag)
    '2121': ('raggio_punta2_mm',      'float'),    # Raggio Punta (tip radius)
    '2122': ('raggio_superiore_mm',   'float'),    # Raggio Superiore
    '2123': ('passo_mm',              'float'),    # Passo (pitch filetto)
    '2124': ('num_filetti',           'int'),      # Numero Filetti
    '2125': ('usa_diam_gambo',        'int'),      # Usa Diametro Gambo (flag)
    '2126': ('lunghezza_conica_mm',   'float'),    # Lunghezza Conica
    '2127': ('usa_angolo_conico',     'int'),      # Usa Angolo Conico (flag)
    '2129': ('altezza_raggio_sup_mm', 'float'),    # Altezza Raggio Superiore
    '2130': ('raggio_profilo_mm',     'float'),    # Raggio Profilo

    # --- GAMBO (SHANK) ---
    '2201': ('diam_gambo1_mm',        'float'),    # Gambo 1 (Shank1)
    '2202': ('diam_gambo_top_mm',     'float'),    # Diametro Gambo Top
    '2203': ('diam_gambo_bot_mm',     'float'),    # Diametro Gambo Bottom
    '2204': ('usa_angolo_gambo',      'int'),      # Usa Angolo Conico Gambo
    '2206': ('lunghezza_gambo_mm',    'float'),    # Lunghezza Cono Gambo

    # --- PARAMETRI MACCHINA ---
    '1201': ('numero_magazzino',      'int'),      # Numero Magazzino (Magazine No.)
    '1202': ('comp_diametro',         'float'),    # Compensazione Diametro
    '1203': ('comp_lunghezza',        'float'),    # Compensazione Lunghezza
    '4203': ('dir_rotazione',         'categoria'),# Direzione Mandrino
    '4204': ('refrigerante',          'categoria'),# Refrigerante
    '4210': ('metodo_visualiz',       'categoria'),# Metodo Visualizzazione
    '4212': ('connessione',           'categoria'),# Connessione (pass successivo)

    # --- PARAMETRI MOTO ---
    '5107': ('modo_taglio',           'categoria'),# Modo Taglio (concordante/discordante)
    '5108': ('direzione_crollo',      'categoria'),# Direzione Crollo
    '5109': ('collasso',              'categoria'),# Collasso Su/Giu

    # --- CICLI FORATURA ---
    '6101': ('ciclo_foratura',        'categoria'),# Ciclo Foratura
    '6102': ('shift_mm',              'float'),    # Shift
    '6105': ('dwell_s',               'float'),    # Dwell
    '6107': ('peck_mm',               'float'),    # Peck

    # --- PORTA UTENSILE ---
    '7001': ('nome_portautensile',    'string'),   # Nome Porta Utensile
    '7002': ('nome_materiale_pu',     'string'),   # Nome Materiale (portautensile)
    '7900': ('e_fisso',               'int'),      # E Fisso (flag)
    '9002': ('tipo_elemento',         'categoria'),# Tipo (Cutter/Holder/Extension)

    # --- PARAMETRI TAGLIO DEFAULT ---
    '4101': ('avanzamento_default',   'float'),    # Avanzamento Vf mm/min
    '4102': ('rotazione_default',     'float'),    # Rotazione RPM
    '4103': ('vc_default',            'float'),    # Velocita taglio Vc m/min
    '4104': ('fz_default',            'float'),    # Avanzamento per dente Fz mm/z
    '4106': ('num_taglienti',         'int'),      # Numero denti/taglienti
    '4202': ('vita_utensile',         'int'),      # Vita utensile
    '4203': ('dir_rotazione',         'categoria'),# Direzione mandrino
    '4204': ('refrigerante',          'categoria'),# Tipo refrigerante
    '5101': ('passo_z_default',       'float'),    # Passo in Z (ap)
    '5102': ('passo_lat_default',     'float'),    # Passo laterale (ae)
    '5106': ('tolleranza_default',    'float'),    # Tolleranza
}

# Valori Punta/Tipo -> tipo master
TIPO_ID_MAP = {
    '210201': 'FLAT',  '210202': 'BALL',  '210203': 'BULL',
    '210204': 'DRILL', '210205': 'REAM',  '210206': 'TAP',
    '210207': 'SPOT',  '210208': 'BALL',  '210209': 'BULL',
    '210210': 'TAPER',
}
TIPO_STR_MAP = {
    'flat':'FLAT', 'piana':'FLAT', 'ball':'BALL', 'sferica':'BALL',
    'bull':'BULL', 'torica':'BULL', 'drilling':'DRILL', 'foratura':'DRILL',
    'ream':'REAM', 'tap':'TAP', 'filettatura':'TAP',
    'center':'SPOT', 'centratura':'SPOT', 'taper':'TAPER',
}

# Campi da NON mostrare nella UI (flags interni, non utili per l'operatore)
CAMPI_INTERNI = {
    'usa_lunghezza_totale', 'conico', 'usa_base_piatta', 'usa_lunghezza_taglio',
    'usa_diam_gambo', 'usa_angolo_conico', 'usa_angolo_gambo', 'e_fisso',
    'comp_diametro', 'comp_lunghezza',
}


def _decodifica_tipo(val: str) -> str:
    v = str(val).strip()
    return TIPO_ID_MAP.get(v, TIPO_STR_MAP.get(v.lower(), '?'))


def _ssl_context():
    """Crea contesto SSL che funziona su Mac con certifi."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    try:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations('/etc/ssl/cert.pem')
        return ctx
    except Exception:
        pass
    return ssl.create_default_context()


def _leggi_csv_cimatron(content_bytes: bytes, nome_file: str = '') -> tuple:
    """
    Legge il contenuto binario di un CSV Cimatron (UTF-16, pipe-separato).
    Ritorna (DataFrame, col_names, col_ids, versione).

    Struttura attesa:
      righe 0-4:  // commenti e header validazione
      riga 5:     CimatronE2025.00|1000|96|...  (metadati)
      riga 6:     (vuota)
      riga 7:     Nomi colonne localizzati (italiano/inglese)
      riga 8:     ID colonne numerici (1101|1102|2101|...)
      riga 9+:    Dati utensili
    """
    for enc in ('utf-16', 'utf-8-sig', 'utf-8', 'latin-1'):
        try:
            text = content_bytes.decode(enc)
            if 'CimatronE' in text or '1101' in text:
                break
        except Exception:
            continue

    lines = text.splitlines()
    nome_riga = id_riga = dati_start = -1
    versione = ''

    for i, line in enumerate(lines):
        stripped = line.strip().lstrip('"')
        if stripped.startswith('CimatronE') and '//' not in stripped[:3]:
            versione = stripped.split('|')[0]
            continue
        if stripped.startswith('//') or stripped == '':
            continue
        if nome_riga == -1:
            nome_riga = i
            continue
        if id_riga == -1:
            id_riga = i
            dati_start = i + 1
            break

    if nome_riga == -1 or id_riga == -1:
        raise ValueError(f"Struttura CSV Cimatron non riconosciuta in {nome_file}")

    col_names = [c.strip() for c in lines[nome_riga].split('|')]
    col_ids   = [c.strip() for c in lines[id_riga].split('|')]

    rows = []
    for line in lines[dati_start:]:
        if not line.strip() or line.strip().startswith('//'):
            continue
        parts = line.split('|')
        row = {col_names[j]: parts[j].strip()
               for j in range(min(len(col_names), len(parts)))
               if col_names[j]}
        if col_names and row.get(col_names[0], '').strip():
            rows.append(row)

    if not rows:
        raise ValueError(
            f"Nessun utensile trovato in {nome_file}.\n"
            "Verifica che il file contenga utensili e non sia un template vuoto."
        )

    df_raw = pd.DataFrame(rows)

    # Decodifica colonne categoria (sostituisce codici numerici con valori leggibili)
    _DECODE_COLS = {
        # col_id: decode_map
        '2101': {'210101':'Fresatura','210102':'Foratura','210103':'Filettatura',
                 '210104':'Alesatura','210105':'Barenatura','210106':'Tornitura'},
        '2102': {'210201':'FLAT','210202':'BALL','210203':'BULL','210204':'DRILL',
                 '210205':'TAP','210206':'REAM','210207':'SPOT','210208':'THREAD',
                 '210209':'TAPER','210210':'FORM','210211':'LOLLIPOP'},
        '4203': {'420301':'CW','420302':'CCW'},
        '4204': {'420401':'OFF','420402':'FLOOD','420403':'MIST','420404':'AIR','420405':'THROUGH'},
    }
    id_to_nome = dict(zip(col_ids, col_names))  # es. '2102' -> 'Punta/Tipo'
    for cid, dmap in _DECODE_COLS.items():
        # trova il nome colonna corrispondente all'ID
        col_nome = id_to_nome.get(cid)
        if col_nome and col_nome in df_raw.columns:
            df_raw[col_nome] = df_raw[col_nome].map(
                lambda v: dmap.get(str(v).strip(), v) if pd.notna(v) else v
            )

    return df_raw, col_names, col_ids, versione


def _mapping_da_ids(col_names: list, col_ids: list) -> dict:
    """Costruisce mappatura campo_master -> info usando gli ID numerici."""
    mapping = {}
    for j, cid_raw in enumerate(col_ids):
        if j >= len(col_names):
            break
        cid  = cid_raw.split('.')[0].strip()
        nome = col_names[j]
        if not cid or not nome:
            continue
        if cid in CIMATRON_ID_MAP:
            campo, tipo = CIMATRON_ID_MAP[cid]
            if campo in CAMPI_INTERNI:
                continue  # salta flags interni
            entry = {
                'colonna_file': nome,
                'score':        10.0,
                'tipo':         tipo,
                'label':        nome,
                'confidenza':   'alta',
                'id_cimatron':  cid,
            }
            # Aggiunge decode_map per i campi categoria
            if cid == '2101':  # tecnologia
                entry['decode_map'] = {'210101':'Fresatura','210102':'Foratura',
                    '210103':'Filettatura','210104':'Alesatura',
                    '210105':'Barenatura','210106':'Tornitura'}
            elif cid == '2102':  # tipo utensile
                entry['decode_map'] = {'210201':'FLAT','210202':'BALL','210203':'BULL',
                    '210204':'DRILL','210205':'TAP','210206':'REAM',
                    '210207':'SPOT','210208':'THREAD','210209':'TAPER',
                    '210210':'FORM','210211':'LOLLIPOP'}
            elif cid == '4203':  # direzione rotazione
                entry['decode_map'] = {'420301':'CW','420302':'CCW'}
            elif cid == '4204':  # refrigerante
                entry['decode_map'] = {'420401':'OFF','420402':'FLOOD',
                    '420403':'MIST','420404':'AIR','420405':'THROUGH'}
            mapping[campo] = entry
    return mapping


def _valori_categoria(df: pd.DataFrame, mapping: dict) -> dict:
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
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.xls':
        try:
            import xlrd
            return 'Cutters' in xlrd.open_workbook(filepath).sheet_names()
        except Exception:
            return False
    if ext == '.csv':
        try:
            with open(filepath, 'rb') as f:
                raw = f.read(500)
            text = raw.decode('utf-16', errors='ignore')
            return 'CimatronE' in text or ('1101' in text and '//' in text)
        except Exception:
            return False
    if ext == '.zip':
        try:
            with zipfile.ZipFile(filepath) as z:
                return any('Cutters' in os.path.basename(n) and n.endswith('.csv')
                           for n in z.namelist())
        except Exception:
            return False
    return False


def leggi_cimatron_xls(filepath: str) -> dict:
    import xlrd
    wb  = xlrd.open_workbook(filepath)
    ws  = wb.sheet_by_name('Cutters')
    versione = ''
    for i in range(min(7, ws.nrows)):
        for j in range(min(3, ws.ncols)):
            v = str(ws.cell_value(i, j))
            if 'Cimatron' in v:
                versione = v.strip(); break

    ID_ROW, NAME_ROW, DATA_ROW = 5, 6, 7
    col_ids   = [str(ws.cell_value(ID_ROW, j)).split('.')[0].strip() for j in range(ws.ncols)]
    col_names = [str(ws.cell_value(NAME_ROW, j)).strip() for j in range(ws.ncols)]

    rows = []
    for i in range(DATA_ROW, ws.nrows):
        row = {col_names[j]: ws.cell_value(i, j)
               for j in range(ws.ncols)
               if col_names[j] and str(ws.cell_value(i, j)).strip() not in ('', 'nan')}
        if row.get(col_names[0], ''):
            rows.append(row)

    if not rows:
        raise ValueError("Nessun utensile nel file XLS Cimatron (template vuoto?)")

    df = pd.DataFrame(rows)
    mapping = _mapping_da_ids(col_names, col_ids)
    mapped  = {v['colonna_file'] for v in mapping.values()}
    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': _valori_categoria(df, mapping),
        'colonne_non_mappate': [c for c in df.columns if c not in mapped],
        'anteprima': df.head(5).to_dict('records'), 'df': df,
        'software_rilevato': 'cimatron', 'versione_rilevata': versione,
        'parser_usato': 'cimatron_xls',
    }


def leggi_cimatron_csv(filepath: str) -> dict:
    with open(filepath, 'rb') as f:
        content = f.read()
    df, col_names, col_ids, versione = _leggi_csv_cimatron(content, os.path.basename(filepath))
    mapping = _mapping_da_ids(col_names, col_ids)
    mapped  = {v['colonna_file'] for v in mapping.values()}
    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': _valori_categoria(df, mapping),
        'colonne_non_mappate': [c for c in df.columns if c not in mapped],
        'anteprima': df.head(5).to_dict('records'), 'df': df,
        'software_rilevato': 'cimatron', 'versione_rilevata': versione,
        'parser_usato': 'cimatron_csv',
    }


def leggi_cimatron_zip(filepath: str) -> dict:
    with zipfile.ZipFile(filepath) as z:
        nomi = z.namelist()
        cutters_f = next(
            (n for n in nomi if 'Cutters' in os.path.basename(n) and n.endswith('.csv')), None)
        if not cutters_f:
            raise ValueError("ZIP: Cutters_*.csv non trovato")
        with z.open(cutters_f) as f:
            cc = f.read()

        mat_f = next(
            (n for n in nomi if 'Material' in os.path.basename(n) and n.endswith('.csv')), None)
        df_mat = None
        if mat_f:
            with z.open(mat_f) as f:
                cm = f.read()
            try:
                df_mat, _, _, _ = _leggi_csv_cimatron(cm, 'Material')
            except Exception:
                pass

    df, col_names, col_ids, versione = _leggi_csv_cimatron(cc, 'Cutters')
    mapping = _mapping_da_ids(col_names, col_ids)
    mapped  = {v['colonna_file'] for v in mapping.values()}
    extra   = {}
    if df_mat is not None:
        extra['dati_taglio'] = f"{len(df_mat)} combinazioni utensile/materiale (Vc, Fz, RPM)"

    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': _valori_categoria(df, mapping),
        'colonne_non_mappate': [c for c in df.columns if c not in mapped],
        'anteprima': df.head(5).to_dict('records'), 'df': df,
        'software_rilevato': 'cimatron', 'versione_rilevata': versione,
        'parser_usato': 'cimatron_zip', 'extra_info': extra, 'df_material': df_mat,
    }
