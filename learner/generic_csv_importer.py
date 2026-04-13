"""
generic_csv_importer.py
=======================
Importatore universale CSV / TSV / Excel -> Tool DB Manager master database.

Gestisce file da qualsiasi sistema CAM (SolidCAM, CAMWorks, NX, custom, ecc.)
con auto-rilevamento di:
  - Delimitatore (virgola, punto e virgola, tab, pipe)
  - Encoding (UTF-8, UTF-16, Latin-1, cp1252)
  - Mapping colonne (auto-detect per nome header in piu' lingue)

Uso:
  from generic_csv_importer import importa_csv_generico
  result = importa_csv_generico('tools.csv', 'database/tool_master.db', dry_run=True)
"""

import csv
import io
import os
import re
import sqlite3
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# COLUMN ALIAS MAPS  (canonical_field -> set of recognized header names)
# All matching is case-insensitive after stripping/normalizing.
# ---------------------------------------------------------------------------

_COLUMN_ALIASES = {
    # -- Identification --
    'codice_interno': {
        'name', 'tool_name', 'nome', 'codice', 'code', 'description',
        'bezeichnung', 'tool', 'tool_id', 'codice_interno', 'id',
        'tool_description', 'cutter_name', 'utensile',
    },
    'diametro_mm': {
        'diameter', 'diametro', 'diam', 'd', 'durchmesser', 'dc',
        'diametro_mm', 'tool_diameter', 'cutter_diameter', 'd1',
        'cutting_diameter',
    },
    'raggio_punta_mm': {
        'corner_radius', 'raggio', 'radius', 're', 'eckenradius', 'cr',
        'raggio_punta', 'raggio_punta_mm', 'corner_rad', 'tip_radius',
        'nose_radius',
    },
    'lunghezza_totale_mm': {
        'overall_length', 'lunghezza_totale', 'oal', 'gesamtlange',
        'gesamtl\u00e4nge', 'length', 'lunghezza_totale_mm', 'total_length',
        'tool_length', 'l', 'l1',
    },
    'lunghezza_tagl_mm': {
        'flute_length', 'lunghezza_tagl', 'lcf', 'schneidenlange',
        'schneidenl\u00e4nge', 'cutting_length', 'lunghezza_tagl_mm',
        'flute_len', 'loc', 'lc', 'cut_length', 'cutting_edge_length',
    },
    'num_taglienti': {
        'flutes', 'num_flutes', 'taglienti', 'nof', 'schneiden', 'teeth',
        'z', 'num_taglienti', 'number_of_flutes', 'zn', 'flute_count',
        'n_flutes',
    },
    'tipo_raw': {
        'type', 'tipo', 'typ', 'tool_type', 'cutter_type', 'tipo_utensile',
        'werkzeugtyp',
    },
    'diam_stelo_mm': {
        'shank_diameter', 'diam_stelo', 'shank', 'schaftdurchmesser',
        'diam_stelo_mm', 'shank_diam', 'ds', 'd2',
    },
    'rotazione_default': {
        'rpm', 'n', 'rotazione', 'drehzahl', 'spindle_speed',
        'rotazione_default', 'speed', 'spindle_rpm',
    },
    'avanzamento_default': {
        'feedrate', 'feed', 'vf', 'avanzamento', 'vorschub',
        'avanzamento_default', 'feed_rate', 'feedrate_mm_min',
    },
    'vc_default': {
        'vc', 'cutting_speed', 'velocita_taglio', 'velocit\u00e0_taglio',
        'schnittgeschwindigkeit', 'vc_default', 'vc_m_min',
    },
    'fz_default': {
        'fz', 'feed_per_tooth', 'fz_mm_z', 'vorschub_pro_zahn',
        'fz_default', 'feed_tooth',
    },
    'passo_z_default': {
        'ap', 'step_down', 'passo_z', 'zustellung_axial',
        'passo_z_default', 'depth_of_cut', 'axial_depth', 'ap_mm',
    },
    'passo_lat_default': {
        'ae', 'step_over', 'passo_lat', 'zustellung_radial',
        'passo_lat_default', 'radial_depth', 'width_of_cut', 'ae_mm',
    },
    'nome_pinza': {
        'holder', 'portautensile', 'pinza', 'nome_pinza', 'aufnahme',
        'holder_name', 'holder_id', 'chuck',
    },
    'fuori_pinza_mm': {
        'stick_out', 'fuori_pinza', 'gauge_length', 'auskraglange',
        'auskragl\u00e4nge', 'fuori_pinza_mm', 'stickout', 'projection',
        'gage_length',
    },
    'materiale_raw': {
        'material', 'materiale', 'werkstoff', 'tool_material',
        'cutter_material', 'mat',
    },
    # -- Extra common columns --
    'descrizione': {
        'desc', 'comment', 'commento', 'bemerkung', 'remarks', 'note',
        'notes', 'descrizione',
    },
    'angolo_punta_gradi': {
        'point_angle', 'angolo_punta', 'spitzenwinkel', 'drill_angle',
        'angolo_punta_gradi', 'tip_angle',
    },
    'angolo_elica_gradi': {
        'helix_angle', 'angolo_elica', 'drallwinkel', 'angolo_elica_gradi',
    },
    'codice_catalogo': {
        'catalog', 'catalog_number', 'part_number', 'codice_catalogo',
        'articolo', 'artikelnummer', 'order_code', 'product_id',
    },
}

# Build a reverse lookup: normalized_alias -> canonical_field
_ALIAS_REVERSE = {}
for _field, _aliases in _COLUMN_ALIASES.items():
    for _a in _aliases:
        _ALIAS_REVERSE[_a.lower()] = _field


# ---------------------------------------------------------------------------
# TOOL TYPE DETECTION
# ---------------------------------------------------------------------------

_TYPE_PATTERNS = [
    # order matters: more specific first
    (re.compile(r'\b(ball\s*(nose|mill|end)?|sferica|kugelkopf)\b', re.I), 'BALL'),
    (re.compile(r'\b(bull\s*(nose)?|torus|torica|torusfr[ae]s)\b', re.I),  'BULL'),
    (re.compile(r'\b(lollipop|t[\-\s]?slot|fresa\s*a\s*t)\b', re.I),      'LOLLIPOP'),
    (re.compile(r'\b(thread\s*mill|filettatore|gewindefr[ae]s)\b', re.I),  'THREAD'),
    (re.compile(r'\b(spot\s*drill|centratore|zentrierbohr|centring)\b', re.I), 'SPOT'),
    (re.compile(r'\b(tap|maschio|gewindebohr)\b', re.I),                    'TAP'),
    (re.compile(r'\b(ream|alesatore|reibahle)\b', re.I),                    'REAM'),
    (re.compile(r'\b(drill|punta|bohr)\b', re.I),                          'DRILL'),
    (re.compile(r'\b(boring|barra\s*di\s*ales|ausbohrstange)\b', re.I),    'BORING'),
    (re.compile(r'\b(taper|conic[oa]|kegelsenk)\b', re.I),                 'TAPER'),
    (re.compile(r'\b(form|sagomato|formfr[ae]s)\b', re.I),                 'FORM'),
    (re.compile(r'\b(flat|end\s*mill|piatta|schaft|fresa\s*piana)\b', re.I), 'FLAT'),
]


def _detect_tool_type(raw_value):
    """Return a tipo_utensile codice from a free-text type string, or None."""
    if not raw_value:
        return None
    s = str(raw_value).strip()
    if not s:
        return None
    # Direct match on known codes
    upper = s.upper()
    if upper in ('FLAT', 'BALL', 'BULL', 'DRILL', 'TAP', 'REAM', 'SPOT',
                 'TAPER', 'THREAD', 'FORM', 'LOLLIPOP', 'BORING', 'TURN'):
        return upper
    for pattern, tipo in _TYPE_PATTERNS:
        if pattern.search(s):
            return tipo
    return None


# ---------------------------------------------------------------------------
# MATERIAL DETECTION
# ---------------------------------------------------------------------------

_MATERIAL_PATTERNS = [
    (re.compile(r'\b(pcd|diamante|polycristalline?\s*diamond)\b', re.I), 'PCD'),
    (re.compile(r'\b(cbn|nitruro\s*di\s*boro|cubic\s*boron)\b', re.I),  'CBN'),
    (re.compile(r'\b(ceramic[ao]?|keramik)\b', re.I),                    'CERAMICA'),
    (re.compile(r'\b(cermet)\b', re.I),                                   'CERMET'),
    (re.compile(r'\b(hss[\-\s]*e|acciaio\s*rapido\s*co|cobalt\s*hss)\b', re.I), 'HSS-E'),
    (re.compile(r'\b(hss|acciaio\s*rapido|high\s*speed\s*steel|schnellarbeitsstahl)\b', re.I), 'HSS'),
    (re.compile(r'\b(hm|carbide|metallo\s*duro|hartmetall|carburo|vhm|solid\s*carbide|wc)\b', re.I), 'HM'),
]


def _detect_material(raw_value):
    """Return a materiale_utensile codice from a free-text material string, or None."""
    if not raw_value:
        return None
    s = str(raw_value).strip()
    if not s:
        return None
    upper = s.upper()
    if upper in ('HM', 'HSS', 'HSS-E', 'CBN', 'PCD', 'CERAMICA', 'CERMET'):
        return upper
    for pattern, mat in _MATERIAL_PATTERNS:
        if pattern.search(s):
            return mat
    return None


# ---------------------------------------------------------------------------
# ENCODING & DELIMITER DETECTION
# ---------------------------------------------------------------------------

def _detect_encoding(filepath):
    """Detect file encoding from BOM or heuristic sampling."""
    with open(filepath, 'rb') as f:
        raw = f.read(8192)
    # BOM detection
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return 'utf-16'
    # Heuristic: try UTF-8 first, then Latin-1
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, ValueError):
            continue
    return 'latin-1'  # fallback


def _detect_delimiter(sample_text):
    """Detect delimiter from a text sample (first few lines)."""
    lines = sample_text.strip().splitlines()
    if len(lines) < 2:
        return ','
    # Use csv.Sniffer first
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=',;\t|')
        return dialect.delimiter
    except csv.Error:
        pass
    # Count occurrences of common delimiters in the first header + data lines
    candidates = [(',', 0), (';', 0), ('\t', 0), ('|', 0)]
    header = lines[0]
    results = []
    for delim, _ in candidates:
        count = header.count(delim)
        if count > 0:
            results.append((delim, count))
    if results:
        results.sort(key=lambda x: x[1], reverse=True)
        return results[0][0]
    return ','


# ---------------------------------------------------------------------------
# FILE READING (CSV / TSV / Excel)
# ---------------------------------------------------------------------------

def _read_tabular_file(filepath):
    """
    Read a CSV/TSV/TXT/XLS/XLSX file into a list of dicts.
    Returns (rows: list[dict], detected_info: dict).
    """
    ext = os.path.splitext(filepath)[1].lower()
    info = {'encoding': None, 'delimiter': None, 'format': ext}

    # --- Excel ---
    if ext in ('.xlsx', '.xls'):
        return _read_excel(filepath, info)

    # --- CSV / TSV / TXT ---
    encoding = _detect_encoding(filepath)
    info['encoding'] = encoding

    with open(filepath, 'r', encoding=encoding, errors='replace') as f:
        sample = f.read(16384)

    # Strip comment lines (Cimatron-style // prefixes, etc.)
    clean_lines = [l for l in sample.splitlines()
                   if l.strip() and not l.strip().startswith('//') and not l.strip().startswith('#')]
    if not clean_lines:
        return [], info

    clean_sample = '\n'.join(clean_lines)
    delimiter = _detect_delimiter(clean_sample)
    info['delimiter'] = delimiter

    # Re-read the full file
    with open(filepath, 'r', encoding=encoding, errors='replace') as f:
        all_lines = [l for l in f
                     if l.strip() and not l.strip().startswith('//') and not l.strip().startswith('#')]

    reader = csv.DictReader(all_lines, delimiter=delimiter)
    rows = []
    for row in reader:
        # Skip completely empty rows
        if all(v is None or str(v).strip() == '' for v in row.values()):
            continue
        rows.append(row)

    return rows, info


def _read_excel(filepath, info):
    """Read an Excel file using openpyxl (xlsx) or xlrd (xls)."""
    ext = os.path.splitext(filepath)[1].lower()
    rows = []

    if ext == '.xlsx':
        try:
            import openpyxl
        except ImportError:
            # Fallback to pandas if openpyxl not available
            return _read_excel_pandas(filepath, info)

        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not all_rows:
            return [], info

        headers = [str(h).strip() if h is not None else f'col_{i}'
                   for i, h in enumerate(all_rows[0])]
        for data_row in all_rows[1:]:
            if all(c is None or str(c).strip() == '' for c in data_row):
                continue
            row_dict = {}
            for i, val in enumerate(data_row):
                if i < len(headers):
                    row_dict[headers[i]] = val
            rows.append(row_dict)
        info['format'] = 'xlsx/openpyxl'
        return rows, info

    elif ext == '.xls':
        try:
            import xlrd
        except ImportError:
            return _read_excel_pandas(filepath, info)

        wb = xlrd.open_workbook(filepath)
        ws = wb.sheet_by_index(0)
        if ws.nrows < 2:
            return [], info
        headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
        for r in range(1, ws.nrows):
            vals = [ws.cell_value(r, c) for c in range(ws.ncols)]
            if all(v is None or str(v).strip() == '' for v in vals):
                continue
            row_dict = {}
            for i, val in enumerate(vals):
                if i < len(headers):
                    row_dict[headers[i]] = val
            rows.append(row_dict)
        info['format'] = 'xls/xlrd'
        return rows, info

    return _read_excel_pandas(filepath, info)


def _read_excel_pandas(filepath, info):
    """Fallback: read Excel via pandas."""
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "Per leggere file Excel serve openpyxl, xlrd, oppure pandas. "
            "Installa con: pip install openpyxl pandas"
        )
    df = pd.read_excel(filepath)
    df.columns = [str(c).strip() for c in df.columns]
    rows = df.where(df.notnull(), None).to_dict('records')
    info['format'] = 'excel/pandas'
    return rows, info


# ---------------------------------------------------------------------------
# COLUMN MAPPING
# ---------------------------------------------------------------------------

def _normalize_header(header):
    """Normalize a column header for matching."""
    s = str(header).strip().lower()
    # Replace common separators with underscore
    s = re.sub(r'[\s\-\.]+', '_', s)
    # Remove parenthetical units: "Diameter (mm)" -> "diameter"
    s = re.sub(r'\([^)]*\)', '', s).strip('_').strip()
    return s


def _build_column_map(raw_headers):
    """
    Map raw CSV/Excel headers -> canonical DB field names.
    Returns dict: {raw_header: canonical_field}
    """
    col_map = {}
    used_fields = set()

    for raw in raw_headers:
        norm = _normalize_header(raw)
        if norm in _ALIAS_REVERSE:
            field = _ALIAS_REVERSE[norm]
            if field not in used_fields:
                col_map[raw] = field
                used_fields.add(field)

    return col_map


# ---------------------------------------------------------------------------
# VALUE PARSING
# ---------------------------------------------------------------------------

def _to_float(val, default=None):
    """Parse a value to float, handling comma decimals."""
    if val is None:
        return default
    s = str(val).strip()
    if s in ('', 'nan', 'None', 'N/A', '-', 'n/a', '#N/A'):
        return default
    try:
        return float(s)
    except ValueError:
        pass
    # Try comma as decimal separator
    try:
        return float(s.replace(',', '.'))
    except ValueError:
        pass
    # Try removing thousands separator (1.234,56 -> 1234.56)
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except ValueError:
        return default


def _to_int(val, default=None):
    """Parse a value to int."""
    f = _to_float(val)
    if f is None:
        return default
    try:
        return int(round(f))
    except (ValueError, OverflowError):
        return default


def _to_str(val, default=None):
    """Parse a value to non-empty string or default."""
    if val is None:
        return default
    s = str(val).strip()
    if s in ('', 'nan', 'None', 'N/A'):
        return default
    return s


# ---------------------------------------------------------------------------
# DB HELPERS
# ---------------------------------------------------------------------------

def _get_tipo_id(conn, codice):
    """Get tipo_utensile.id for a codice, fallback to FLAT."""
    if codice:
        row = conn.execute(
            "SELECT id FROM tipo_utensile WHERE codice = ?", (codice,)
        ).fetchone()
        if row:
            return row['id']
    # Default to FLAT
    row = conn.execute(
        "SELECT id FROM tipo_utensile WHERE codice = 'FLAT'"
    ).fetchone()
    return row['id'] if row else 1


def _get_materiale_id(conn, codice):
    """Get materiale_utensile.id for a codice, fallback to HM."""
    if codice:
        row = conn.execute(
            "SELECT id FROM materiale_utensile WHERE codice = ?", (codice,)
        ).fetchone()
        if row:
            return row['id']
    # Default to HM
    row = conn.execute(
        "SELECT id FROM materiale_utensile WHERE codice = 'HM'"
    ).fetchone()
    return row['id'] if row else 1


# ---------------------------------------------------------------------------
# MAIN IMPORT FUNCTION
# ---------------------------------------------------------------------------

def importa_csv_generico(filepath, master_db_path, dry_run=False):
    """
    Import a generic CSV/TSV/Excel tool library into the Tool DB Manager
    master database.

    Parameters
    ----------
    filepath : str
        Path to the input file (.csv, .tsv, .txt, .xls, .xlsx).
    master_db_path : str
        Path to the SQLite master database (tool_master.db).
    dry_run : bool
        If True, do not write to the database, just report what would happen.

    Returns
    -------
    dict with keys:
        inseriti       - int, number of new tools inserted
        aggiornati     - int, number of existing tools updated
        saltati        - int, number of rows skipped (no usable name/code)
        errori         - list[str], error messages
        dry_run        - bool
        colonne_detect - dict, detected column mapping {raw_header: db_field}
        file_info      - dict, detected encoding/delimiter/format
        totale_righe   - int, total data rows read from the file
        condizioni_inserite - int, cutting conditions inserted
    """
    result = {
        'inseriti': 0,
        'aggiornati': 0,
        'saltati': 0,
        'errori': [],
        'dry_run': dry_run,
        'colonne_detect': {},
        'file_info': {},
        'totale_righe': 0,
        'condizioni_inserite': 0,
    }

    # ── 1. Read the file ──────────────────────────────────────────────────
    if not os.path.isfile(filepath):
        result['errori'].append(f"File non trovato: {filepath}")
        return result

    try:
        rows, file_info = _read_tabular_file(filepath)
    except Exception as e:
        result['errori'].append(f"Errore lettura file: {e}")
        return result

    result['file_info'] = file_info
    result['totale_righe'] = len(rows)

    if not rows:
        result['errori'].append("Nessuna riga di dati trovata nel file.")
        return result

    # ── 2. Detect column mapping ──────────────────────────────────────────
    raw_headers = list(rows[0].keys())
    col_map = _build_column_map(raw_headers)
    result['colonne_detect'] = col_map

    # We need at least a tool name/code column
    if 'codice_interno' not in col_map.values():
        # Try to use the first text column as fallback
        fallback = None
        for raw_h in raw_headers:
            sample_vals = [_to_str(r.get(raw_h)) for r in rows[:5] if _to_str(r.get(raw_h))]
            if sample_vals and all(not _is_purely_numeric(v) for v in sample_vals):
                fallback = raw_h
                break
        if fallback:
            col_map[fallback] = 'codice_interno'
            result['colonne_detect'] = col_map
            log.info("Colonna '%s' usata come codice_interno (fallback)", fallback)
        else:
            result['errori'].append(
                f"Nessuna colonna riconosciuta come nome/codice utensile. "
                f"Colonne trovate: {raw_headers}"
            )
            return result

    # Reverse map: canonical_field -> raw_header
    field_to_raw = {v: k for k, v in col_map.items()}

    # ── 3. Connect to DB ──────────────────────────────────────────────────
    if not os.path.isfile(master_db_path):
        result['errori'].append(f"Database non trovato: {master_db_path}")
        return result

    conn = sqlite3.connect(master_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        _import_rows(rows, field_to_raw, conn, dry_run, result)
        if not dry_run:
            conn.commit()
    except Exception as e:
        result['errori'].insert(0, f"Errore DB: {e}")
        log.exception("Errore durante importazione")
    finally:
        conn.close()

    return result


def _is_purely_numeric(s):
    """Check if a string is purely numeric (int or float)."""
    try:
        float(str(s).replace(',', '.'))
        return True
    except (ValueError, TypeError):
        return False


def _import_rows(rows, field_to_raw, conn, dry_run, result):
    """Process all rows and insert/update into DB."""

    def _get(row, canonical_field, parser=_to_str, default=None):
        raw_header = field_to_raw.get(canonical_field)
        if raw_header is None:
            return default
        return parser(row.get(raw_header), default)

    # Fields that go directly into `utensile` as floats
    _FLOAT_FIELDS = [
        'diametro_mm', 'raggio_punta_mm', 'lunghezza_totale_mm',
        'lunghezza_tagl_mm', 'diam_stelo_mm', 'fuori_pinza_mm',
        'angolo_punta_gradi', 'angolo_elica_gradi',
        'rotazione_default', 'avanzamento_default', 'vc_default',
        'fz_default', 'passo_z_default', 'passo_lat_default',
    ]

    _INT_FIELDS = [
        'num_taglienti',
    ]

    _STR_FIELDS = [
        'nome_pinza', 'descrizione', 'codice_catalogo',
    ]

    # Cutting condition fields (float) that if present, we also write to
    # condizioni_taglio for the default material.
    _CUTTING_FIELDS_MAP = {
        'vc_default':          'vc_m_min',
        'rotazione_default':   'rotazione_rpm',
        'fz_default':          'fz_mm_z',
        'avanzamento_default': 'avanzamento_mm_min',
        'passo_z_default':     'ap_mm',
        'passo_lat_default':   'ae_mm',
    }

    for idx, row in enumerate(rows):
        codice = _get(row, 'codice_interno')
        if not codice:
            result['saltati'] += 1
            continue

        # Sanitize codice: some exports have leading/trailing junk
        codice = re.sub(r'[\x00-\x1f]', '', codice).strip()
        if not codice:
            result['saltati'] += 1
            continue

        try:
            # -- Build params dict --
            params = {}

            # Type detection
            tipo_raw = _get(row, 'tipo_raw')
            tipo_codice = _detect_tool_type(tipo_raw)
            params['id_tipo'] = _get_tipo_id(conn, tipo_codice)

            # Material detection
            mat_raw = _get(row, 'materiale_raw')
            mat_codice = _detect_material(mat_raw)
            params['id_materiale'] = _get_materiale_id(conn, mat_codice)

            # Float fields
            for field in _FLOAT_FIELDS:
                val = _get(row, field, parser=_to_float)
                if val is not None:
                    params[field] = val

            # Int fields
            for field in _INT_FIELDS:
                val = _get(row, field, parser=_to_int)
                if val is not None:
                    params[field] = val

            # String fields
            for field in _STR_FIELDS:
                val = _get(row, field)
                if val is not None:
                    params[field] = val

            # Source tracking
            params['cam_sorgente'] = 'CSV_IMPORT'

            # -- Insert or Update --
            existing = conn.execute(
                "SELECT id FROM utensile WHERE codice_interno = ?", (codice,)
            ).fetchone()

            if not dry_run:
                if existing:
                    tool_id = existing['id']
                    sets = ', '.join(f"{k} = :{k}" for k in params)
                    conn.execute(
                        f"UPDATE utensile SET {sets} WHERE codice_interno = :_codice",
                        {**params, '_codice': codice}
                    )
                    result['aggiornati'] += 1
                else:
                    cols = 'codice_interno, ' + ', '.join(params.keys())
                    placeholders = ':_codice, ' + ', '.join(f':{k}' for k in params)
                    conn.execute(
                        f"INSERT INTO utensile ({cols}) VALUES ({placeholders})",
                        {'_codice': codice, **params}
                    )
                    tool_id = conn.execute(
                        "SELECT id FROM utensile WHERE codice_interno = ?", (codice,)
                    ).fetchone()['id']
                    result['inseriti'] += 1

                # -- Write cutting conditions if available --
                cutting_params = {}
                for src_field, dst_field in _CUTTING_FIELDS_MAP.items():
                    val = params.get(src_field)
                    if val is not None and val > 0:
                        cutting_params[dst_field] = val

                if cutting_params:
                    cutting_params['id_utensile'] = tool_id
                    cutting_params['materiale_pezzo'] = 'Generico'
                    cutting_params['cam_sorgente'] = 'CSV_IMPORT'

                    existing_cond = conn.execute(
                        "SELECT id FROM condizioni_taglio "
                        "WHERE id_utensile = ? AND materiale_pezzo = ? AND applicazione IS NULL",
                        (tool_id, 'Generico')
                    ).fetchone()

                    if existing_cond:
                        sets = ', '.join(f"{k} = :{k}" for k in cutting_params
                                         if k not in ('id_utensile', 'materiale_pezzo'))
                        conn.execute(
                            f"UPDATE condizioni_taglio SET {sets} "
                            f"WHERE id_utensile = :id_utensile "
                            f"AND materiale_pezzo = :materiale_pezzo "
                            f"AND applicazione IS NULL",
                            cutting_params
                        )
                    else:
                        cols = ', '.join(cutting_params.keys())
                        placeholders = ', '.join(f':{k}' for k in cutting_params)
                        conn.execute(
                            f"INSERT INTO condizioni_taglio ({cols}) VALUES ({placeholders})",
                            cutting_params
                        )
                    result['condizioni_inserite'] += 1
            else:
                # dry_run
                if existing:
                    result['aggiornati'] += 1
                else:
                    result['inseriti'] += 1

        except Exception as e:
            result['errori'].append(f"Riga {idx + 2} ({codice}): {e}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(
        description='Importatore CSV/TSV/Excel generico -> Tool DB Manager'
    )
    parser.add_argument('filepath', help='File da importare (.csv/.tsv/.txt/.xls/.xlsx)')
    parser.add_argument('--db', default=None,
                        help='Path al database master (default: database/tool_master.db)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simula importazione senza scrivere nel DB')
    args = parser.parse_args()

    db_path = args.db
    if db_path is None:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        db_path = os.path.join(base, 'database', 'tool_master.db')

    res = importa_csv_generico(args.filepath, db_path, dry_run=args.dry_run)

    print("\n=== Risultato Importazione ===")
    print(f"  File:        {args.filepath}")
    print(f"  Dry-run:     {res['dry_run']}")
    print(f"  Righe lette: {res['totale_righe']}")
    print(f"  Inseriti:    {res['inseriti']}")
    print(f"  Aggiornati:  {res['aggiornati']}")
    print(f"  Saltati:     {res['saltati']}")
    print(f"  Condizioni:  {res['condizioni_inserite']}")
    if res['errori']:
        print(f"  Errori ({len(res['errori'])}):")
        for e in res['errori'][:20]:
            print(f"    - {e}")
    print(f"\n  Colonne rilevate: {json.dumps(res['colonne_detect'], indent=4)}")
    print(f"  Info file:        {json.dumps(res['file_info'], indent=4)}")
