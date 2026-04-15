#!/usr/bin/env python3
"""
export_worknc.py — Export CSV semicolonato WorkNC.

Sorgente: tabelle master utensile + condizioni_taglio (cam_sorgente='WorkNC').
Applica i fattori di correzione S/F/ae/ap dell'utensile ai valori di
condizioni_taglio: S_eff = S * fattore_s, F_eff = F * fattore_f, ecc.

Output: exports/export_worknc_YYYYMMDD.csv (UTF-8 BOM)
"""
import os
import sys
import sqlite3
import csv
from datetime import datetime

_BASE = os.path.join(os.path.dirname(__file__), '..')
DB_PATH = os.path.join(_BASE, 'database', 'tool_master.db')
OUTPUT_DIR = os.path.join(_BASE, 'exports')

HEADER = [
    'Numero', 'AliasUtensile', 'NomeUtensile', 'Tipo', 'Diametro', 'Raggio',
    'NumDenti', 'Materiale', 'Scopo', 'Vc', 'fz', 'f', 'S', 'F', 'FRidotta',
    'ae', 'ap', 'HolderRef', 'Gauge', 'Componenti',
]

# Inverso di TIPO_MAP dell'importer (codice EN → nome italiano WorkNC)
TIPO_INV = {
    'BULL':     'Torico',
    'BALL':     'Sferica',
    'FLAT':     'Piatta',
    'LOLLIPOP': 'Lollipop',
    'FORM':     'Disco',
    'SPOT':     'Smussatore',
    'DRILL':    'Foratura',
    'TAP':      'Maschio',
    'REAM':     'Alesatore',
}

QUERY = """
SELECT
    u.codice_interno                                         AS numero,
    u.alias                                                  AS alias,
    u.descrizione                                            AS nome,
    tu.codice                                                AS tipo_codice,
    u.diametro_mm                                            AS diametro,
    u.raggio_punta_mm                                        AS raggio,
    u.num_taglienti                                          AS denti,
    ct.materiale_pezzo                                       AS materiale,
    ct.applicazione                                          AS scopo,
    ct.vc_m_min                                              AS vc,
    ct.fz_mm_z                                               AS fz,
    ct.f_foratura_mm_giro                                    AS f_foratura,
    ROUND(ct.rotazione_rpm      * COALESCE(u.fattore_s, 1.0))       AS s_eff,
    ROUND(ct.avanzamento_mm_min * COALESCE(u.fattore_f, 1.0))       AS f_eff,
    ROUND(ct.f_ridotta_mm_min   * COALESCE(u.fattore_f, 1.0))       AS f_rid_eff,
    ROUND(ct.ae_mm              * COALESCE(u.fattore_ae, 1.0), 3)   AS ae_eff,
    ROUND(ct.ap_mm              * COALESCE(u.fattore_ap, 1.0), 3)   AS ap_eff,
    u.nome_pinza                                             AS holder_ref,
    u.fuori_pinza_mm                                         AS gauge,
    u.note                                                   AS componenti
FROM condizioni_taglio ct
JOIN utensile u       ON ct.id_utensile = u.id
JOIN tipo_utensile tu ON u.id_tipo = tu.id
WHERE u.attivo = 1
  AND ct.cam_sorgente = 'WorkNC'
ORDER BY u.codice_interno, ct.materiale_pezzo, ct.applicazione
"""


def _fmt(v):
    if v is None or v == '':
        return ''
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f'{v:g}'
    return str(v)


def export_worknc(output_path=None, db_path=None):
    """Genera il CSV WorkNC. Ritorna (path, num_righe)."""
    if db_path is None:
        db_path = DB_PATH
    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d')
        output_path = os.path.join(OUTPUT_DIR, f'export_worknc_{stamp}.csv')

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    tbls = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if 'utensile' not in tbls or 'condizioni_taglio' not in tbls:
        conn.close()
        print("Tabelle utensile/condizioni_taglio mancanti.", file=sys.stderr)
        return output_path, 0

    try:
        rows = conn.execute(QUERY).fetchall()
    except sqlite3.OperationalError as e:
        conn.close()
        print(f"Query export WorkNC fallita: {e}", file=sys.stderr)
        return output_path, 0
    conn.close()

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        w.writerow(HEADER)
        for r in rows:
            tipo_it = TIPO_INV.get(r['tipo_codice'], r['tipo_codice'] or '')
            w.writerow([
                _fmt(r['numero']), _fmt(r['alias']), _fmt(r['nome']),
                _fmt(tipo_it), _fmt(r['diametro']), _fmt(r['raggio']),
                _fmt(r['denti']), _fmt(r['materiale']), _fmt(r['scopo']),
                _fmt(r['vc']), _fmt(r['fz']), _fmt(r['f_foratura']),
                _fmt(r['s_eff']), _fmt(r['f_eff']), _fmt(r['f_rid_eff']),
                _fmt(r['ae_eff']), _fmt(r['ap_eff']),
                r['holder_ref'] or '',   # HolderRef → nome_pinza
                _fmt(r['gauge']),         # Gauge     → fuori_pinza_mm
                _fmt(r['componenti']),
            ])

    print(f"Export WorkNC: {len(rows)} righe → {output_path}")
    return output_path, len(rows)


if __name__ == '__main__':
    export_worknc()
