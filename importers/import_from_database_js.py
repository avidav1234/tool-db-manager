#!/usr/bin/env python3
"""
import_from_database_js.py — Importa CSV estratto da database.js (WorkNC format)

Il file .js contiene la tabella come stringa tra backticks:
    const DATABASE_CSV = `...contenuto CSV separato da ;...`;

Uso:
    python importers/import_from_database_js.py [path/database.js]

Default path: ./database.js
"""
import sys
import os
import re
import sqlite3
from datetime import datetime

DB_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')

# Colonne attese nell'ordine del CSV
COLS = [
    'numero', 'alias', 'nome', 'tipo', 'diametro', 'raggio', 'denti',
    'materiale', 'scopo', 'vc', 'fz', 'f', 'formula_s', 's', 'formula_f', 'f_val',
    'formula_f_rid', 'f_ridotta', 'ae', 'ap',
    'fattore_s', 'fattore_f', 'fattore_ae', 'fattore_ap',
    'param_validi', 'componenti',
]


def ensure_tables(conn):
    """Crea le tabelle se non esistono (utensile e parametri_taglio)."""
    # utensile_worknc: una riga per utensile (Numero + Alias)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS utensile_worknc (
            numero          TEXT NOT NULL,
            alias           TEXT NOT NULL,
            nome            TEXT,
            tipo            TEXT,
            diametro_mm     REAL,
            raggio_mm       REAL,
            denti           INTEGER,
            componenti      TEXT,
            cam_sorgente    TEXT DEFAULT 'WorkNC',
            data_import     TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (numero, alias)
        )
    """)
    # parametri_taglio: una riga per combinazione utensile × materiale × scopo
    conn.execute("""
        CREATE TABLE IF NOT EXISTS parametri_taglio (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            numero          TEXT NOT NULL,
            alias           TEXT NOT NULL,
            materiale       TEXT NOT NULL,
            scopo           TEXT,
            vc              REAL,
            fz              REAL,
            f_foratura      REAL,
            formula_s       TEXT,
            s               REAL,
            formula_f       TEXT,
            f               REAL,
            formula_f_rid   TEXT,
            f_ridotta       REAL,
            ae              REAL,
            ap              REAL,
            fattore_s       REAL,
            fattore_f       REAL,
            fattore_ae      REAL,
            fattore_ap      REAL,
            param_validi    TEXT,
            cam_sorgente    TEXT DEFAULT 'WorkNC',
            UNIQUE (numero, alias, materiale, scopo)
        )
    """)
    conn.commit()


def extract_csv_from_js(js_content):
    """Estrae la stringa tra backticks dal contenuto .js.

    Usa index/rindex (primo e ultimo backtick) invece di regex:
    evita problemi con caratteri speciali nelle righe CSV.
    """
    try:
        start = js_content.index('`') + 1
        end = js_content.rindex('`')
    except ValueError:
        raise ValueError("Nessuna stringa tra backticks trovata nel file .js")
    if end <= start:
        raise ValueError("Backtick di chiusura non trovato")
    return js_content[start:end].strip()


def _to_float(v):
    if v is None or str(v).strip() in ('', 'NaN', 'None'):
        return None
    try:
        return round(float(str(v).replace(',', '.')), 6)
    except (ValueError, TypeError):
        return None


def _to_int(v):
    f = _to_float(v)
    return int(f) if f is not None else None


def _to_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def parse_csv(csv_text):
    """Parsa il testo CSV con separatore ; ritorna lista di dict."""
    lines = csv_text.splitlines()
    # Salta header
    data_rows = []
    header_found = False
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(';')
        if not header_found:
            # Assume la prima riga non vuota sia l'header
            header_found = True
            continue
        # Pad se ci sono meno colonne (campo componenti può contenere ;)
        if len(parts) < len(COLS):
            parts = parts + [''] * (len(COLS) - len(parts))
        elif len(parts) > len(COLS):
            # Componenti alla fine: ricombina gli extra
            parts = parts[:len(COLS) - 1] + [';'.join(parts[len(COLS) - 1:])]
        row = dict(zip(COLS, parts))
        data_rows.append(row)
    return data_rows


def import_file(js_path, db_path):
    print(f"Leggo: {js_path}")
    with open(js_path, 'r', encoding='utf-8') as f:
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
    ensure_tables(conn)

    n_utensili = 0
    n_parametri = 0
    utensili_visti = set()

    for row in rows:
        numero = _to_str(row.get('numero'))
        alias = _to_str(row.get('alias'))
        if not numero or not alias:
            continue

        materiale = _to_str(row.get('materiale'))
        key = (numero, alias)

        # UTENSILE: righe senza materiale OR prima occorrenza della combinazione
        if not materiale or key not in utensili_visti:
            conn.execute("""
                INSERT OR REPLACE INTO utensile_worknc
                (numero, alias, nome, tipo, diametro_mm, raggio_mm, denti, componenti)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                numero, alias,
                _to_str(row.get('nome')),
                _to_str(row.get('tipo')),
                _to_float(row.get('diametro')),
                _to_float(row.get('raggio')),
                _to_int(row.get('denti')),
                _to_str(row.get('componenti')),
            ))
            if key not in utensili_visti:
                n_utensili += 1
                utensili_visti.add(key)

        # PARAMETRI_TAGLIO: solo se c'è un materiale
        if materiale:
            conn.execute("""
                INSERT OR REPLACE INTO parametri_taglio
                (numero, alias, materiale, scopo, vc, fz, f_foratura,
                 formula_s, s, formula_f, f, formula_f_rid, f_ridotta,
                 ae, ap, fattore_s, fattore_f, fattore_ae, fattore_ap, param_validi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                numero, alias, materiale,
                _to_str(row.get('scopo')),
                _to_float(row.get('vc')),
                _to_float(row.get('fz')),
                _to_float(row.get('f')),
                _to_str(row.get('formula_s')),
                _to_float(row.get('s')),
                _to_str(row.get('formula_f')),
                _to_float(row.get('f_val')),
                _to_str(row.get('formula_f_rid')),
                _to_float(row.get('f_ridotta')),
                _to_float(row.get('ae')),
                _to_float(row.get('ap')),
                _to_float(row.get('fattore_s')) or 1.0,
                _to_float(row.get('fattore_f')) or 1.0,
                _to_float(row.get('fattore_ae')) or 1.0,
                _to_float(row.get('fattore_ap')) or 1.0,
                _to_str(row.get('param_validi')),
            ))
            n_parametri += 1

    conn.commit()
    conn.close()
    print(f"Importati: {n_utensili} utensili, {n_parametri} set di parametri.")
    return {'utensili': n_utensili, 'parametri': n_parametri}


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), '..', 'database.js'
    )
    if not os.path.exists(path):
        print(f"File non trovato: {path}", file=sys.stderr)
        sys.exit(1)
    import_file(path, DB_PATH_DEFAULT)
