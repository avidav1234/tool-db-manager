"""
export_cimatron.py
Genera i file CSV pipe-separati per Cimatron NC
Formato: CimatronE - separatore "|" - ID colonne numerici
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output', 'cimatron')

# Mappatura tipo utensile -> ID Cimatron
# 1=Flat, 2=Ball, 3=Bull, 4=Drill, 5=Tap
TIPO_MAP = {
    'FLAT':  1,
    'BALL':  2,
    'BULL':  3,
    'DRILL': 4,
    'TAP':   5,
    'REAM':  4,
    'SPOT':  4,
    'TAPER': 1,
    'FORM':  1,
}

MATERIALE_MAP = {
    'HM':   1,
    'HSS':  2,
    'HSCo': 2,
    'CBN':  3,
    'PCD':  4,
    'CER':  5,
}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def export_cutters(output_path: str = None) -> str:
    """
    Genera il file CSV utensili per Cimatron.
    Restituisce il path del file generato.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(OUTPUT_DIR, f'cimatron_cutters_{ts}.csv')

    conn = get_connection()
    rows = conn.execute("""
        SELECT u.*, t.codice AS tipo_cod, m.codice AS mat_cod, f.nome AS fornitore_nome
        FROM utensile u
        JOIN tipo_utensile t      ON u.id_tipo     = t.id
        JOIN materiale_utensile m ON u.id_materiale = m.id
        LEFT JOIN fornitore f     ON u.id_fornitore = f.id
        WHERE u.attivo = 1
        ORDER BY u.codice_interno
    """).fetchall()
    conn.close()

    lines = []

    # Riga 1: versione Cimatron
    lines.append('//CimatronE26.00')

    # Riga 2: numero utensili
    lines.append(f'//Cutters count={len(rows)}')

    # Riga 3: nomi colonne (commento ignorato in import)
    lines.append('//Name|Type|Diameter|CornerRadius|PointAngle|FluteLength|OverallLength|NumFlutes|Material|CatalogName|Comment')

    # Riga 4: ID colonne Cimatron
    lines.append('1001|1002|1003|1004|1005|1006|1007|1008|1009|1010|1099')

    # Unita di misura (101 = mm)
    lines.append('//Units=101')

    for r in rows:
        tipo_id  = TIPO_MAP.get(r['tipo_cod'], 1)
        mat_id   = MATERIALE_MAP.get(r['mat_cod'], 1)
        name     = r['codice_interno']
        diam     = r['diametro_mm'] or 0
        corner   = r['raggio_punta_mm'] or 0
        angle    = r['angolo_punta_gradi'] or 0
        flute_l  = r['lunghezza_tagl_mm'] or 0
        total_l  = r['lunghezza_totale_mm'] or 0
        flutes   = r['num_taglienti'] or 2
        catalog  = r['codice_catalogo'] or ''
        comment  = r['descrizione'] or ''

        line = f'{name}|{tipo_id}|{diam}|{corner}|{angle}|{flute_l}|{total_l}|{flutes}|{mat_id}|{catalog}|{comment}'
        lines.append(line)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'[Cimatron] Export completato: {len(rows)} utensili -> {output_path}')

    # Log nel database
    conn = get_connection()
    conn.execute(
        "INSERT INTO log_export (cam, num_utensili, file_output) VALUES (?, ?, ?)",
        ('CIMATRON', len(rows), output_path)
    )
    conn.commit()
    conn.close()

    return output_path


if __name__ == '__main__':
    path = export_cutters()
    print(f'File generato: {path}')
