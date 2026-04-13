"""
fusion360_importer.py  –  v1.0
Importa utensili da librerie Fusion 360 (.tools / .json) nel DB master Tool DB Manager.

Formati supportati:
  .tools  →  archivio ZIP contenente un file JSON (tools.json o simile)
  .json   →  file JSON diretto con struttura Fusion 360 tool library

Struttura JSON attesa:
  { "data": [ { "description": ..., "type": ..., "unit": ...,
                 "geometry": { "DC": ..., "RE": ..., "LCF": ..., ... },
                 "BMC": "carbide", "holder": {...},
                 "start-values": { "presets": [...] },
                 "post-process": { "number": ..., "comment": ... }
               }, ... ] }

Tabelle master popolate:
  utensile, portautensile, portautensile_segmento, condizioni_taglio
"""
import sqlite3, os, sys, json, zipfile, math


# ── Mappature Fusion 360 → master ──────────────────────────────────────────

TIPO_MAP = {
    'flat end mill':        'FLAT',
    'ball end mill':        'BALL',
    'bull nose end mill':   'BULL',
    'drill':                'DRILL',
    'tap right hand':       'TAP',
    'tap left hand':        'TAP',
    'tap':                  'TAP',
    'reamer':               'REAM',
    'spot drill':           'SPOT',
    'center drill':         'SPOT',
    'boring bar':           'BORING',
    'counter bore':         'FLAT',
    'counter sink':         'SPOT',
    'chamfer mill':         'TAPER',
    'taper mill':           'TAPER',
    'face mill':            'FLAT',
    'slot mill':            'FLAT',
    'radius mill':          'BULL',
    'dovetail mill':        'FORM',
    'lollipop mill':        'LOLLIPOP',
    'thread mill':          'THREAD',
    'form mill':            'FORM',
    'turning general':      'TURN',
    'turning threading':    'TURN',
    'turning grooving':     'TURN',
    'turning boring':       'BORING',
}

MATERIALE_MAP = {
    'carbide':          'HM',
    'hss':              'HSS',
    'high speed steel': 'HSS',
    'hss-e':            'HSS-E',
    'cobalt':           'HSS-E',
    'cbn':              'CBN',
    'ceramics':         'CERAMICA',
    'ceramic':          'CERAMICA',
    'cermet':           'CERMET',
    'pcd':              'PCD',
    'diamond':          'PCD',
    'unspecified':      'HM',
}

COOLANT_MAP = {
    'disabled':     'OFF',
    'flood':        'Flood',
    'mist':         'Mist',
    'through':      'Through',
    'air':          'Air',
    'suction':      'Suction',
    'through-tool': 'Through',
}

INCH_TO_MM = 25.4


# ── Utilità ────────────────────────────────────────────────────────────────

def _load_json_from_file(filepath):
    """Carica il JSON da un file .tools (ZIP) o .json diretto."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.tools':
        with zipfile.ZipFile(filepath, 'r') as zf:
            json_names = [n for n in zf.namelist() if n.lower().endswith('.json')]
            if not json_names:
                raise ValueError(f"Nessun file JSON trovato dentro {filepath}")
            # Preferisci tools.json, altrimenti il primo .json trovato
            target = None
            for n in json_names:
                if os.path.basename(n).lower() == 'tools.json':
                    target = n
                    break
            if target is None:
                target = json_names[0]
            with zf.open(target) as f:
                return json.loads(f.read().decode('utf-8'))
    elif ext == '.json':
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        raise ValueError(f"Formato non supportato: {ext} (atteso .tools o .json)")


def _conv(val, unit, is_length=True):
    """Converte un valore da inch a mm se necessario. Ritorna None se manca."""
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return 0.0
    if unit == 'inches' and is_length:
        v = round(v * INCH_TO_MM, 4)
    return round(v, 4)


def _conv_speed(val, unit):
    """Converte velocità di taglio (m/min o ft/min → m/min)."""
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    if unit == 'inches':
        v = round(v * 0.3048, 4)   # ft/min → m/min
    return round(v, 4)


def _conv_feed(val, unit):
    """Converte avanzamento (mm/min o in/min → mm/min)."""
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    if unit == 'inches':
        v = round(v * INCH_TO_MM, 4)
    return round(v, 4)


def _conv_fpt(val, unit):
    """Converte feed-per-tooth (mm/z o in/z → mm/z)."""
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    if unit == 'inches':
        v = round(v * INCH_TO_MM, 6)
    return round(v, 6)


def _safe_get(d, *keys, default=None):
    """Naviga un dict annidato in sicurezza."""
    cur = d
    for k in keys:
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return default
        if cur is None:
            return default
    return cur


def _map_coolant(tool_data):
    """Estrai tipo di refrigerante dal JSON Fusion."""
    coolant = _safe_get(tool_data, 'start-values', 'presets', 0, 'f_coolant')
    if coolant is None:
        coolant = _safe_get(tool_data, 'shaft', 'coolant')
    if coolant is None:
        return None
    return COOLANT_MAP.get(str(coolant).lower(), str(coolant))


# ── Import principale ─────────────────────────────────────────────────────

def importa_fusion360(filepath, master_db_path, dry_run=False):
    """
    Importa una libreria utensili Fusion 360 nel database master.

    Args:
        filepath:       percorso al file .tools (ZIP) o .json
        master_db_path: percorso al database master SQLite
        dry_run:        se True, conta senza scrivere

    Returns:
        dict con statistiche: utensili, condizioni_taglio, portautensili, errori
    """
    if not os.path.isfile(filepath):
        return {'errore': f'File non trovato: {filepath}'}

    try:
        data = _load_json_from_file(filepath)
    except Exception as e:
        return {'errore': f'Errore lettura file: {e}'}

    # Supporta sia {"data": [...]} sia lista diretta
    if isinstance(data, dict):
        tools = data.get('data', [])
    elif isinstance(data, list):
        tools = data
    else:
        return {'errore': 'Struttura JSON non riconosciuta (atteso oggetto con "data" o array)'}

    if not tools:
        return {'errore': 'Nessun utensile trovato nel file'}

    stats = {
        'utensili': 0,
        'condizioni_taglio': 0,
        'portautensili': 0,
        'segmenti_holder': 0,
        'errori': 0,
        'dry_run': dry_run,
    }

    if dry_run:
        stats['utensili'] = len(tools)
        # Conta tool con preset di taglio
        for t in tools:
            presets = _safe_get(t, 'start-values', 'presets') or []
            stats['condizioni_taglio'] += len(presets) if presets else 0
            if _safe_get(t, 'holder'):
                stats['portautensili'] += 1
        return stats

    master = sqlite3.connect(master_db_path)
    master.execute("PRAGMA foreign_keys = ON")
    master.execute("PRAGMA journal_mode = WAL")

    try:
        # Costruisci mappe dizionari
        id_tipo_map = {}
        for row in master.execute("SELECT id, codice FROM tipo_utensile").fetchall():
            id_tipo_map[row[1]] = row[0]
        id_tipo_default = id_tipo_map.get('UNKNOWN', 1)

        id_mat_map = {}
        for row in master.execute("SELECT id, codice FROM materiale_utensile").fetchall():
            id_mat_map[row[1]] = row[0]
        id_mat_default = id_mat_map.get('HM', 1)

        master_cols = {r[1] for r in master.execute("PRAGMA table_info('utensile')").fetchall()}

        lib_name = os.path.splitext(os.path.basename(filepath))[0]

        for idx, tool in enumerate(tools):
            try:
                _importa_singolo_utensile(
                    tool, idx, lib_name, master,
                    id_tipo_map, id_tipo_default,
                    id_mat_map, id_mat_default,
                    master_cols, stats,
                )
            except Exception as e:
                stats['errori'] += 1
                desc = _safe_get(tool, 'description') or f'tool#{idx}'
                if stats['errori'] <= 5:
                    print(f'Errore import Fusion360 [{desc}]: {e}', file=sys.stderr)

        master.commit()
    except Exception as e:
        master.rollback()
        stats['errore'] = str(e)
        import traceback
        traceback.print_exc()
    finally:
        master.close()

    return stats


def _importa_singolo_utensile(tool, idx, lib_name, master,
                               id_tipo_map, id_tipo_default,
                               id_mat_map, id_mat_default,
                               master_cols, stats):
    """Importa un singolo utensile dal JSON Fusion 360."""

    unit = (tool.get('unit') or 'millimeters').lower()
    geo = tool.get('geometry') or {}
    post = tool.get('post-process') or {}
    description = tool.get('description') or ''
    tool_type_str = (tool.get('type') or '').lower()
    bmc = (tool.get('BMC') or 'carbide').lower()

    # ── Tipo e materiale ───────────────────────────────────────────────────
    tipo_codice = TIPO_MAP.get(tool_type_str, 'UNKNOWN')
    id_tipo = id_tipo_map.get(tipo_codice, id_tipo_default)
    mat_codice = MATERIALE_MAP.get(bmc, 'HM')
    id_materiale = id_mat_map.get(mat_codice, id_mat_default)

    # ── Geometria ──────────────────────────────────────────────────────────
    diametro     = _conv(geo.get('DC'), unit)
    raggio_punta = _conv(geo.get('RE'), unit)
    lunghezza_tagl = _conv(geo.get('LCF'), unit)
    lunghezza_tot  = _conv(geo.get('OAL'), unit)
    lunghezza_body = _conv(geo.get('LB'), unit)
    diam_stelo     = _conv(geo.get('SFDM'), unit)
    num_taglienti  = geo.get('NOF')
    angolo_conico  = geo.get('TA')  # gradi, non serve conversione
    angolo_punta   = geo.get('SIG')  # angolo punta (punte)
    angolo_elica   = geo.get('HA')   # angolo elica

    # Se raggio_punta mancante, calcola per tipo sfera
    if raggio_punta is None and tipo_codice == 'BALL' and diametro:
        raggio_punta = round(diametro / 2.0, 4)
    elif raggio_punta is None:
        raggio_punta = 0.0

    # ── Tool number e codice interno ───────────────────────────────────────
    tool_number = post.get('number')
    comment = post.get('comment') or ''
    product_id = tool.get('product-id') or ''

    codice_interno = f"F360_{lib_name}_{idx+1}"
    if tool_number is not None:
        codice_interno = f"F360_T{tool_number}_{lib_name}"

    alias = description or comment or codice_interno

    # ── Holder (portautensile) ─────────────────────────────────────────────
    id_portautensile = None
    holder_data = tool.get('holder') or {}
    holder_segments_raw = holder_data.get('segments') or []
    if holder_segments_raw:
        id_portautensile = _importa_holder(
            holder_data, holder_segments_raw, unit, codice_interno, master, stats
        )

    # ── Parametri di taglio default (dal primo preset) ─────────────────────
    presets = _safe_get(tool, 'start-values', 'presets') or []
    rpm_default = None
    vf_default = None
    vc_default = None
    fz_default = None

    if presets:
        p0 = presets[0]
        rpm_default = p0.get('n')
        vf_default  = _conv_feed(p0.get('v_f'), unit)
        vc_default  = _conv_speed(p0.get('v_c'), unit)
        fz_default  = _conv_fpt(p0.get('f_z'), unit)

        # Calcola vc se mancante
        if not vc_default and rpm_default and diametro:
            vc_default = round(math.pi * diametro * rpm_default / 1000, 2)

        # Calcola fz se mancante
        if not fz_default and vf_default and rpm_default and num_taglienti:
            try:
                fz_default = round(vf_default / (rpm_default * num_taglienti), 6)
            except ZeroDivisionError:
                pass

    # ── Refrigerante ───────────────────────────────────────────────────────
    refrigerante = _map_coolant(tool)

    # ── Fuori pinza ────────────────────────────────────────────────────────
    fuori_pinza = None
    if lunghezza_tot and diam_stelo:
        # Stima: lunghezza totale meno qualcosa per la presa
        fuori_pinza = lunghezza_tot

    # ── Costruisci record utensile ─────────────────────────────────────────
    utensile = {
        'codice_interno':       codice_interno,
        'alias':                alias,
        'descrizione':          description,
        'cam_sorgente':         'Fusion360',
        'id_originale_cam':     str(product_id or f'{lib_name}_{idx}'),
        'id_tipo':              id_tipo,
        'id_materiale':         id_materiale,
        'id_portautensile':     id_portautensile,
        'diametro_mm':          diametro or 0,
        'raggio_punta_mm':      raggio_punta,
        'angolo_punta_gradi':   angolo_punta,
        'lunghezza_totale_mm':  lunghezza_tot or 0,
        'lunghezza_tagl_mm':    lunghezza_tagl or 0,
        'num_taglienti':        num_taglienti,
        'angolo_conico_gradi':  angolo_conico,
        'angolo_elica_gradi':   angolo_elica,
        'diam_stelo_mm':        diam_stelo,
        'fuori_pinza_mm':       fuori_pinza,
        'rotazione_default':    rpm_default,
        'avanzamento_default':  vf_default,
        'vc_default':           vc_default,
        'fz_default':           fz_default,
        'refrigerante':         refrigerante,
        'hm_tool_number':       tool_number,
        'f360_library':         lib_name,
        'f360_product_id':      product_id or None,
        'nome_pinza':           None,
    }

    # Rimuovi None e stringa vuota
    utensile = {k: v for k, v in utensile.items() if v is not None and v != ''}
    insert_data = {k: v for k, v in utensile.items() if k in master_cols}

    cols = ', '.join(insert_data.keys())
    ph = ', '.join(['?'] * len(insert_data))
    master.execute(f"INSERT INTO utensile ({cols}) VALUES ({ph})", list(insert_data.values()))
    stats['utensili'] += 1

    # ── Condizioni di taglio (tutti i preset) ──────────────────────────────
    ut_id = master.execute(
        "SELECT id FROM utensile WHERE codice_interno = ?", (codice_interno,)
    ).fetchone()
    if ut_id and presets:
        ut_id = ut_id[0]
        _importa_presets(presets, ut_id, unit, diametro, num_taglienti, master, stats)


def _importa_holder(holder_data, segments_raw, unit, tool_codice, master, stats):
    """Importa portautensile con segmenti. Ritorna id_portautensile o None."""
    holder_codice = f"F360_H_{tool_codice}"
    descrizione = holder_data.get('description') or holder_codice

    # Inserisci portautensile
    try:
        master.execute("""INSERT OR IGNORE INTO portautensile
            (codice_interno, descrizione, num_segmenti, cam_sorgente, id_originale_cam)
            VALUES (?,?,?,?,?)""",
            (holder_codice, descrizione, len(segments_raw), 'Fusion360', holder_codice))
    except Exception:
        pass

    row = master.execute(
        "SELECT id FROM portautensile WHERE codice_interno = ?", (holder_codice,)
    ).fetchone()
    if not row:
        return None

    porta_id = row[0]
    stats['portautensili'] += 1

    # Inserisci segmenti
    for i, seg in enumerate(segments_raw):
        d_upper = _conv(seg.get('upper-diameter') or seg.get('diameter'), unit)
        d_lower = _conv(seg.get('lower-diameter') or seg.get('diameter'), unit)
        length  = _conv(seg.get('height') or seg.get('length'), unit)

        if d_upper is None and d_lower is None:
            continue

        try:
            master.execute("""INSERT OR IGNORE INTO portautensile_segmento
                (id_portautensile, numero_segmento, diametro_sup_mm, diametro_inf_mm, lunghezza_mm)
                VALUES (?,?,?,?,?)""",
                (porta_id, i + 1, d_upper, d_lower, length))
            stats['segmenti_holder'] += 1
        except Exception:
            pass

    return porta_id


def _importa_presets(presets, ut_id, unit, diametro, num_taglienti, master, stats):
    """Importa i preset come condizioni_taglio."""
    for pidx, preset in enumerate(presets):
        nome_preset = preset.get('name') or preset.get('description') or f'Preset {pidx+1}'
        applicazione = nome_preset

        rpm  = preset.get('n')
        vf   = _conv_feed(preset.get('v_f'), unit)
        vc   = _conv_speed(preset.get('v_c'), unit)
        fz   = _conv_fpt(preset.get('f_z'), unit)
        f_n  = _conv_fpt(preset.get('f_n'), unit)  # feed per revolution
        ap   = _conv(preset.get('a_p') or preset.get('ap'), unit)
        ae   = _conv(preset.get('a_e') or preset.get('ae'), unit)

        # Calcolo derivati
        if not vc and rpm and diametro:
            vc = round(math.pi * diametro * rpm / 1000, 2)
        if not fz and f_n and num_taglienti and num_taglienti > 0:
            fz = round(f_n / num_taglienti, 6)
        if not fz and vf and rpm and num_taglienti:
            try:
                fz = round(vf / (rpm * num_taglienti), 6)
            except ZeroDivisionError:
                pass
        if not vf and fz and rpm and num_taglienti:
            vf = round(fz * rpm * num_taglienti, 2)

        # Salta preset vuoti
        if not any([rpm, vf, vc, fz]):
            continue

        # Materiale pezzo dal preset
        mat_pezzo = preset.get('workpiece') or preset.get('material') or 'Default'
        if isinstance(mat_pezzo, dict):
            mat_pezzo = mat_pezzo.get('name', 'Default')

        # Refrigerante dal preset
        coolant = preset.get('f_coolant') or preset.get('coolant')
        refrig = COOLANT_MAP.get(str(coolant).lower(), None) if coolant else None

        try:
            master.execute("""INSERT OR REPLACE INTO condizioni_taglio
                (id_utensile, materiale_pezzo, applicazione, cam_sorgente,
                 vc_m_min, rotazione_rpm, fz_mm_z, avanzamento_mm_min, ap_mm, ae_mm, refrigerante)
                VALUES (?,?,?,'Fusion360',?,?,?,?,?,?,?)""",
                (ut_id, mat_pezzo, applicazione, vc, rpm, fz, vf, ap, ae, refrig))
            stats['condizioni_taglio'] += 1
        except Exception as e:
            if stats['condizioni_taglio'] == 0:
                print(f'Errore condizioni_taglio Fusion360: {e}', file=sys.stderr)


# ── Entry point CLI ────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Uso: python {sys.argv[0]} <file.tools|file.json> <master.db> [--dry-run]")
        sys.exit(1)
    filepath = sys.argv[1]
    master_db = sys.argv[2]
    dry = '--dry-run' in sys.argv
    result = importa_fusion360(filepath, master_db, dry_run=dry)
    print(json.dumps(result, indent=2, ensure_ascii=False))
