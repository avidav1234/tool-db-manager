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


def _decodifica_holder(polyline):
    """
    Decodifica la polyline binaria del portautensile Hypermill.
    Formato: double big-endian, 8 byte per valore.
    pos=136: lunghezza corpo (moltiplicatore 0.954)
    Diametro serraggio: estratto dal nome
    """
    import struct, re
    if not polyline or len(polyline) < 144:
        return {}
    def get_be(pos):
        chunk = polyline[pos:pos+8]
        try: return round(struct.unpack('>d', chunk)[0], 3)
        except: return None
    p136 = get_be(136)
    l_corpo = round(p136 / 0.954, 1) if p136 and 5 < p136 < 400 else None
    # Lunghezza totale: cerca il valore piu grande plausibile in fondo alla polyline
    l_totale = None
    for pos in [552, 544, 536, 560, 528]:
        v = get_be(pos)
        if v and 30 < v < 500:
            l_totale = round(v - 30, 1)
            break
    return {
        'lungh_corpo_mm': l_corpo,
        'lungh_totale_mm': l_totale,
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
    """
    Estrae parametri geometrici dai dbl_param.
    Decodifica verificata su manuali Moldino ETM/ETMLN/ASRM/ABPF:
      dbl_param1  = altezza tagliente (l2)
      dbl_param2  = diametro stelo/attacco
      dbl_param3  = lunghezza smusso
      dbl_param4  = DIAMETRO (D)
      dbl_param5  = lunghezza punta (l1)
      dbl_param7  = angolo cono
      dbl_param8  = raggio corner (CR) per BULL, diam gambo scaricato per BALL
      total_length = lunghezza totale utensile
    """
    def p(i):
        try: return row[f'dbl_param{i}'] or 0.0
        except: return 0.0
    def ip(i):
        try: return row[f'int_param{i}'] or 0
        except: return 0

    geo = {
        'lunghezza_totale_mm':  row['total_length'],
        'num_taglienti':        ip(1) or None,
        'diam_stelo_mm':        p(2) or None,
        'angolo_conico_gradi':  p(7) or None,
    }

    if tool_type_id in (1, 5):
        # Fresa sferica (BALL): D=p4, raggio=D/2, altezza_tagl=p1, lungh_punta=p5
        geo['diametro_mm']       = p(4)
        geo['raggio_punta_mm']   = round(p(4) / 2.0, 4) if p(4) else None
        geo['lunghezza_tagl_mm'] = p(1) or None

    elif tool_type_id == 2:
        # Fresa piatta con inserto: D=p4
        geo['diametro_mm']       = p(4)
        geo['raggio_punta_mm']   = 0.0
        geo['lunghezza_tagl_mm'] = p(1) or None

    elif tool_type_id == 3:
        # Fresa torica/BULL: D=p4, CR=p8, altezza_tagl=p1, lungh_punta=p5
        geo['diametro_mm']       = p(4)
        geo['raggio_punta_mm']   = p(8) if p(8) else 0.0
        geo['lunghezza_tagl_mm'] = p(1) or None

    elif tool_type_id == 4:
        # Punta (DRILL): D=p4, lungh_tagl=p1, angolo_punta=p7
        geo['diametro_mm']       = p(4)
        geo['lunghezza_tagl_mm'] = p(1) or None
        geo['angolo_punta_gradi'] = p(7) or None

    elif tool_type_id in (16,):
        # Alesatore (REAM): D=p4, lungh_tagl=p1
        geo['diametro_mm']       = p(4)
        geo['lunghezza_tagl_mm'] = p(1) or None

    elif tool_type_id == 15:
        # Fresa per filetti (THREAD): D=p4, passo=p9
        geo['diametro_mm']       = p(4)
        geo['passo_mm']          = p(9) or None

    elif tool_type_id == 9:
        # Maschio (TAP): D=p4
        geo['diametro_mm']       = p(4)

    else:
        geo['diametro_mm']       = p(4) or None
        geo['lunghezza_tagl_mm'] = p(1) or None

    # Campi comuni a tutti i tipi
    if p(5): geo['raggio_raccordo_mm'] = p(5)  # lunghezza punta

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
            COALESCE(c.reach, 0) as ext_reach,
            e.name as ext_name,
            t.id as tool_id, t.name as tool_name, t.comment as tool_comment,
            t.tool_type_id, t.total_length, t.ordering_code,
            t.dbl_param1, t.dbl_param2, t.dbl_param3, t.dbl_param4,
            t.dbl_param5, t.dbl_param6, t.dbl_param7, t.dbl_param8,
            t.dbl_param9, t.dbl_param10, t.dbl_param11, t.dbl_param12,
            t.dbl_param13, t.dbl_param14, t.dbl_param15, t.dbl_param16, t.dbl_param17,
            t.int_param1, t.int_param2, t.int_param3, t.int_param4, t.int_param5, t.int_param6,
            h.name as holder_name,
            gh.polyline as holder_polyline,
            m.name as manufacturer_name
        FROM NCTools n
        JOIN Tools t ON n.tool_id = t.id
        LEFT JOIN Holders h ON n.holder_id = h.id
        LEFT JOIN HolderGeometries hg ON hg.holder_id = h.id
        LEFT JOIN Geometries gh ON gh.id = hg.geometry_id
        LEFT JOIN Manufacturers m ON t.manufacturer_id = m.manufacturer_id
        LEFT JOIN Components c ON c.nctool_id = n.id
        LEFT JOIN Extensions e ON c.extension_id = e.extension_id
        ORDER BY n.nc_number_val
    """).fetchall()

    techs_raw = hm.execute("""
        SELECT tt.tool_id, t.feedrate,
               t.dbl_param2 as fz,
               t.dbl_param3 as rpm,
               t.dbl_param5 as ae,
               t.dbl_param6 as ap,
               t.dbl_param10 as vc,
               tp.purpose
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

        # Rendi codice_interno unico aggiungendo il numero NC come suffisso
        nc_code = row['nc_name'] or row['tool_name'] or ''
        # Decodifica geometria portautensile
        holder_geo = _decodifica_holder(row['holder_polyline']) if row['holder_polyline'] else {}
        # Tipo attacco da coupling
        tipo_attacco = None
        holder_name = row['holder_name'] or ''
        if 'HSK' in holder_name: tipo_attacco = 'HSK63'
        elif 'ISO' in holder_name: tipo_attacco = 'ISO50'
        elif 'SK40' in holder_name: tipo_attacco = 'SK40'

        utensile = {
            'codice_interno':        f"{row['nc_number_str'] or row['nc_name'] or ''}_hm_{row['nc_id']}",
            'alias':                 row['nc_name'] or '',
            'descrizione':           row['tool_name'] or '',
            'codice_catalogo':       row['ordering_code'] or '',
            'tipo':                  TIPO_MAP.get(row['tool_type_id'], 'FLAT'),
            'cam_sorgente':          'Hypermill',
            'id_originale_cam':      str(row['nc_id']),
            'nome_pinza':            holder_name or None,
            'lungh_presa_mm':        holder_geo.get('lungh_corpo_mm'),
            'fuori_pinza_mm':        round((row['tool_length'] or 0) + (row['ext_reach'] or 0), 2) or None,
            'lungh_libera_prolunga_mm': row['ext_reach'] or None,
            'tipo_attacco':          tipo_attacco,
            **geo,
        }
        if tech:
            import math as _math
            feed  = tech['feedrate'] or 0
            rpm   = tech['rpm'] or 0
            fz    = tech['fz'] or 0
            ae    = tech['ae'] or 0
            ap    = tech['ap'] or 0
            vc    = tech['vc'] or 0
            diam  = utensile.get('diametro_mm') or 0
            denti = utensile.get('num_taglienti') or 0
            # Fattori correzione NCTool (portautensile lungo riduce parametri)
            try: feed_factor = row['feedrate_factor'] or 1.0
            except: feed_factor = 1.0
            try: spd_factor = row['spindle_speed_factor'] or 1.0
            except: spd_factor = 1.0
            try: ae_factor = row['infeed_width_factor'] or 1.0
            except: ae_factor = 1.0
            try: ap_factor = row['infeed_length_factor'] or 1.0
            except: ap_factor = 1.0
            # Applica fattori
            if feed:  utensile['avanzamento_default'] = round(feed * feed_factor, 2)
            if rpm:   utensile['rotazione_default']   = round(rpm * spd_factor, 1)
            if fz:    utensile['fz_default']           = round(fz, 4)
            if ae:    utensile['passo_lat_default']    = round(ae * ae_factor, 4)
            if ap:    utensile['passo_z_default']      = round(ap * ap_factor, 4)
            if vc:    utensile['vc_default']           = round(vc, 2)
            # Se Fz non disponibile calcolalo: Fz = Feed / (RPM * denti)
            if not fz and feed and rpm and denti:
                utensile['fz_default'] = round((feed * feed_factor) / (rpm * spd_factor * denti), 4)
            # Se Vc non disponibile calcolalo: Vc = RPM * D * pi / 1000
            if not vc and rpm and diam:
                utensile['vc_default'] = round(rpm * spd_factor * diam * _math.pi / 1000, 2)

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
        'cam_sorgente', 'id_originale_cam',
        'diametro_mm', 'raggio_punta_mm', 'raggio_raccordo_mm',
        'lunghezza_totale_mm', 'lunghezza_tagl_mm', 'angolo_punta_gradi',
        'angolo_conico_gradi', 'diam_stelo_mm', 'passo_mm',
        'num_taglienti', 'nome_pinza', 'fuori_pinza_mm', 'nome_prolunga',
        'lungh_presa_mm', 'lungh_libera_prolunga_mm', 'tipo_attacco',
        'avanzamento_default', 'rotazione_default', 'vc_default',
        'fz_default', 'passo_z_default', 'passo_lat_default',
    }

    importati = errori = ignorati = 0
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

    return {'importati': importati, 'errori': errori, 'ignorati': ignorati,
            'totale': len(utensili), 'utensili': utensili}
