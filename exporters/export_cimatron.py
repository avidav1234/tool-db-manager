"""
export_cimatron.py  –  v3.0
Genera i 3 file CSV pipe-separati per import completo in Cimatron NC.

File generati:
  Cutters.csv  — geometria utensile, stelo, pinza, parametri taglio default
  Holders.csv  — portautensili con geometria multi-segmento (max 20 sezioni)
  Material.csv — condizioni taglio Vc/Fz specifiche per materiale pezzo

Formato: CimatronE 26.00, separatore "|", colonne identificate da ID numerico.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output', 'cimatron')

# Tipo utensile master → Cimatron type ID (campo 2102)
TIPO_MAP = {
    'FLAT': 210201, 'BALL': 210202, 'BULL': 210203,
    'DRILL': 210204, 'REAM': 210205, 'TAP': 210206,
    'SPOT': 210207, 'TAPER': 210210, 'THREAD': 210201,
    'FORM': 210201, 'LOLLIPOP': 210201,
}

TECNOLOGIA_MAP = {
    'Fresatura': 210101, 'Foratura': 210102, 'Filettatura': 210101,
    'Alesatura': 210102, 'Tornitura': 210101,
}

DIR_ROT_MAP = {'CW': 420301, 'CCW': 420302, 'OFF': 420303}

REFRIG_MAP = {
    'OFF': 420401, 'Flood': 420402, 'FLOOD': 420402,
    'Mist': 420403, 'MIST': 420403, 'Air': 420404,
    'AIR': 420404, 'Through': 420405, 'THROUGH': 420405,
}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt(val, decimals=4):
    if val is None or val == 0:
        return ''
    if isinstance(val, float):
        return f'{val:.{decimals}f}'.rstrip('0').rstrip('.')
    return str(val)


def export_cutters(output_path=None):
    """Genera Cutters.csv: geometria + stelo + pinza + parametri taglio default."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT u.*, t.codice AS tipo_cod, m.codice AS mat_cod
        FROM utensile u
        JOIN tipo_utensile t      ON u.id_tipo = t.id
        JOIN materiale_utensile m ON u.id_materiale = m.id
        WHERE u.attivo = 1
        ORDER BY u.codice_interno
    """).fetchall()
    conn.close()

    col_ids = [
        '1101', '1102', '2101', '2102', '2103',
        '2105', '2106', '2108', '2109', '2110',
        '2111', '2112', '2113',
        '2202', '2203', '2206', '2207',
        '3101', '3102', '3103',
        '4101', '4102', '4103', '4104', '4106',
        '4202', '4203', '4204',
        '5101', '5102',
    ]
    col_names = [
        'Name', 'Comment', 'Technology', 'Type', 'CatalogName',
        'Diameter', 'CornerRadius', 'OverallLength', 'FluteLength', 'CutLength2',
        'Taper', 'TaperAngle', 'PointAngle',
        'ShankDiamTop', 'ShankDiamBot', 'ShankConeLength', 'ShankFreeLength',
        'HolderName', 'GripLength', 'StickOut',
        'Feedrate', 'RPM', 'Vc', 'Fz', 'NumFlutes',
        'ToolLife', 'SpindleDir', 'Coolant',
        'StepDown', 'StepOver',
    ]

    lines = []
    lines.append('//CimatronE26.00')
    lines.append(f'//Cutters count={len(rows)}')
    lines.append('//' + '|'.join(col_names))
    lines.append('|'.join(col_ids))
    lines.append('//Units=101')

    for r in rows:
        tipo_cod = r['tipo_cod'] or 'FLAT'
        tecnologia = r['tecnologia'] or ('Foratura' if tipo_cod in ('DRILL','REAM','TAP','SPOT') else 'Fresatura')

        vals = [
            r['codice_interno'] or '',
            r['alias'] or r['descrizione'] or '',
            str(TECNOLOGIA_MAP.get(tecnologia, 210101)),
            str(TIPO_MAP.get(tipo_cod, 210201)),
            r['codice_catalogo'] or '',
            _fmt(r['diametro_mm']),
            _fmt(r['raggio_punta_mm']),
            _fmt(r['lunghezza_totale_mm']),
            _fmt(r['lunghezza_tagl_mm']),
            _fmt(r['lunghezza_tagl2_mm']),
            str(r['conico'] or 0),
            _fmt(r['angolo_conico_gradi']),
            _fmt(r['angolo_punta_gradi']),
            _fmt(r['diam_stelo_mm'] or r['diam_stelo_sup_mm']),
            _fmt(r['diam_stelo_inf_mm']),
            _fmt(r['lungh_cono_stelo_mm']),
            _fmt(r['lungh_libera_stelo_mm']),
            r['nome_pinza'] or '',
            _fmt(r['lungh_presa_mm']),
            _fmt(r['fuori_pinza_mm']),
            _fmt(r['avanzamento_default'], 2),
            _fmt(r['rotazione_default'], 1),
            _fmt(r['vc_default'], 2),
            _fmt(r['fz_default']),
            str(r['num_taglienti'] or 2),
            str(r['vita_utensile'] or ''),
            str(DIR_ROT_MAP.get(r['dir_rotazione'] or 'CW', 420301)),
            str(REFRIG_MAP.get(r['refrigerante'] or '', '')),
            _fmt(r['passo_z_default']),
            _fmt(r['passo_lat_default']),
        ]
        lines.append('|'.join(vals))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(OUTPUT_DIR, f'Cutters_{ts}.csv')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return output_path, len(rows)


def export_holders(output_path=None):
    """Genera Holders.csv con geometria multi-segmento (max 20 sezioni)."""
    conn = get_connection()
    holders = conn.execute("""
        SELECT p.id, p.codice_interno, p.descrizione, p.tipo_attacco, p.num_segmenti
        FROM portautensile p WHERE p.attivo = 1
        ORDER BY p.codice_interno
    """).fetchall()

    segments = {}
    for seg in conn.execute("""
        SELECT id_portautensile, numero_segmento,
               diametro_inf_mm, diametro_sup_mm, lunghezza_mm
        FROM portautensile_segmento ORDER BY id_portautensile, numero_segmento
    """).fetchall():
        pid = seg['id_portautensile']
        if pid not in segments:
            segments[pid] = []
        segments[pid].append(seg)
    conn.close()

    col_ids = ['7001', '7002', '7003', '7004', '7010']
    col_names = ['Name', 'Description', 'NumSegments', 'NumMandrelSeg', 'AdapterType']
    for sn in range(1, 21):
        base = 7000 + sn * 10
        col_ids.extend([str(base + 1), str(base + 2), str(base + 3), str(base + 4)])
        col_names.extend([f'S{sn}_DInf', f'S{sn}_DSup', f'S{sn}_ConeH', f'S{sn}_TotH'])

    lines = []
    lines.append('//CimatronE26.00')
    lines.append(f'//Holders count={len(holders)}')
    lines.append('//' + '|'.join(col_names))
    lines.append('|'.join(col_ids))
    lines.append('//Units=101')

    for h in holders:
        segs = segments.get(h['id'], [])
        num_seg = len(segs) or h['num_segmenti'] or 0
        vals = [h['codice_interno'], h['descrizione'] or '', str(num_seg), '0', h['tipo_attacco'] or '']
        for i in range(1, 21):
            if i <= len(segs):
                s = segs[i - 1]
                d_inf = s['diametro_inf_mm'] or 0
                d_sup = s['diametro_sup_mm'] or 0
                h_tot = s['lunghezza_mm'] or 0
                h_cono = h_tot if abs(d_inf - d_sup) > 0.01 else 0
                vals.extend([_fmt(d_inf), _fmt(d_sup), _fmt(h_cono), _fmt(h_tot)])
            else:
                vals.extend(['', '', '', ''])
        lines.append('|'.join(vals))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(OUTPUT_DIR, f'Holders_{ts}.csv')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return output_path, len(holders)


def export_material(output_path=None):
    """Genera Material.csv: condizioni taglio Vc/Fz per materiale pezzo."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT u.codice_interno, ct.materiale_pezzo,
               ct.avanzamento_mm_min, ct.rotazione_rpm,
               ct.vc_m_min, ct.fz_mm_z,
               ct.ap_mm, ct.ae_mm,
               ct.rompitruciolo, ct.decrementa, ct.refrigerante
        FROM condizioni_taglio ct
        JOIN utensile u ON ct.id_utensile = u.id
        WHERE u.attivo = 1
        ORDER BY u.codice_interno, ct.materiale_pezzo
    """).fetchall()
    conn.close()

    col_ids = ['8001', '8002', '8101', '8102', '8103', '8104', '8201', '8202', '8301', '8302', '8401']
    col_names = ['ToolName', 'Material', 'Feedrate', 'RPM', 'Vc', 'Fz', 'Ap', 'Ae', 'ChipBreaker', 'Decrement', 'Coolant']

    lines = []
    lines.append('//CimatronE26.00')
    lines.append(f'//Material count={len(rows)}')
    lines.append('//' + '|'.join(col_names))
    lines.append('|'.join(col_ids))
    lines.append('//Units=101')

    for r in rows:
        refrig = REFRIG_MAP.get(r['refrigerante'] or '', '')
        vals = [
            r['codice_interno'],
            r['materiale_pezzo'] or '',
            _fmt(r['avanzamento_mm_min'], 2),
            _fmt(r['rotazione_rpm'], 1),
            _fmt(r['vc_m_min'], 2),
            _fmt(r['fz_mm_z']),
            _fmt(r['ap_mm']),
            _fmt(r['ae_mm']),
            _fmt(r['rompitruciolo']),
            _fmt(r['decrementa']),
            str(refrig) if refrig else '',
        ]
        lines.append('|'.join(vals))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(OUTPUT_DIR, f'Material_{ts}.csv')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return output_path, len(rows)


def export_all(output_dir=None):
    """Genera tutti i file per import completo in Cimatron."""
    if output_dir is None:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = os.path.join(OUTPUT_DIR, f'export_{ts}')
    os.makedirs(output_dir, exist_ok=True)

    cutters_path, n_cutters = export_cutters(os.path.join(output_dir, 'Cutters.csv'))
    holders_path, n_holders = export_holders(os.path.join(output_dir, 'Holders.csv'))
    material_path, n_material = export_material(os.path.join(output_dir, 'Material.csv'))

    result = {
        'output_dir': output_dir,
        'cutters': {'path': cutters_path, 'count': n_cutters},
        'holders': {'path': holders_path, 'count': n_holders},
        'material': {'path': material_path, 'count': n_material},
    }

    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO log_export (cam_destinazione, formato, num_utensili, filepath, note)
            VALUES ('Cimatron', 'CSV pipe-separated', ?, ?, ?)
        """, (n_cutters, output_dir,
              f'Cutters:{n_cutters}, Holders:{n_holders}, Material:{n_material}'))
        conn.commit()
        conn.close()
    except Exception:
        pass

    return result


if __name__ == '__main__':
    result = export_all()
    print(f"Export Cimatron completato:")
    print(f"  Cartella:  {result['output_dir']}")
    print(f"  Cutters:   {result['cutters']['count']} utensili")
    print(f"  Holders:   {result['holders']['count']} portautensili")
    print(f"  Material:  {result['material']['count']} condizioni taglio")
