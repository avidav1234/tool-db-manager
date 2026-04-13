"""
worknc_importer.py
Importa utensili da librerie WorkNC nel DB master Tool DB Manager.

Formati supportati:
  .wkz  — file testo proprietario (un utensile per file, INI-like)
  .hlx  — holder XML (dal V19+)
  .hld  — holder legacy (profilo testo)
  Cartella — scansiona ricorsivamente per .wkz + .hlx/.hld

Struttura WKZ (reverse-engineered da documentazione VisuOutil/5axes):
  Blocchi [TOOL], [CUTTING], [HOLDER] con key=value
  Geometria: DIAMETER, CORNER_RADIUS, LENGTH, FLUTE_LENGTH, NB_TEETH, SHANK_DIAM
  Parametri: SPEED (RPM), FEED (mm/min), PLUNGE_FEED, DOC (ap), WOC (ae)
"""
import os, sys, re, sqlite3, math
from xml.etree import ElementTree as ET


# ── Mappature ────────────────────────────────────────────────────────────

TIPO_MAP = {
    'endmill':     'FLAT',
    'flatendmill':  'FLAT',
    'flat':        'FLAT',
    'ballnose':    'BALL',
    'ball':        'BALL',
    'ballendmill': 'BALL',
    'sphere':      'BALL',
    'bullnose':    'BULL',
    'bull':        'BULL',
    'torus':       'BULL',
    'torique':     'BULL',
    'torica':      'BULL',
    'drill':       'DRILL',
    'foret':       'DRILL',
    'punta':       'DRILL',
    'tap':         'TAP',
    'taraud':      'TAP',
    'maschio':     'TAP',
    'reamer':      'REAM',
    'alesoir':     'REAM',
    'alesatore':   'REAM',
    'spotdrill':   'SPOT',
    'centerdrill': 'SPOT',
    'centrino':    'SPOT',
    'chamfer':     'SPOT',
    'taper':       'TAPER',
    'conical':     'TAPER',
    'conico':      'TAPER',
    'threadmill':  'THREAD',
    'lollipop':    'LOLLIPOP',
    'tslot':       'LOLLIPOP',
    'formtool':    'FORM',
    'form':        'FORM',
}


def _detect_tipo(raw_type, tool_name=''):
    """Rileva tipo utensile da stringa tipo o nome file."""
    if raw_type:
        key = re.sub(r'[^a-z]', '', raw_type.lower())
        for pattern, tipo in TIPO_MAP.items():
            if pattern in key:
                return tipo
    # Fallback dal nome file/utensile
    name_lower = tool_name.lower()
    if 'ball' in name_lower or 'spher' in name_lower:
        return 'BALL'
    elif 'bull' in name_lower or 'torus' in name_lower or 'toric' in name_lower:
        return 'BULL'
    elif 'drill' in name_lower or 'foret' in name_lower:
        return 'DRILL'
    elif 'tap' in name_lower or 'taraud' in name_lower:
        return 'TAP'
    elif 'ream' in name_lower or 'alesoir' in name_lower:
        return 'REAM'
    return 'FLAT'


# ── Parser WKZ ───────────────────────────────────────────────────────────

def _parse_wkz(filepath):
    """
    Parsa un file .wkz WorkNC.
    Formato INI-like con sezioni [TOOL], [CUTTING], [HOLDER], ecc.
    Ritorna dict con tutte le key=value raggruppate per sezione.
    """
    result = {'_filepath': filepath, '_filename': os.path.basename(filepath)}
    current_section = 'GENERAL'

    encodings = ['utf-8', 'latin-1', 'cp1252']
    lines = None
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if not lines:
        return result

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//'):
            continue

        # Sezione [NOME]
        m = re.match(r'\[(\w+)\]', line)
        if m:
            current_section = m.group(1).upper()
            continue

        # Key=Value o Key:Value
        m = re.match(r'(\w[\w\s]*?)\s*[=:]\s*(.*)', line)
        if m:
            key = m.group(1).strip().upper().replace(' ', '_')
            val = m.group(2).strip().strip('"').strip("'")
            full_key = f'{current_section}.{key}'
            result[full_key] = val
            # Anche senza prefisso per accesso diretto
            if key not in result:
                result[key] = val

    return result


def _wkz_float(data, *keys):
    """Cerca un valore float tra diverse chiavi possibili."""
    for k in keys:
        for prefix in ('TOOL.', 'CUTTING.', 'GEOMETRY.', 'GENERAL.', ''):
            val = data.get(prefix + k)
            if val:
                try:
                    return float(val.replace(',', '.'))
                except (ValueError, TypeError):
                    continue
    return None


def _wkz_int(data, *keys):
    v = _wkz_float(data, *keys)
    return int(v) if v is not None else None


def _wkz_str(data, *keys):
    for k in keys:
        for prefix in ('TOOL.', 'GENERAL.', 'CUTTING.', ''):
            val = data.get(prefix + k)
            if val:
                return val
    return None


# ── Parser HLX (XML) ────────────────────────────────────────────────────

def _parse_hlx(filepath):
    """Parsa un file .hlx (holder XML) di WorkNC. Ritorna lista di segmenti."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except Exception:
        return []

    segmenti = []
    seg_num = 0

    # Cerca elementi che definiscono segmenti del profilo
    for elem in root.iter():
        tag = elem.tag.lower()
        if 'segment' in tag or 'section' in tag or 'profile' in tag:
            d_inf = None
            d_sup = None
            length = None

            for attr_name in ('diameter', 'diam', 'd', 'diameter_bottom', 'lower_diameter'):
                v = elem.get(attr_name) or elem.get(attr_name.upper())
                if v:
                    d_inf = float(v)
                    break

            for attr_name in ('upper_diameter', 'diameter_top', 'top_diameter'):
                v = elem.get(attr_name) or elem.get(attr_name.upper())
                if v:
                    d_sup = float(v)
                    break

            for attr_name in ('length', 'height', 'h', 'l'):
                v = elem.get(attr_name) or elem.get(attr_name.upper())
                if v:
                    length = float(v)
                    break

            if d_inf is not None and length:
                seg_num += 1
                segmenti.append({
                    'numero_segmento': seg_num,
                    'diametro_inf_mm': d_inf,
                    'diametro_sup_mm': d_sup if d_sup is not None else d_inf,
                    'lunghezza_mm': length,
                })

    # Fallback: cerca coppie (diametro, altezza) in qualsiasi elemento con testo numerico
    if not segmenti:
        for elem in root.iter():
            if elem.text and ',' in (elem.text or ''):
                parts = elem.text.strip().split(',')
                if len(parts) >= 2:
                    try:
                        d = float(parts[0])
                        h = float(parts[1])
                        seg_num += 1
                        segmenti.append({
                            'numero_segmento': seg_num,
                            'diametro_inf_mm': d,
                            'diametro_sup_mm': d,
                            'lunghezza_mm': h,
                        })
                    except ValueError:
                        continue

    return segmenti


# ── Parser HLD (legacy testo) ────────────────────────────────────────────

def _parse_hld(filepath):
    """Parsa un file .hld legacy di WorkNC. Profilo come lista di (raggio, z)."""
    segmenti = []
    points = []

    encodings = ['utf-8', 'latin-1', 'cp1252']
    lines = None
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if not lines:
        return segmenti

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//'):
            continue
        parts = re.split(r'[\s,;]+', line)
        if len(parts) >= 2:
            try:
                r_or_d = float(parts[0].replace(',', '.'))
                z = float(parts[1].replace(',', '.'))
                points.append((r_or_d, z))
            except ValueError:
                continue

    # Converti punti profilo in segmenti
    for i, (d, z) in enumerate(points):
        if i == 0:
            segmenti.append({
                'numero_segmento': 1,
                'diametro_inf_mm': d,
                'diametro_sup_mm': d,
                'lunghezza_mm': z,
            })
        else:
            prev_d, prev_z = points[i - 1]
            segmenti.append({
                'numero_segmento': i + 1,
                'diametro_inf_mm': prev_d,
                'diametro_sup_mm': d,
                'lunghezza_mm': round(z - prev_z, 3),
            })

    return segmenti


# ── Scansione cartella ───────────────────────────────────────────────────

def _scan_worknc_folder(folder_path):
    """Scansiona ricorsivamente una cartella per file .wkz, .hlx, .hld."""
    wkz_files = []
    hlx_files = {}
    hld_files = {}

    for root, dirs, files in os.walk(folder_path):
        for f in files:
            fpath = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            name = os.path.splitext(f)[0]

            if ext == '.wkz':
                wkz_files.append(fpath)
            elif ext == '.hlx':
                hlx_files[name.lower()] = fpath
            elif ext == '.hld':
                hld_files[name.lower()] = fpath

    return wkz_files, hlx_files, hld_files


# ══════════════════════════════════════════════════════════════════════════
#  IMPORT PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════

def importa_worknc(filepath, master_db_path, dry_run=False):
    """
    Importa utensili da file/cartella WorkNC nel DB master.
    Supporta: singolo .wkz, singolo .hlx, o cartella con multipli.
    """
    stats = {
        'utensili': 0,
        'condizioni_taglio': 0,
        'portautensili': 0,
        'segmenti_holder': 0,
        'errori': 0,
        'dry_run': dry_run,
    }

    # Determina cosa importare
    if os.path.isdir(filepath):
        wkz_files, hlx_files, hld_files = _scan_worknc_folder(filepath)
    elif filepath.lower().endswith('.wkz'):
        wkz_files = [filepath]
        hlx_files = {}
        hld_files = {}
        # Cerca holder nella stessa cartella
        folder = os.path.dirname(filepath)
        for f in os.listdir(folder):
            ext = os.path.splitext(f)[1].lower()
            name = os.path.splitext(f)[0].lower()
            if ext == '.hlx':
                hlx_files[name] = os.path.join(folder, f)
            elif ext == '.hld':
                hld_files[name] = os.path.join(folder, f)
    else:
        return {**stats, 'errore': f'Formato non supportato: {filepath}'}

    if not wkz_files:
        return {**stats, 'errore': 'Nessun file .wkz trovato'}

    if dry_run:
        stats['utensili'] = len(wkz_files)
        stats['portautensili'] = len(hlx_files) + len(hld_files)
        return stats

    master = sqlite3.connect(master_db_path)
    master.execute("PRAGMA foreign_keys = ON")
    master.row_factory = sqlite3.Row

    # Lookup tipi
    id_tipo_map = {}
    for row in master.execute("SELECT id, codice FROM tipo_utensile").fetchall():
        id_tipo_map[row['codice']] = row['id']
    id_tipo_default = id_tipo_map.get('FLAT', 1)
    id_mat_default = master.execute(
        "SELECT id FROM materiale_utensile WHERE codice='HM'"
    ).fetchone()
    id_mat_default = id_mat_default[0] if id_mat_default else 1

    master_cols = {r[1] for r in master.execute("PRAGMA table_info('utensile')").fetchall()}

    # ── Import holders ──
    holder_id_map = {}  # nome_holder → portautensile.id

    for name, hpath in {**hld_files, **hlx_files}.items():
        try:
            if hpath.lower().endswith('.hlx'):
                segs = _parse_hlx(hpath)
            else:
                segs = _parse_hld(hpath)

            holder_name = os.path.splitext(os.path.basename(hpath))[0]
            master.execute("""
                INSERT OR IGNORE INTO portautensile
                    (codice_interno, descrizione, num_segmenti, cam_sorgente, id_originale_cam)
                VALUES (?, ?, ?, 'WorkNC', ?)
            """, (holder_name, holder_name, len(segs), holder_name))

            row = master.execute(
                "SELECT id FROM portautensile WHERE codice_interno=?", (holder_name,)
            ).fetchone()
            if row:
                pid = row[0]
                holder_id_map[name] = pid
                for seg in segs:
                    master.execute("""
                        INSERT OR IGNORE INTO portautensile_segmento
                            (id_portautensile, numero_segmento,
                             diametro_inf_mm, diametro_sup_mm, lunghezza_mm)
                        VALUES (?, ?, ?, ?, ?)
                    """, (pid, seg['numero_segmento'],
                          seg['diametro_inf_mm'], seg['diametro_sup_mm'],
                          seg['lunghezza_mm']))
                    stats['segmenti_holder'] += 1
                stats['portautensili'] += 1
        except Exception as e:
            stats['errori'] += 1
            if stats['errori'] == 1:
                print(f'Errore holder {name}: {e}', file=sys.stderr)

    # ── Import utensili da WKZ ──
    for wkz_path in wkz_files:
        try:
            data = _parse_wkz(wkz_path)
            filename = os.path.splitext(os.path.basename(wkz_path))[0]

            # Geometria
            diam = _wkz_float(data, 'DIAMETER', 'DIAM', 'D', 'DIA', 'TOOL_DIAMETER')
            if not diam or diam <= 0:
                continue

            corner_r = _wkz_float(data, 'CORNER_RADIUS', 'RADIUS', 'CR', 'RE', 'TOOL_RADIUS')
            length = _wkz_float(data, 'LENGTH', 'OVERALL_LENGTH', 'OAL', 'TOOL_LENGTH', 'TOTAL_LENGTH')
            flute_l = _wkz_float(data, 'FLUTE_LENGTH', 'CUTTING_LENGTH', 'LCF', 'CUT_LENGTH')
            n_flutes = _wkz_int(data, 'NB_TEETH', 'TEETH', 'FLUTES', 'NUM_FLUTES', 'NOF', 'Z')
            shank_d = _wkz_float(data, 'SHANK_DIAM', 'SHANK_DIAMETER', 'SHANK', 'SFDM')
            point_angle = _wkz_float(data, 'POINT_ANGLE', 'TIP_ANGLE', 'ANGLE')
            taper_angle = _wkz_float(data, 'TAPER_ANGLE', 'CONE_ANGLE')

            # Tipo
            raw_type = _wkz_str(data, 'TYPE', 'TOOL_TYPE', 'CATEGORY')
            tipo_str = _detect_tipo(raw_type, filename)
            id_tipo = id_tipo_map.get(tipo_str, id_tipo_default)

            # Nome/descrizione
            tool_name = _wkz_str(data, 'NAME', 'TOOL_NAME', 'DESCRIPTION', 'COMMENT') or filename
            codice = f"{filename}_wnc"

            # Holder reference
            holder_ref = _wkz_str(data, 'HOLDER', 'HOLDER_NAME', 'HOLDER_FILE')
            id_porta = None
            if holder_ref:
                h_key = os.path.splitext(os.path.basename(holder_ref))[0].lower()
                id_porta = holder_id_map.get(h_key)

            # Parametri taglio
            rpm = _wkz_float(data, 'SPEED', 'RPM', 'SPINDLE_SPEED', 'N', 'CUTTING.SPEED')
            feed = _wkz_float(data, 'FEED', 'FEEDRATE', 'FEED_RATE', 'VF', 'CUTTING.FEED')
            fz = _wkz_float(data, 'FZ', 'FEED_PER_TOOTH', 'FEED_TOOTH')
            vc = _wkz_float(data, 'VC', 'CUTTING_SPEED', 'SURFACE_SPEED')
            ap = _wkz_float(data, 'DOC', 'AP', 'DEPTH_OF_CUT', 'STEP_DOWN', 'CUTTING.DOC')
            ae = _wkz_float(data, 'WOC', 'AE', 'WIDTH_OF_CUT', 'STEP_OVER', 'CUTTING.WOC')

            # Calcola valori mancanti
            if not vc and rpm and diam:
                vc = round(math.pi * diam * rpm / 1000, 2)
            if not rpm and vc and diam:
                rpm = round(vc * 1000 / (math.pi * diam), 1)
            if not fz and feed and rpm and n_flutes:
                fz = round(feed / (rpm * n_flutes), 4)

            # Ball nose: raggio = D/2
            if tipo_str == 'BALL' and not corner_r and diam:
                corner_r = round(diam / 2, 4)

            utensile = {
                'codice_interno': codice,
                'alias': tool_name,
                'descrizione': tool_name,
                'cam_sorgente': 'WorkNC',
                'id_originale_cam': filename,
                'id_tipo': id_tipo,
                'id_materiale': id_mat_default,
                'id_portautensile': id_porta,
                'diametro_mm': diam,
                'raggio_punta_mm': corner_r,
                'lunghezza_totale_mm': length,
                'lunghezza_tagl_mm': flute_l,
                'num_taglienti': n_flutes,
                'diam_stelo_mm': shank_d,
                'angolo_punta_gradi': point_angle,
                'angolo_conico_gradi': taper_angle,
                'rotazione_default': rpm,
                'avanzamento_default': feed,
                'vc_default': vc,
                'fz_default': fz,
                'passo_z_default': ap,
                'passo_lat_default': ae,
                'wnc_tool_id': filename,
            }

            utensile = {k: v for k, v in utensile.items() if v is not None}
            insert_data = {k: v for k, v in utensile.items() if k in master_cols}

            cols = ', '.join(insert_data.keys())
            ph = ', '.join(['?'] * len(insert_data))
            master.execute(f"INSERT OR IGNORE INTO utensile ({cols}) VALUES ({ph})",
                           list(insert_data.values()))
            stats['utensili'] += 1

            # Condizioni taglio (se presenti)
            if any([vc, fz, feed, rpm, ap, ae]):
                ut_row = master.execute(
                    "SELECT id FROM utensile WHERE codice_interno=?", (codice,)
                ).fetchone()
                if ut_row:
                    # Cerca materiale dal path (convenzione WorkNC: cartella = materiale)
                    rel_path = os.path.relpath(wkz_path, filepath) if os.path.isdir(filepath) else ''
                    materiale = _detect_materiale_da_path(rel_path)

                    master.execute("""
                        INSERT OR REPLACE INTO condizioni_taglio
                            (id_utensile, materiale_pezzo, applicazione, cam_sorgente,
                             vc_m_min, rotazione_rpm, fz_mm_z,
                             avanzamento_mm_min, ap_mm, ae_mm)
                        VALUES (?, ?, ?, 'WorkNC', ?, ?, ?, ?, ?, ?)
                    """, (ut_row[0], materiale, 'Default',
                          vc, rpm, fz, feed, ap, ae))
                    stats['condizioni_taglio'] += 1

        except Exception as e:
            stats['errori'] += 1
            if stats['errori'] <= 3:
                print(f'Errore WKZ {wkz_path}: {e}', file=sys.stderr)

    master.commit()
    master.close()

    return stats


def _detect_materiale_da_path(rel_path):
    """Rileva il materiale pezzo dal percorso cartella (convenzione WorkNC)."""
    path_lower = rel_path.lower()
    if any(x in path_lower for x in ('alumin', 'alluminio', 'alu')):
        return 'Alluminio'
    elif any(x in path_lower for x in ('inox', 'stainless')):
        return 'Acciaio Inox'
    elif any(x in path_lower for x in ('titan', 'ti6al')):
        return 'Titanio'
    elif any(x in path_lower for x in ('inconel', 'hastelloy', 'nimonic')):
        return 'Inconel'
    elif any(x in path_lower for x in ('ghisa', 'cast_iron', 'fonte')):
        return 'Ghisa'
    elif any(x in path_lower for x in ('acciaio', 'steel', 'acier', 'stahl')):
        return 'Acciaio'
    return 'Generico'


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Uso: python {sys.argv[0]} <cartella_o_file.wkz> [master.db] [--dry-run]")
        sys.exit(1)

    src = sys.argv[1]
    db = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('-') \
        else os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')
    dr = '--dry-run' in sys.argv

    import json
    result = importa_worknc(src, db, dry_run=dr)
    print(json.dumps(result, indent=2, ensure_ascii=False))
