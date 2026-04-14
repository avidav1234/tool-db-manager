"""
hypermill_db_importer.py  –  v3.0
Importa TUTTO dal database Hypermill (.db) nel DB master Tool DB Manager.

Tabelle importate:
  Materials        → materiale_pezzo
  CuttingMaterials → grado_utensile
  MatTechItems     → catalogo_velocita
  Holders          → portautensile + portautensile_segmento
  Extensions       → prolunga
  NCTools + Tools  → utensile  (con gage_length, fattori correzione, ecc.)
  CuttingProfiles  → condizioni_taglio  (per materiale × applicazione)

Decodifica verificata:
  CuttingProfiles:  feedrate=Vf, dbl_param5=Ae, dbl_param7=Ap, dbl_param13=Fz (p6/p8/p9/p10=fattori)
  Technologies:     feedrate=Vf, dbl_param3=RPM, dbl_param5=Ae, dbl_param6=Fz
  Holder polyline:  104 byte/segmento, double big-endian
"""
import sqlite3, os, sys, struct, re, math


TIPO_MAP = {
    1:  'BALL',
    2:  'FLAT',
    3:  'BULL',
    4:  'DRILL',
    5:  'BALL',
    6:  'FORM',
    9:  'SPOT',      # Chamfer/smusso (non TAP!)
    15: 'THREAD',
    16: 'REAM',
}

COOLANT_MAP = {
    '':  None,
    '1': 'OFF',
    '2': 'Through',
    '3': 'Flood',
}

PURPOSE_MAP = {
    'v Finitura Piani':         'Finitura piani',
    'v Prefinitura Normale':    'Prefinitura',
    'v Finitura':               'Finitura',
    'v Prefinitura Piano':      'Prefinitura piani',
    'v Prefinitura Spazz':      'Prefinitura spazzata',
    'v Ripresa':                'Ripresa',
    'v Incisione':              'Incisione',
    'v Contornitura':           'Contornitura',
    'v Cont. verticale':        'Contornitura verticale',
    'v Coda di rondine Lat':    'Coda di rondine laterale',
    'v Coda di rondine Pieno':  'Coda di rondine pieno',
    'v Finitura plunging':      'Finitura plunging',
    'v Foratura':               'Foratura',
    'v Smussatura a Tuffo':     'Smussatura tuffo',
    'v Smussatura 3D':          'Smussatura 3D',
    'v Filettatura':            'Filettatura',
    'v Filettatura + Foro':     'Filettatura + foro',
    'v Alesatura':              'Alesatura',
    'v Centrino':               'Centratura',
    'v Sgross Troc (HPC)':     'Sgrossatura HPC',
    'v Cont. elicoidale':       'Contornitura elicoidale',
    'v Finitura Spazz':         'Finitura spazzata',
    'v Prefinitura plunging':   'Prefinitura plunging',
    'v Sgross elicoidale':      'Sgrossatura elicoidale',
    'v Prefinitura Ridotta':    'Prefinitura ridotta',
    'FORATURA':                 'Foratura',
    'FINITURA DI CONTORNATURA': 'Finitura contornitura',
    'SEMIFINITURA':             'Semifinitura',
    'FINITURA PIANI':           'Finitura piani',
    'SGROSSATURA HPC':          'Sgrossatura HPC',
    'SGROSSATURA':              'Sgrossatura',
    'SGROSSATURA HSC':          'Sgrossatura HSC',
    'FINITURA HSC':             'Finitura HSC',
}


# Decoder universale (unico per importer + renderer) — nessuna logica type-specific
from polyline_decoder import decode_polyline, decode_with_origin as _leggi_profilo_polyline  # noqa


def _decodifica_holder(polyline, holder_name=''):
    """
    Decodifica universale holder da polyline Hypermill.
    Usa decode_polyline() dal modulo condiviso — zero logica type-specific.

    Ritorna:
      result: dict con campi derivati (d1, d3, d_hsk, nl, z_cono, a_lungh)
              calcolati dal primo/ultimo punto del profilo esterno
      segmenti: lista di segmenti per portautensile_segmento
                (primo segmento = cono dal naso al primo punto, poi punti consecutivi)

    Il naso (r, z=0) non è in polyline: dedotto da D_ut + 4 (convenzione TSF Bilz)
    o proporzionale al primo punto se D_ut non estraibile dal nome.
    """
    if not polyline or not isinstance(polyline, (bytes, bytearray)) or len(polyline) < 144:
        return {}, []

    # Usa il decoder universale (filtro monotonia + estensione z_tot)
    punti = decode_polyline(polyline)
    if not punti:
        return {}, []

    # D_ut dal nome per il naso (non presente nella polyline)
    m_dut = re.search(r'D(\d+(?:\.\d+)?)', holder_name, re.IGNORECASE)
    d_ut = float(m_dut.group(1)) if m_dut else 0

    r_slim, z_slim = punti[0]
    r_flangia, z_flangia = punti[-1]

    # Naso: da D_ut estratto dal nome, oppure proporzionale al primo punto
    if d_ut > 0:
        d_naso = round(d_ut + 4, 2)
    else:
        d_naso = round(r_slim * 2 * 0.4, 2)

    # Costruisci segmenti
    segmenti = []
    # Seg 1: cono dal naso al primo punto (solo se z_slim > 0, es. TSF)
    if z_slim > 0.01:
        segmenti.append({
            'numero_segmento': 1,
            'diametro_inf_mm': d_naso,
            'diametro_sup_mm': round(r_slim * 2, 2),
            'lunghezza_mm': round(z_slim, 2),
        })
    # Segmenti intermedi: tra ogni coppia di punti consecutivi
    for i in range(1, len(punti)):
        r_prev, z_prev = punti[i-1]
        r_curr, z_curr = punti[i]
        l_seg = round(z_curr - z_prev, 2)
        if l_seg <= 0.01:
            continue
        segmenti.append({
            'numero_segmento': len(segmenti) + 1,
            'diametro_inf_mm': round(r_prev * 2, 2),
            'diametro_sup_mm': round(r_curr * 2, 2),
            'lunghezza_mm': l_seg,
        })

    # Campi derivati (primo/ultimo punto del profilo esterno)
    # z_fine_cono = z del penultimo punto (inizio flangia cilindrica finale)
    z_cono = round(punti[-2][1], 2) if len(punti) > 1 else round(z_slim, 2)
    result = {
        'd1_serraggio_mm':    d_ut,
        'd3_corpo_mm':        round(r_slim * 2, 2),
        'd_hsk_mm':           round(r_flangia * 2, 2),
        'nl_serraggio_mm':    round(z_slim, 2),
        'z_fine_cono_mm':     z_cono,
        'a_lungh_holder_mm':  round(z_flangia, 2),
        # Compat con vecchi nomi usati altrove nel codice
        'd3_diam_corpo_mm':     round(r_slim * 2, 2),
        'nl_lungh_serraggio_mm': round(z_slim, 2),
        'a_lungh_totale_mm':    round(z_flangia, 2),
    }
    return result, segmenti


def _leggi_profilo_fresa(tool_row, hm_conn):
    """
    Estrae profili gambo (free_shaft) e punta (free_tip) da Geometries.
    Ritorna dict con shaft_points, tip_points, shaft_length, shaft_raw.
    """
    result = {'shaft_points': [], 'tip_points': [], 'shaft_length': None, 'shaft_raw': None}

    shaft_id = tool_row['free_shaft_geom_id'] if 'free_shaft_geom_id' in tool_row.keys() else None
    tip_id = tool_row['free_tip_geom_id'] if 'free_tip_geom_id' in tool_row.keys() else None

    if shaft_id:
        row = hm_conn.execute("SELECT polyline FROM Geometries WHERE id=?", (shaft_id,)).fetchone()
        if row and row['polyline']:
            result['shaft_raw'] = row['polyline']
            result['shaft_points'] = _leggi_profilo_polyline(row['polyline'])
            try:
                if len(row['polyline']) >= 560:
                    z_tot = struct.unpack('>d', row['polyline'][552:560])[0]
                    if 0 < z_tot < 1000:
                        result['shaft_length'] = round(z_tot, 2)
            except Exception:
                pass

    if tip_id:
        row = hm_conn.execute("SELECT polyline FROM Geometries WHERE id=?", (tip_id,)).fetchone()
        if row and row['polyline']:
            result['tip_points'] = _leggi_profilo_polyline(row['polyline'])

    return result


def _is_hypermill_db(db_path):
    try:
        con = sqlite3.connect(db_path)
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        con.close()
        return {'NCTools', 'Tools', 'Technologies', 'Holders'}.issubset(tables)
    except Exception:
        return False


def _estrai_geometria(row, tool_type_id):
    """
    Estrae parametri geometrici dai dbl_param della tabella Tools.
    Mappatura verificata su cataloghi Moldino ETM/ETMLN/ASRM/ABPF (2026-04-14):

    Comuni a tutti i tipi:
      dbl_param2  = diametro pinza/attacco (non gambo fisico)
      dbl_param3  = diametro nocciolo/scarico (dn)
      dbl_param4  = DIAMETRO nominale (D)

    Per tipo:
      1,5 BALL:  p1=lungh libera (l1, NON tagliente!), p8=diam zona ridotta (neck)
      2   FLAT:  p13=lungh tagliente
      3   BULL:  p1=lungh libera (l1), p5=l1 ridondante, p8=raggio corner (R)
      4   DRILL: p1=lungh tagliente, p7=angolo punta
      6   FORM:  p5=spessore disco, p7=raggio corner disco, p8=diam foro interno
      9   SPOT:  p7=altezza tagliente chamfer, p8=angolo chamfer
      15  THREAD: p9=passo filetto
      16  REAM:  p7=lungh tagliente, p9=diam pilota, p10=angolo entrata
    """
    def p(i):
        try:
            return row[f'dbl_param{i}'] or 0.0
        except (KeyError, IndexError):
            return 0.0
    def ip(i):
        try:
            return row[f'int_param{i}'] or 0
        except (KeyError, IndexError):
            return 0

    geo = {
        'lunghezza_totale_mm':  row['total_length'],
        'num_taglienti':        ip(1) or None,
        'diam_stelo_mm':        p(2) or None,  # diametro pinza/attacco
    }

    if tool_type_id in (1, 5):
        # BALL: D=p4, R=D/2, p1=lungh libera (l1), p8=diam neck
        geo['diametro_mm']       = p(4)
        geo['raggio_punta_mm']   = round(p(4) / 2.0, 4) if p(4) else None
        geo['lunghezza_tagl_mm'] = p(1) or None  # l1 = lungh libera (usata come approssimazione)
        if p(8) and p(8) > 0:
            geo['diam_libero_mm'] = p(8)  # diametro zona ridotta (neck)

    elif tool_type_id == 2:
        # FLAT/Endmill: D=p4, R=0, p13=lungh tagliente
        geo['diametro_mm']       = p(4)
        geo['raggio_punta_mm']   = 0.0
        geo['lunghezza_tagl_mm'] = p(13) or p(1) or None  # p13 prioritario, p1 fallback

    elif tool_type_id == 3:
        # BULL/Radius: D=p4, CR=p8, p1=lungh libera (l1)
        geo['diametro_mm']       = p(4)
        geo['raggio_punta_mm']   = p(8) if p(8) else 0.0
        geo['lunghezza_tagl_mm'] = p(1) or None  # l1 = lungh libera

    elif tool_type_id == 4:
        # DRILL: D=p4, p1=lungh tagliente, p7=angolo punta
        geo['diametro_mm']       = p(4)
        geo['lunghezza_tagl_mm'] = p(1) or None
        geo['angolo_punta_gradi'] = p(7) or None

    elif tool_type_id == 6:
        # FORM/Woodruff: D=p4, p7=raggio corner disco, p5=spessore, p8=diam foro
        geo['diametro_mm']       = p(4)
        geo['raggio_punta_mm']   = p(7) if p(7) else 0.0  # raggio corner disco
        geo['lunghezza_tagl_mm'] = p(5) or None  # spessore disco
        if p(8) and p(8) > 0:
            geo['diam_libero_mm'] = p(8)  # diametro foro/albero interno

    elif tool_type_id == 9:
        # CHAMFER/SPOT: D=p4, p8=angolo chamfer, p7=altezza tagliente
        geo['diametro_mm']       = p(4)
        geo['angolo_punta_gradi'] = p(8) if p(8) else None  # angolo chamfer
        geo['lunghezza_tagl_mm'] = p(7) or None  # altezza tagliente chamfer

    elif tool_type_id == 15:
        # THREAD: D=p4 (diametro nucleo), p9=passo filetto
        geo['diametro_mm']       = p(4)
        geo['passo_mm']          = p(9) or None

    elif tool_type_id == 16:
        # REAMER: D=p4, p7=lungh tagliente, p9=diam pilota, p10=angolo entrata
        geo['diametro_mm']       = p(4)
        geo['lunghezza_tagl_mm'] = p(7) or None
        geo['angolo_punta_gradi'] = p(10) or None  # angolo entrata

    else:
        geo['diametro_mm']       = p(4) or None
        geo['lunghezza_tagl_mm'] = p(1) or None

    return {k: v for k, v in geo.items() if v is not None and v != 0.0}


def _detect_tipo_attacco(holder_name, holder_comment=''):
    s = (holder_name or '') + ' ' + (holder_comment or '')
    if 'HSK' in s: return 'HSK63'
    elif any(x in s for x in ('ISO 50', 'ISO50', 'DIN69871')): return 'ISO50'
    elif any(x in s for x in ('SK40', 'SK 40')): return 'SK40'
    elif 'CAPTO' in s.upper(): return 'Capto'
    return None


def importa_hypermill_db(hm_db_path, master_db_path, dry_run=False):
    if not _is_hypermill_db(hm_db_path):
        return {'errore': 'File non riconosciuto come database Hypermill'}

    hm = sqlite3.connect(hm_db_path)
    hm.row_factory = sqlite3.Row

    stats = {
        'materiali_pezzo': 0, 'gradi_utensile': 0, 'catalogo_velocita': 0,
        'portautensili': 0, 'segmenti_holder': 0, 'prolunghe': 0,
        'utensili': 0, 'condizioni_taglio': 0, 'errori': 0, 'dry_run': dry_run,
    }

    if dry_run:
        stats['materiali_pezzo'] = hm.execute("SELECT COUNT(*) FROM Materials").fetchone()[0]
        stats['gradi_utensile'] = hm.execute("SELECT COUNT(*) FROM CuttingMaterials").fetchone()[0]
        stats['catalogo_velocita'] = hm.execute("SELECT COUNT(*) FROM MatTechItems").fetchone()[0]
        stats['portautensili'] = hm.execute("SELECT COUNT(*) FROM Holders").fetchone()[0]
        stats['prolunghe'] = hm.execute("SELECT COUNT(*) FROM Extensions").fetchone()[0]
        stats['utensili'] = hm.execute("SELECT COUNT(*) FROM NCTools").fetchone()[0]
        stats['condizioni_taglio'] = hm.execute("SELECT COUNT(*) FROM CuttingProfiles WHERE feedrate > 0").fetchone()[0]
        hm.close()
        return stats

    master = sqlite3.connect(master_db_path)
    master.execute("PRAGMA foreign_keys = ON")
    master.execute("PRAGMA journal_mode = WAL")

    try:
        stats['materiali_pezzo'] = _importa_materiali_pezzo(hm, master)
        stats['gradi_utensile'] = _importa_gradi_utensile(hm, master)
        stats['catalogo_velocita'] = _importa_catalogo_velocita(hm, master)
        h_stats = _importa_portautensili(hm, master)
        stats['portautensili'] = h_stats['holders']
        stats['segmenti_holder'] = h_stats['segmenti']
        stats['prolunghe'] = _importa_prolunghe(hm, master)
        stats['utensili'] = _importa_utensili(hm, master)
        stats['condizioni_taglio'] = _importa_condizioni_taglio(hm, master)
        master.commit()
    except Exception as e:
        master.rollback()
        stats['errore'] = str(e)
        import traceback
        traceback.print_exc()
    finally:
        hm.close()
        master.close()

    return stats


def _importa_materiali_pezzo(hm, master):
    rows = hm.execute("SELECT id, name, norm_code, milling_factor_vc, milling_factor_fz, milling_factor_ae, milling_factor_ap, drilling_factor_vc, drilling_factor_fz FROM Materials ORDER BY id").fetchall()
    count = 0
    for r in rows:
        nome = r['name']
        gruppo = _classifica_gruppo_iso(nome)
        durezza_min, durezza_max = _parse_durezza(nome)
        existing = master.execute("SELECT id FROM materiale_pezzo WHERE nome=?", (nome,)).fetchone()
        if existing:
            master.execute("""UPDATE materiale_pezzo SET norm_code=?, gruppo=?, durezza_min=?, durezza_max=?,
                milling_factor_vc=?, milling_factor_fz=?, milling_factor_ae=?, milling_factor_ap=?,
                drilling_factor_vc=?, drilling_factor_fz=?, cam_sorgente='Hypermill', id_originale_cam=?
                WHERE nome=?""",
                (r['norm_code'], gruppo, durezza_min, durezza_max, r['milling_factor_vc'], r['milling_factor_fz'],
                 r['milling_factor_ae'], r['milling_factor_ap'], r['drilling_factor_vc'], r['drilling_factor_fz'],
                 str(r['id']), nome))
        else:
            master.execute("""INSERT INTO materiale_pezzo (nome, norm_code, gruppo, durezza_min, durezza_max,
                milling_factor_vc, milling_factor_fz, milling_factor_ae, milling_factor_ap,
                drilling_factor_vc, drilling_factor_fz, cam_sorgente, id_originale_cam)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'Hypermill',?)""",
                (nome, r['norm_code'], gruppo, durezza_min, durezza_max, r['milling_factor_vc'], r['milling_factor_fz'],
                 r['milling_factor_ae'], r['milling_factor_ap'], r['drilling_factor_vc'], r['drilling_factor_fz'],
                 str(r['id'])))
        count += 1
    return count


def _classifica_gruppo_iso(nome):
    n = nome.upper()
    if 'ALLUMINIO' in n or 'ALUMIN' in n: return 'N'
    elif 'INOX' in n: return 'M'
    elif 'TEMPRATO' in n or 'HRC' in n: return 'H'
    elif 'TITANIO' in n: return 'S'
    elif 'INCONEL' in n: return 'S'
    elif 'GHISA' in n: return 'K'
    elif 'ACCIAIO' in n or 'DIEVAR' in n or 'BOHLER' in n or '1.2' in n: return 'P'
    elif 'OTTONE' in n or 'BRONZO' in n or 'RAME' in n: return 'N'
    elif 'PLASTICA' in n or 'UREOL' in n or 'LEGNO' in n: return 'O'
    elif 'MAGNESIO' in n: return 'N'
    return None


def _parse_durezza(nome):
    m = re.search(r'R[_]?(\d+)-(\d+)', nome)
    if m: return float(m.group(1)), float(m.group(2))
    m = re.search(r'HRC(\d+)', nome, re.IGNORECASE)
    if m: return None, float(m.group(1))
    m = re.search(r'HBS(\d+)', nome, re.IGNORECASE)
    if m: return None, float(m.group(1))
    m = re.search(r'Max(\d+)HB', nome, re.IGNORECASE)
    if m: return None, float(m.group(1))
    return None, None


def _importa_gradi_utensile(hm, master):
    rows = hm.execute("SELECT id, name, comment FROM CuttingMaterials ORDER BY id").fetchall()
    count = 0
    for r in rows:
        nome = r['name']
        comment = r['comment'] or ''
        famiglia = _classifica_famiglia_grado(nome, comment)
        existing = master.execute("SELECT id FROM grado_utensile WHERE nome=?", (nome,)).fetchone()
        if existing:
            master.execute("UPDATE grado_utensile SET descrizione=?, famiglia=?, cam_sorgente='Hypermill', id_originale_cam=? WHERE nome=?",
                (comment, famiglia, str(r['id']), nome))
        else:
            master.execute("INSERT INTO grado_utensile (nome, descrizione, famiglia, cam_sorgente, id_originale_cam) VALUES (?,?,?,'Hypermill',?)",
                (nome, comment, famiglia, str(r['id'])))
        count += 1
    return count


def _classifica_famiglia_grado(nome, commento):
    s = (nome + ' ' + commento).upper()
    if 'HSS' in s: return 'HSS'
    elif any(x in s for x in ('HM', 'MD', 'METALLO DURO', 'CARBIDE', 'SOLID CARBIDE')): return 'HM'
    elif 'CBN' in s: return 'CBN'
    elif 'PCD' in s or 'DIAMANTE' in s: return 'PCD'
    elif 'CERAMICA' in s or 'CERAMIC' in s: return 'CERAMICA'
    elif 'CERMET' in s: return 'CERMET'
    if 'INS' in s or 'INSERTO' in s: return 'HM'
    return 'HM'


def _importa_catalogo_velocita(hm, master):
    mat_map = _build_material_map(hm, master)
    grado_map = _build_grado_map(hm, master)
    rows = hm.execute("""
        SELECT mti.limiting_diameter, mti.cutting_speed, mti.feedrate_per_edge, mti.drilling_feedrate,
               mt.material_id, mt.cutting_material_id
        FROM MatTechItems mti JOIN MatTechs mt ON mti.mat_tech_id = mt.mat_tech_id
        ORDER BY mt.material_id, mt.cutting_material_id, mti.limiting_diameter
    """).fetchall()
    count = 0
    for r in rows:
        id_mat = mat_map.get(r['material_id'])
        id_grado = grado_map.get(r['cutting_material_id'])
        if not id_mat or not id_grado: continue
        master.execute("INSERT OR REPLACE INTO catalogo_velocita (id_materiale_pezzo, id_grado_utensile, limiting_diameter_mm, vc_m_min, fz_mm_z, drilling_feedrate, cam_sorgente) VALUES (?,?,?,?,?,?,'Hypermill')",
            (id_mat, id_grado, r['limiting_diameter'], r['cutting_speed'], r['feedrate_per_edge'], r['drilling_feedrate']))
        count += 1
    return count


def _importa_portautensili(hm, master):
    rows = hm.execute("""
        SELECT h.id, h.name, h.comment, h.ordering_code, h.spindle_speed_factor, h.feedrate_factor,
               h.infeed_width_factor, h.infeed_length_factor, h.max_spindle_speed, h.max_feedrate, h.coolant_through,
               g.polyline
        FROM Holders h LEFT JOIN HolderGeometries hg ON hg.holder_id = h.id
        LEFT JOIN Geometries g ON g.id = hg.geometry_id ORDER BY h.id
    """).fetchall()
    import json as _json
    count_h = count_s = 0
    for r in rows:
        holder_name = r['name']
        tipo_attacco = _detect_tipo_attacco(holder_name, r['comment'])
        holder_geo, segmenti = _decodifica_holder(r['polyline'], holder_name)
        # Salva SOLO i punti reali del profilo esterno (senza origine artificiale)
        # decode_polyline filtra i punti interni HSK via monotonia su r
        punti_raw = decode_polyline(r['polyline']) if r['polyline'] else []
        profilo_json = _json.dumps([[round(p[0], 4), round(p[1], 4)] for p in punti_raw]) if punti_raw else None

        existing_h = master.execute("SELECT id FROM portautensile WHERE codice_interno=?", (holder_name,)).fetchone()
        if existing_h:
            master.execute("""UPDATE portautensile SET descrizione=?, tipo_attacco=?, num_segmenti=?,
                spindle_speed_factor=?, feedrate_factor=?, infeed_width_factor=?, infeed_length_factor=?,
                max_spindle_speed=?, max_feedrate=?, coolant_through=?, cam_sorgente='Hypermill',
                id_originale_cam=?, profilo_punti_json=?, profilo_polyline_raw=?
                WHERE codice_interno=?""",
                (r['comment'] or r['ordering_code'], tipo_attacco, len(segmenti),
                 r['spindle_speed_factor'], r['feedrate_factor'], r['infeed_width_factor'], r['infeed_length_factor'],
             r['max_spindle_speed'] or None, r['max_feedrate'] or None, r['coolant_through'], str(r['id']),
             profilo_json, r['polyline'], holder_name))
        else:
            master.execute("""INSERT INTO portautensile
                (codice_interno, descrizione, tipo_attacco, num_segmenti, spindle_speed_factor, feedrate_factor,
                 infeed_width_factor, infeed_length_factor, max_spindle_speed, max_feedrate, coolant_through,
                 cam_sorgente, id_originale_cam, profilo_punti_json, profilo_polyline_raw)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'Hypermill',?,?,?)""",
                (holder_name, r['comment'] or r['ordering_code'], tipo_attacco, len(segmenti),
                 r['spindle_speed_factor'], r['feedrate_factor'], r['infeed_width_factor'], r['infeed_length_factor'],
                 r['max_spindle_speed'] or None, r['max_feedrate'] or None, r['coolant_through'], str(r['id']),
                 profilo_json, r['polyline']))
        row_id = master.execute("SELECT id FROM portautensile WHERE codice_interno = ?", (holder_name,)).fetchone()
        if row_id:
            porta_id = row_id[0]
            # Cancella tutti i segmenti vecchi prima di inserire i nuovi
            master.execute("DELETE FROM portautensile_segmento WHERE id_portautensile=?", (porta_id,))
            for seg in segmenti:
                master.execute("INSERT INTO portautensile_segmento (id_portautensile, numero_segmento, diametro_inf_mm, diametro_sup_mm, lunghezza_mm) VALUES (?,?,?,?,?)",
                    (porta_id, seg['numero_segmento'], seg['diametro_inf_mm'], seg['diametro_sup_mm'], seg['lunghezza_mm']))
                count_s += 1
        count_h += 1
    return {'holders': count_h, 'segmenti': count_s}


def _importa_prolunghe(hm, master):
    rows = hm.execute("SELECT extension_id, name, comment, ordering_code, spindle_speed_factor, feedrate_factor, infeed_width_factor, infeed_length_factor, max_spindle_speed, max_feedrate, coolant_through FROM Extensions ORDER BY extension_id").fetchall()
    count = 0
    for r in rows:
        existing = master.execute("SELECT id FROM prolunga WHERE codice_interno=?", (r['name'],)).fetchone()
        if existing:
            master.execute("""UPDATE prolunga SET descrizione=?, spindle_speed_factor=?, feedrate_factor=?,
                infeed_width_factor=?, infeed_length_factor=?, max_spindle_speed=?, max_feedrate=?,
                coolant_through=?, cam_sorgente='Hypermill', id_originale_cam=? WHERE codice_interno=?""",
                (r['comment'] or r['ordering_code'], r['spindle_speed_factor'], r['feedrate_factor'],
                 r['infeed_width_factor'], r['infeed_length_factor'], r['max_spindle_speed'] or None,
                 r['max_feedrate'] or None, r['coolant_through'], str(r['extension_id']), r['name']))
        else:
            master.execute("""INSERT INTO prolunga (codice_interno, descrizione, spindle_speed_factor, feedrate_factor,
                infeed_width_factor, infeed_length_factor, max_spindle_speed, max_feedrate, coolant_through,
                cam_sorgente, id_originale_cam) VALUES (?,?,?,?,?,?,?,?,?,'Hypermill',?)""",
                (r['name'], r['comment'] or r['ordering_code'], r['spindle_speed_factor'], r['feedrate_factor'],
                 r['infeed_width_factor'], r['infeed_length_factor'], r['max_spindle_speed'] or None,
                 r['max_feedrate'] or None, r['coolant_through'], str(r['extension_id'])))
        count += 1
    return count


def _importa_utensili(hm, master):
    id_tipo_map = {}
    for row in master.execute("SELECT id, codice FROM tipo_utensile").fetchall():
        id_tipo_map[row[1]] = row[0]
    id_tipo_default = id_tipo_map.get('UNKNOWN', 1)
    id_mat_default = master.execute("SELECT id FROM materiale_utensile WHERE codice='HM'").fetchone()
    id_mat_default = id_mat_default[0] if id_mat_default else 1

    porta_map = {}
    for row in master.execute("SELECT id, codice_interno FROM portautensile").fetchall():
        porta_map[row[1]] = row[0]
    prol_map = {}
    for row in master.execute("SELECT id, codice_interno FROM prolunga").fetchall():
        prol_map[row[1]] = row[0]
    grado_map = _build_grado_map(hm, master)
    master_cols = {r[1] for r in master.execute("PRAGMA table_info('utensile')").fetchall()}

    rows = hm.execute("""
        SELECT n.id as nc_id, n.nc_name, n.nc_number_str, n.nc_number_val,
            n.gage_length, n.tool_length, n.holder_reach, n.usable_length, n.clearance_length, n.preset_diameter,
            n.comment as nc_comment, n.spindle_speed_factor as nc_spd_factor, n.feedrate_factor as nc_feed_factor,
            n.infeed_width_factor as nc_ae_factor, n.infeed_length_factor as nc_ap_factor,
            COALESCE(c.reach, 0) as ext_reach, e.name as ext_name,
            t.id as tool_id, t.name as tool_name, t.comment as tool_comment,
            t.tool_type_id, t.total_length, t.ordering_code, t.cutting_material_id, t.spindle_direction,
            t.free_shaft_geom_id, t.free_tip_geom_id,
            t.dbl_param1, t.dbl_param2, t.dbl_param3, t.dbl_param4, t.dbl_param5, t.dbl_param6, t.dbl_param7, t.dbl_param8,
            t.dbl_param9, t.dbl_param10, t.dbl_param11, t.dbl_param12, t.dbl_param13, t.dbl_param14, t.dbl_param15, t.dbl_param16, t.dbl_param17,
            t.int_param1, t.int_param2, t.int_param3, t.int_param4, t.int_param5, t.int_param6,
            h.name as holder_name, h.comment as holder_comment,
            gh.polyline as holder_polyline, m.name as manufacturer_name
        FROM NCTools n JOIN Tools t ON n.tool_id = t.id
        LEFT JOIN Holders h ON n.holder_id = h.id
        LEFT JOIN HolderGeometries hg ON hg.holder_id = h.id
        LEFT JOIN Geometries gh ON gh.id = hg.geometry_id
        LEFT JOIN Manufacturers m ON t.manufacturer_id = m.manufacturer_id
        LEFT JOIN Components c ON c.nctool_id = n.id
        LEFT JOIN Extensions e ON c.extension_id = e.extension_id
        ORDER BY n.nc_number_val
    """).fetchall()

    rpm_map = {}
    for tech in hm.execute("""
        SELECT tt.tool_id, tech.dbl_param3 as rpm FROM ToolTechnologies tt
        JOIN Technologies tech ON tt.technology_id = tech.technology_id WHERE tech.dbl_param3 > 0
        ORDER BY tt.tool_id, tech.purpose_id
    """).fetchall():
        tid = tech['tool_id']
        if tid not in rpm_map:
            rpm_map[tid] = tech['rpm']

    count = 0
    for row in rows:
        geo = _estrai_geometria(row, row['tool_type_id'])
        tipo_str = TIPO_MAP.get(row['tool_type_id'], 'UNKNOWN')
        id_tipo = id_tipo_map.get(tipo_str, id_tipo_default)
        holder_geo, _ = _decodifica_holder(row['holder_polyline'], row['holder_name'] or '') if row['holder_polyline'] else ({}, [])
        holder_name = row['holder_name'] or ''
        tipo_attacco = _detect_tipo_attacco(holder_name, row['holder_comment'] or '')
        id_porta = porta_map.get(holder_name)
        id_prol = prol_map.get(row['ext_name']) if row['ext_name'] else None
        id_grado = grado_map.get(row['cutting_material_id'])
        dir_rot = 'CW' if row['spindle_direction'] == 0 else 'CCW'
        rpm_default = rpm_map.get(row['tool_id'])
        vc_default = None
        diam = geo.get('diametro_mm', 0)
        if rpm_default and diam:
            vc_default = round(rpm_default * diam * math.pi / 1000, 2)
        fuori_pinza = round((row['tool_length'] or 0) + (row['ext_reach'] or 0), 2) or None

        utensile = {
            'codice_interno': f"{row['nc_number_str'] or row['nc_name'] or ''}_hm_{row['nc_id']}",
            'alias': row['nc_name'] or '',
            'descrizione': row['tool_name'] or '',
            'codice_catalogo': row['ordering_code'] or '',
            'cam_sorgente': 'Hypermill',
            'id_originale_cam': str(row['nc_id']),
            'id_tipo': id_tipo,
            'id_materiale': id_mat_default,
            'id_portautensile': id_porta,
            'id_grado_utensile': id_grado,
            'id_prolunga': id_prol,
            'nome_pinza': holder_name or None,
            'tipo_attacco': tipo_attacco,
            'fuori_pinza_mm': fuori_pinza,
            'lungh_presa_mm': holder_geo.get('nl_lungh_serraggio_mm'),
            'lungh_libera_prolunga_mm': row['ext_reach'] or None,
            'gage_length_mm': row['gage_length'] or None,
            'usable_length_mm': row['usable_length'] or None,
            'clearance_length_mm': row['clearance_length'] or None,
            'preset_diameter_mm': row['preset_diameter'] or None,
            'd1_serraggio_mm': holder_geo.get('d1_serraggio_mm'),
            'd3_corpo_mm': holder_geo.get('d3_diam_corpo_mm'),
            'd_hsk_mm': holder_geo.get('d_hsk_mm'),
            'nl_serraggio_mm': holder_geo.get('nl_lungh_serraggio_mm'),
            'z_fine_cono_mm': holder_geo.get('z_fine_cono_mm'),
            'a_lungh_holder_mm': holder_geo.get('a_lungh_totale_mm'),
            'rotazione_default': rpm_default,
            'vc_default': vc_default,
            'dir_rotazione': dir_rot,
            'hm_tool_number': row['nc_number_val'],
            'hm_tool_type_id': str(row['tool_type_id']),
            **geo,
        }

        # Estrai profili polyline (gambo + punta) e salva come JSON + raw BLOB
        try:
            import json as _json
            profili = _leggi_profilo_fresa(row, hm)
            if profili['shaft_points']:
                utensile['profilo_gambo_json'] = _json.dumps({
                    'punti': profili['shaft_points'],
                    'lunghezza': profili['shaft_length'],
                })
            if profili['shaft_raw']:
                utensile['shaft_polyline_raw'] = profili['shaft_raw']
            if profili['tip_points']:
                utensile['profilo_punta_json'] = _json.dumps({
                    'punti': profili['tip_points'],
                })
        except Exception:
            pass
        utensile = {k: v for k, v in utensile.items() if v is not None and v != ''}
        insert_data = {k: v for k, v in utensile.items() if k in master_cols}
        codice = insert_data.get('codice_interno')
        try:
            # Controlla se esiste già
            existing = master.execute(
                "SELECT id FROM utensile WHERE codice_interno=?", (codice,)
            ).fetchone()
            if existing:
                # UPDATE: aggiorna tutti i campi tranne codice_interno
                upd = {k: v for k, v in insert_data.items() if k != 'codice_interno'}
                if upd:
                    sets = ', '.join(f'{k}=?' for k in upd)
                    master.execute(
                        f"UPDATE utensile SET {sets} WHERE codice_interno=?",
                        list(upd.values()) + [codice]
                    )
            else:
                # INSERT nuovo
                cols = ', '.join(insert_data.keys())
                ph = ', '.join(['?'] * len(insert_data))
                master.execute(f"INSERT INTO utensile ({cols}) VALUES ({ph})",
                               list(insert_data.values()))
            count += 1
        except Exception as e:
            if count == 0:
                print(f'Errore utensile: {e} | {codice}', file=sys.stderr)
    return count


def _importa_condizioni_taglio(hm, master):
    ut_map = {}
    for row in master.execute("SELECT id, id_originale_cam FROM utensile WHERE cam_sorgente='Hypermill'").fetchall():
        ut_map[row[1]] = row[0]
    mat_map = _build_material_map(hm, master)
    tool_info = {}
    for row in hm.execute("SELECT n.id as nc_id, t.dbl_param4 as diam, t.int_param1 as denti FROM NCTools n JOIN Tools t ON n.tool_id = t.id").fetchall():
        tool_info[row['nc_id']] = (row['diam'] or 0, row['denti'] or 0)
    rpm_lookup = {}
    for tech in hm.execute("SELECT cp.nctool_id, cp.technology_id, tech.dbl_param3 as rpm FROM CuttingProfiles cp JOIN Technologies tech ON cp.technology_id = tech.technology_id WHERE tech.dbl_param3 > 0").fetchall():
        rpm_lookup[(tech['nctool_id'], tech['technology_id'])] = tech['rpm']
    mat_names = {}
    for r in hm.execute("SELECT id, name FROM Materials").fetchall():
        mat_names[r['id']] = r['name']

    rows = hm.execute("""
        SELECT cp.nctool_id, cp.technology_id, cp.feedrate,
               cp.dbl_param5 as ae, cp.dbl_param7 as ap, cp.dbl_param13 as fz,
               cp.coolants, tech.material_id, tp.purpose
        FROM CuttingProfiles cp
        JOIN Technologies tech ON cp.technology_id = tech.technology_id
        LEFT JOIN TechnologyPurposes tp ON tech.purpose_id = tp.id
        WHERE cp.feedrate > 0
        ORDER BY cp.nctool_id, tech.material_id, tech.purpose_id
    """).fetchall()

    count = 0
    for r in rows:
        nc_id_str = str(r['nctool_id'])
        id_ut = ut_map.get(nc_id_str)
        if not id_ut: continue
        mat_name = mat_names.get(r['material_id'], 'Sconosciuto')
        id_mat = mat_map.get(r['material_id'])
        purpose = r['purpose'] or ''
        applicazione = PURPOSE_MAP.get(purpose, purpose) or 'Default'
        vf = r['feedrate']
        ae = r['ae'] if r['ae'] and r['ae'] > 0 else None
        ap = r['ap'] if r['ap'] and r['ap'] > 0 else None
        fz = r['fz'] if r['fz'] and r['fz'] > 0 else None
        rpm = rpm_lookup.get((r['nctool_id'], r['technology_id']))
        diam, denti = tool_info.get(r['nctool_id'], (0, 0))
        if not rpm and fz and denti:
            rpm = round(vf / (fz * denti), 1)
        vc = None
        if rpm and diam:
            vc = round(math.pi * diam * rpm / 1000, 2)
        refrig = COOLANT_MAP.get(r['coolants'], None)
        try:
            master.execute("""INSERT OR REPLACE INTO condizioni_taglio
                (id_utensile, id_materiale_pezzo, materiale_pezzo, applicazione, cam_sorgente,
                 vc_m_min, rotazione_rpm, fz_mm_z, avanzamento_mm_min, ap_mm, ae_mm, refrigerante)
                VALUES (?,?,?,?,'Hypermill',?,?,?,?,?,?,?)""",
                (id_ut, id_mat, mat_name, applicazione, vc, rpm, fz, vf, ap, ae, refrig))
            count += 1
        except Exception as e:
            if count == 0:
                print(f'Errore condizioni_taglio: {e}', file=sys.stderr)
    return count


def _build_material_map(hm, master):
    result = {}
    for r in hm.execute("SELECT id, name FROM Materials").fetchall():
        row = master.execute("SELECT id FROM materiale_pezzo WHERE nome = ?", (r['name'],)).fetchone()
        if row: result[r['id']] = row[0]
    return result


def _build_grado_map(hm, master):
    result = {}
    for r in hm.execute("SELECT id, name FROM CuttingMaterials").fetchall():
        row = master.execute("SELECT id FROM grado_utensile WHERE nome = ?", (r['name'],)).fetchone()
        if row: result[r['id']] = row[0]
    return result
