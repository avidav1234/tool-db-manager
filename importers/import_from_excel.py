"""
import_from_excel.py
Importa utensili da un file Excel o CSV esistente nel database master.

Uso:
    python import_from_excel.py --file utensili.xlsx
    python import_from_excel.py --file utensili.csv

Colonne attese nel file (i nomi sono flessibili, usa --mapping per personalizzare):
    codice_interno, descrizione, tipo, diametro_mm, raggio_punta_mm,
    lunghezza_totale_mm, lunghezza_tagl_mm, num_taglienti, materiale, fornitore
"""

import sqlite3
import os
import sys
import argparse
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')

TIPO_ALIAS = {
    'flat': 'FLAT', 'piatta': 'FLAT', 'fresa piatta': 'FLAT',
    'ball': 'BALL', 'sferica': 'BALL', 'fresa sferica': 'BALL',
    'bull': 'BULL', 'torica': 'BULL', 'bull nose': 'BULL',
    'drill': 'DRILL', 'punta': 'DRILL',
    'tap': 'TAP', 'maschio': 'TAP',
    'ream': 'REAM', 'alesatore': 'REAM',
}

MATERIALE_ALIAS = {
    'hm': 'HM', 'carbide': 'HM', 'widia': 'HM', 'metallo duro': 'HM',
    'hss': 'HSS', 'acciaio rapido': 'HSS',
    'hsco': 'HSCo', 'cobalto': 'HSCo',
}


def init_db(conn):
    with open(os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql'), 'r') as f:
        conn.executescript(f.read())


def normalizza_tipo(val: str) -> str:
    return TIPO_ALIAS.get(str(val).strip().lower(), 'FLAT')


def normalizza_materiale(val: str) -> str:
    return MATERIALE_ALIAS.get(str(val).strip().lower(), 'HM')


def importa(filepath: str, dry_run: bool = False) -> dict:
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    inseriti = 0
    aggiornati = 0
    errori = []

    for i, row in df.iterrows():
        try:
            tipo_cod = normalizza_tipo(row.get('tipo', 'FLAT'))
            mat_cod  = normalizza_materiale(row.get('materiale', 'HM'))

            tipo_id = conn.execute(
                "SELECT id FROM tipo_utensile WHERE codice=?", (tipo_cod,)
            ).fetchone()['id']

            mat_id = conn.execute(
                "SELECT id FROM materiale_utensile WHERE codice=?", (mat_cod,)
            ).fetchone()['id']

            codice = str(row['codice_interno']).strip()
            esistente = conn.execute(
                "SELECT id FROM utensile WHERE codice_interno=?", (codice,)
            ).fetchone()

            params = (
                str(row.get('descrizione', '')),
                tipo_id, mat_id,
                float(row.get('diametro_mm', 0)),
                float(row.get('raggio_punta_mm', 0)),
                float(row.get('lunghezza_totale_mm', 0)),
                float(row.get('lunghezza_tagl_mm', 0)),
                int(row.get('num_taglienti', 2)),
                str(row.get('codice_catalogo', '') or ''),
            )

            if not dry_run:
                if esistente:
                    conn.execute("""
                        UPDATE utensile SET
                            descrizione=?, id_tipo=?, id_materiale=?,
                            diametro_mm=?, raggio_punta_mm=?,
                            lunghezza_totale_mm=?, lunghezza_tagl_mm=?,
                            num_taglienti=?, codice_catalogo=?
                        WHERE codice_interno=?
                    """, (*params, codice))
                    aggiornati += 1
                else:
                    conn.execute("""
                        INSERT INTO utensile
                            (codice_interno, descrizione, id_tipo, id_materiale,
                             diametro_mm, raggio_punta_mm, lunghezza_totale_mm,
                             lunghezza_tagl_mm, num_taglienti, codice_catalogo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (codice, *params))
                    inseriti += 1
        except Exception as e:
            errori.append(f'Riga {i+2}: {e}')

    if not dry_run:
        conn.commit()
    conn.close()

    risultato = {'inseriti': inseriti, 'aggiornati': aggiornati, 'errori': errori}
    print(f'Import completato: {inseriti} inseriti, {aggiornati} aggiornati, {len(errori)} errori')
    if errori:
        for e in errori:
            print(f'  ERRORE: {e}')
    return risultato


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Importa utensili da Excel/CSV nel database master')
    parser.add_argument('--file', required=True, help='Percorso del file Excel o CSV')
    parser.add_argument('--dry-run', action='store_true', help='Simula import senza scrivere nel DB')
    args = parser.parse_args()
    importa(args.file, dry_run=args.dry_run)
