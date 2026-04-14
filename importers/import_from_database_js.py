#!/usr/bin/env python3
"""
import_from_database_js.py — Importa CSV estratto da database.js (WorkNC)
nelle tabelle master: utensile + condizioni_taglio.

Struttura CSV:
    - Righe "header" (Materiale vuoto)      → tabella utensile
    - Righe "dati"   (Materiale non vuoto)  → tabella condizioni_taglio
      (fanno riferimento all'utensile con lo stesso Numero)

Uso:
    python importers/import_from_database_js.py [path/database.js]
"""
import sys
import os
import sqlite3

DB_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')

# Ordine colonne nel CSV (26)
COLS = [
    'numero', 'alias', 'nome', 'tipo', 'diametro', 'raggio', 'denti',
    'materiale', 'scopo',
    'vc', 'fz', 'f_foratura',
    'formula_s', 's', 'formula_f', 'f', 'formula_f_rid', 'f_ridotta',
    'ae', 'ap',
    'fattore_s', 'fattore_f', 'fattore_ae', 'fattore_ap',
    'param_validi', 'componenti',
]

# Mappa Tipo italiano → codice tipo_utensile
TIPO_MAP = {
    'Torico':     'BULL',
    'Sferica':    'BALL',
    'Piatta':     'FLAT',
    'Lollipop':   'LOLLIPOP',
    'Disco':      'FORM',
    'Smussatore': 'SPOT',
    'Foratura':   'DRILL',
    'Maschio':    'TAP',
    'Alesatore':  'REAM',
}


# ── Utility parsing ──────────────────────────────────────────────────────

def _to_float(v):
    if v is None: return None
    s = str(v).strip()
    if s in ('', 'NaN', 'None'): return None
    try:
        return round(float(s.replace(',', '.')), 6)
    except (ValueError, TypeError):
        return None


def _to_int(v):
    f = _to_float(v)
    return int(f) if f is not None else None


def _to_str(v):
    if v is None: return None
    s = str(v).strip()
    return s if s else None


def _fat(v, default=1.0):
    """Fattore: float, fallback a default se None/vuoto."""
    f = _to_float(v)
    return f if f is not None else default


# ── Estrazione CSV dal .js ────────────────────────────────────────────────

def extract_csv_from_js(js_content):
    """Estrae la stringa tra primo e ultimo backtick (robusto)."""
    try:
        start = js_content.index('`') + 1
        end = js_content.rindex('`')
    except ValueError:
        raise ValueError("Nessuna stringa tra backticks trovata nel file .js")
    if end <= start:
        raise ValueError("Backtick di chiusura non trovato")
    return js_content[start:end].strip()


def parse_csv(csv_text):
    """Parsa CSV ; separato. Prima riga = header (saltato)."""
    lines = csv_text.splitlines()
    rows = []
    header_found = False
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(';')
        if not header_found:
            header_found = True
            continue
        # Ultima colonna Componenti può contenere ';' → ricombina extra
        if len(parts) < len(COLS):
            parts = parts + [''] * (len(COLS) - len(parts))
        elif len(parts) > len(COLS):
            parts = parts[:len(COLS) - 1] + [';'.join(parts[len(COLS) - 1:])]
        rows.append(dict(zip(COLS, parts)))
    return rows


# ── Schema migration (ALTER ADD COLUMN idempotente) ───────────────────────

def _ensure_columns(conn):
    """Aggiunge le colonne WorkNC se mancanti (try/except per compat SQLite < 3.35)."""
    migrations = [
        ("utensile",          "fattore_s",          "REAL DEFAULT 1.0"),
        ("utensile",          "fattore_f",          "REAL DEFAULT 1.0"),
        ("utensile",          "fattore_ae",         "REAL DEFAULT 1.0"),
        ("utensile",          "fattore_ap",         "REAL DEFAULT 1.0"),
        ("condizioni_taglio", "f_ridotta_mm_min",   "REAL"),
        ("condizioni_taglio", "f_foratura_mm_giro", "REAL"),
    ]
    for tbl, col, decl in migrations:
        try:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            # Colonna già esistente → ignora
            pass
    conn.commit()


def _get_tipo_id(conn, tipo_ita):
    """Lookup id in tipo_utensile dato il nome italiano. Fallback a UNKNOWN."""
    codice = TIPO_MAP.get((tipo_ita or '').strip(), 'UNKNOWN')
    r = conn.execute("SELECT id FROM tipo_utensile WHERE codice = ?", (codice,)).fetchone()
    if r: return r[0]
    # Fallback al primo tipo esistente
    r = conn.execute("SELECT id FROM tipo_utensile ORDER BY id LIMIT 1").fetchone()
    return r[0] if r else 1


def _get_materiale_utensile_default(conn):
    """Ritorna id di materiale_utensile 'UNKNOWN' o primo disponibile."""
    r = conn.execute("SELECT id FROM materiale_utensile WHERE codice='UNKNOWN'").fetchone()
    if r: return r[0]
    r = conn.execute("SELECT id FROM materiale_utensile ORDER BY id LIMIT 1").fetchone()
    return r[0] if r else 1


# ── Insert/Upsert ─────────────────────────────────────────────────────────

def _upsert_utensile(conn, row, id_tipo, id_materiale):
    """Inserisce o aggiorna un utensile. Ritorna id."""
    codice = _to_str(row.get('numero'))
    if not codice:
        return None

    componenti = _to_str(row.get('componenti'))
    param_validi = (row.get('param_validi') or '').strip().lower()
    attivo = 1 if param_validi == 'ok' else 0

    data = {
        'codice_interno':  codice,
        'alias':           _to_str(row.get('alias')),
        'descrizione':     _to_str(row.get('nome')),
        'id_tipo':         id_tipo,
        'id_materiale':    id_materiale,
        'diametro_mm':     _to_float(row.get('diametro')) or 0,
        'raggio_punta_mm': _to_float(row.get('raggio')) or 0,
        'num_taglienti':   _to_int(row.get('denti')),
        'fattore_s':       _fat(row.get('fattore_s')),
        'fattore_f':       _fat(row.get('fattore_f')),
        'fattore_ae':      _fat(row.get('fattore_ae')),
        'fattore_ap':      _fat(row.get('fattore_ap')),
        'attivo':          attivo,
        'note':            componenti,
        'nome_pinza':      componenti,  # per spec: nome_pinza + note
        'cam_sorgente':    'WorkNC',
        'id_originale_cam': codice,
    }

    existing = conn.execute(
        "SELECT id FROM utensile WHERE codice_interno = ?", (codice,)
    ).fetchone()
    if existing:
        uid = existing[0]
        sets = ', '.join(f"{k}=?" for k in data.keys() if k != 'codice_interno')
        vals = [v for k, v in data.items() if k != 'codice_interno']
        conn.execute(f"UPDATE utensile SET {sets} WHERE id=?", (*vals, uid))
        return uid, False  # (id, inserted=False)
    else:
        cols = ', '.join(data.keys())
        placeholders = ', '.join('?' * len(data))
        cur = conn.execute(
            f"INSERT INTO utensile ({cols}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        return cur.lastrowid, True


def _upsert_condizione(conn, id_utensile, row):
    """Inserisce/aggiorna condizioni_taglio (UNIQUE: id_utensile, materiale_pezzo, applicazione)."""
    materiale = _to_str(row.get('materiale'))
    if not materiale:
        return False
    applicazione = _to_str(row.get('scopo')) or ''

    data = {
        'id_utensile':        id_utensile,
        'materiale_pezzo':    materiale,
        'applicazione':       applicazione,
        'cam_sorgente':       'WorkNC',
        'vc_m_min':           _to_float(row.get('vc')),
        'rotazione_rpm':      _to_float(row.get('s')),
        'fz_mm_z':            _to_float(row.get('fz')),
        'avanzamento_mm_min': _to_float(row.get('f')),
        'ap_mm':              _to_float(row.get('ap')),
        'ae_mm':              _to_float(row.get('ae')),
        'f_ridotta_mm_min':   _to_float(row.get('f_ridotta')),
        'f_foratura_mm_giro': _to_float(row.get('f_foratura')),
    }
    cols = ', '.join(data.keys())
    placeholders = ', '.join('?' * len(data))
    # INSERT OR REPLACE sfrutta l'UNIQUE(id_utensile, materiale_pezzo, applicazione)
    conn.execute(
        f"INSERT OR REPLACE INTO condizioni_taglio ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    return True


# ── Entry point ───────────────────────────────────────────────────────────

def import_file(js_path, db_path):
    print(f"Leggo: {js_path}")
    with open(js_path, 'r', encoding='utf-8', errors='replace') as f:
        js_content = f.read()

    csv_text = extract_csv_from_js(js_content)
    lines = csv_text.splitlines()
    print(f"Righe estratte: {len(lines)}")
    if len(lines) >= 1:
        print(f"Prima riga (header): {lines[0][:80]}")
    if len(lines) >= 2:
        print(f"Seconda riga (primo dato): {lines[1][:80]}")

    rows = parse_csv(csv_text)
    print(f"Righe CSV parse: {len(rows)}")

    conn = sqlite3.connect(db_path)
    _ensure_columns(conn)
    id_materiale_default = _get_materiale_utensile_default(conn)

    n_utensili = 0
    n_aggiornati = 0
    n_condizioni = 0
    utensile_id_by_numero = {}  # numero → id utensile (per le righe dati)

    for row in rows:
        numero = _to_str(row.get('numero'))
        if not numero:
            continue
        materiale = _to_str(row.get('materiale'))

        # RIGA HEADER (Materiale vuoto) → upsert utensile
        if not materiale:
            id_tipo = _get_tipo_id(conn, row.get('tipo'))
            uid, inserted = _upsert_utensile(conn, row, id_tipo, id_materiale_default)
            if uid is None:
                continue
            utensile_id_by_numero[numero] = uid
            if inserted: n_utensili += 1
            else:        n_aggiornati += 1
            continue

        # RIGA DATI (Materiale valorizzato) → condizioni_taglio
        uid = utensile_id_by_numero.get(numero)
        if uid is None:
            # Fallback: cerca utensile già in DB
            r = conn.execute("SELECT id FROM utensile WHERE codice_interno=?", (numero,)).fetchone()
            if r:
                uid = r[0]
                utensile_id_by_numero[numero] = uid
            else:
                # Nessun header visto → crea utensile minimale dalla riga
                id_tipo = _get_tipo_id(conn, row.get('tipo'))
                uid, inserted = _upsert_utensile(conn, row, id_tipo, id_materiale_default)
                if uid is None: continue
                utensile_id_by_numero[numero] = uid
                if inserted: n_utensili += 1

        if _upsert_condizione(conn, uid, row):
            n_condizioni += 1

    conn.commit()
    conn.close()
    print(f"Importati: {n_utensili} nuovi utensili, {n_aggiornati} aggiornati, "
          f"{n_condizioni} condizioni_taglio.")
    return {
        'utensili':       n_utensili + n_aggiornati,
        'utensili_nuovi': n_utensili,
        'utensili_upd':   n_aggiornati,
        'parametri':      n_condizioni,
    }


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), '..', 'database.js'
    )
    if not os.path.exists(path):
        print(f"File non trovato: {path}", file=sys.stderr)
        sys.exit(1)
    import_file(path, DB_PATH_DEFAULT)
