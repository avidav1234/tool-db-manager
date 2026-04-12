"""
hypermill_db_importer.py
Importa utensili da database Hypermill (.db) nel DB master Tool DB Manager.
Formato: SQLite proprietario Open Mind / Hypermill
"""
import sqlite3, os, sys

# Mappatura tool_type_id tipo master
TIPO_MAP = {
    1:  'BALL',
    2:  'FLAT',
    3:  'BULL',
    4:  'DRILL',
    5:  'BALL',
    6:  'FORM',
    9:  'TAP',
    15: 'THREAD',
    16: 'REAM',
}

def _is_hypermill_db(db_path):
    """Verifica se il file e' un DB Hypermill."""
    try:
        con = sqlite3.connect(db_path)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        con.close()
        required = {'NCTools', 'Tools', 'Technologies', 'Holders'}
        return required.issubset(tables)
    except Exception:
        return False

def _estrai_geometria(row, tool_type_id):
    """Estrae parametri geometrici dai dbl_param in base al tipo."""
    def p(i):
        try: return row[f'dbl_param{i}'] or 0.0
        except: return 0.0
    def ip(i):
        try: return row[f'int_param{i}'] or 0
        except: return 0

    geo = {
        'lunghezza_totale_mm': row['total_length'],
        'num_taglienti': ip(1) or None,
    }

    if tool_type_id in (1, 5):
        geo['diametro_mm'] = p(4)
        geo['raggio_punta_mm'] = round(p(4) / 2.0, 4) if p(4) else None
        geo['lunghezza_tagl_mm'] = p(3) or None
    elif tool_type_id == 2:
        geo['diametro_mm'] = p(4)
        geo['raggio_punta_mm'] = 0.0
    elif tool_type_id == 3:
        geo['diametro_mm'] = p(4)
        geo['raggio_punta_mm'] = p(10) if p(10) else 0.0
        geo['lunghezza_tagl_mm'] = p(5) or None
    elif tool_type_id == 4:
        geo['diametro_mm'] = p(4)
        geo['lunghezza_tagl_mm'] = p(1) or None
        geo['angolo_punta_gradi'] = p(7) or None
    elif tool_type_id == 16:
        geo['diametro_mm'] = p(4)
        geo['lunghezza_tagl_mm'] = p(1) or None
    else:
        geo['diametro_mm'] = p(4) or p(1) or None

    return {k: v for k, v in geo.items() if v is not None and v != 0.0}


def importa_hypermill_db(hm_db_path, master_db_path, dry_run=False):
    """
    Importa utensili da DB Hypermill nel DB master.
    Ritorna: {'importati': N, 'errori': N, 'utensili': [...]}
    """
    if not _is_hypermill_db(hm_db_path):
        return {'errore': 'File non riconosciuto come database Hypermill'}

    hm = sqlite3.connect(hm_db_path)
    hm.row_factory = sqlite3.Row

    rows = hm.execute("""
        SELECT
            n.id as nc_id, n.nc_name, n.nc_number_str, n.nc_number_val,
            n.gage_length, n.tool_length, n.comment as nc_comment,
            t.id as tool_id, t.name as tool_name, t.comment as tool_comment,
            t.tool_type_id, t.total_length, t.ordering_code,
            t.dbl_param1, t.dbl_param2, t.dbl_param3, t.dbl_param4,
            t.dbl_param5, t.dbl_param6, t.dbl_param7, t.dbl_param8,
            t.dbl_param9, t.dbl_param10, t.dbl_param11, t.dbl_param12,
            t.dbl_param13, t.dbl_param14, t.dbl_param15, t.dbl_param16, t.dbl_param17,
            t.int_param1, t.int_param2, t.int_param3, t.int_param4, t.int_param5, t.int_param6,
            h.name as holder_name,
            m.name as manufacturer_name
        FROM NCTools n
        JOIN Tools t ON n.tool_id = t.id
        LEFT JOIN Holders h ON n.holder_id = h.id
        LEFT JOIN Manufacturers m ON t.manufacturer_id = m.manufacturer_id
        ORDER BY n.nc_number_val
    """).fetchall()

    techs_raw = hm.execute("""
        SELECT tt.tool_id, t.feedrate, t.dbl_param2 as fz, t.dbl_param3 as rpm,
               t.dbl_param5 as vc, t.dbl_param6 as ap, tp.purpose
        FROM ToolTechnologies tt
        JOIN Technologies t ON tt.technology_id = t.technology_id
        LEFT JOIN TechnologyPurposes tp ON t.purpose_id = tp.id
        WHERE t.feedrate > 0
        ORDER BY tt.tool_id, t.purpose_id
    """).fetchall()

    techs = {}
    for tech in techs_raw:
        tid = tech['tool_id']
        if tid not in techs or 'Prefinitura Normale' in (tech['purpose'] or ''):
            techs[tid] = tech

    utensili = []
    for row in rows:
        geo = _estrai_geometria(row, row['tool_type_id'])
        tech = techs.get(row['tool_id'])

        utensile = {
            'codice_interno':   row['nc_name'] or row['tool_name'] or '',
            'alias':            row['nc_number_str'] or '',
            'descrizione':      row['tool_name'] or '',
            'codice_catalogo':  row['ordering_code'] or '',
            'tipo':             TIPO_MAP.get(row['tool_type_id'], 'FLAT'),
            'cam_sorgente':     'Hypermill',
            'id_originale_cam': str(row['nc_id']),
            'nome_pinza':       row['holder_name'] or '',
            'fuori_pinza_mm':   row['gage_length'] or None,
            **geo,
        }
        if tech:
            if tech['feedrate']: utensile['avanzamento_default'] = tech['feedrate']
            if tech['fz']:       utensile['fz_default'] = tech['fz']
            if tech['rpm']:      utensile['rotazione_default'] = tech['rpm']
            if tech['vc']:       utensile['vc_default'] = tech['vc']
            if tech['ap']:       utensile['passo_z_default'] = tech['ap']

        utensile = {k: v for k, v in utensile.items() if v is not None and v != ''}
        utensili.append(utensile)

    hm.close()

    if dry_run:
        return {'importati': 0, 'errori': 0, 'totale': len(utensili),
                'utensili': utensili, 'dry_run': True}

    master = sqlite3.connect(master_db_path)
    # PRAGMA senza row_factory per usare indici numerici
    master_cols = {r[1] for r in master.execute("PRAGMA table_info('utensile')").fetchall()}
    id_tipo_default = master.execute("SELECT id FROM tipo_utensile LIMIT 1").fetchone()[0]
    id_mat_default = master.execute("SELECT id FROM materiale_utensile LIMIT 1").fetchone()[0]
    master.row_factory = sqlite3.Row

    CAMPO_MAP = {
        'codice_interno', 'alias', 'descrizione', 'codice_catalogo',
        'cam_sorgente', 'id_originale_cam', 'diametro_mm', 'raggio_punta_mm',
        'lunghezza_totale_mm', 'lunghezza_tagl_mm', 'angolo_punta_gradi',
        'num_taglienti', 'nome_pinza', 'fuori_pinza_mm',
        'avanzamento_default', 'rotazione_default', 'vc_default',
        'fz_default', 'passo_z_default',
    }

    importati = errori = 0
    for u in utensili:
        try:
            tipo_str = u.get('tipo', 'FLAT')
            id_tipo_row = master.execute(
                "SELECT id FROM tipo_utensile WHERE codice=? LIMIT 1", (tipo_str,)
            ).fetchone()
            id_tipo = id_tipo_row['id'] if id_tipo_row else id_tipo_default

            insert_data = {'id_tipo': id_tipo, 'id_materiale': id_mat_default}
            for campo in CAMPO_MAP:
                if campo in u and campo in master_cols:
                    insert_data[campo] = u[campo]

            cols = ', '.join(insert_data.keys())
            ph = ', '.join(['?'] * len(insert_data))
            master.execute(f"INSERT INTO utensile ({cols}) VALUES ({ph})",
                           list(insert_data.values()))
            importati += 1
        except Exception as e:
            errori += 1
            if errori == 1:
                import sys as _sys
                print(f'Primo errore: {e} | utensile: {u.get("codice_interno","?")} | dati: {list(insert_data.items())[:5]}', file=_sys.stderr)

    master.commit()
    master.close()

    return {'importati': importati, 'errori': errori,
            'totale': len(utensili), 'utensili': utensili}
