#!/usr/bin/env python3
"""
import_hypermill_xml.py — Parser XML HyperMill (formato OMTDX v34)

Struttura XML:
  <tools>/<tool>        = geometria fresa (diametro, raggio, taglienti, ecc.)
    <tecsets>/<tecset>  = parametri taglio per materiale (vc, fz, ae, ap)
  <holders>/<holder>    = portautensili con geometria cont2D
  <ncTools>/<ncTool>    = assemblaggio (fresa + holder + prolunga) con fuori_pinza
    <components>        = lista componenti (spindle, holder, extension, tool)

Relazioni:
  ncTool.components[type=tool].name → tool.name (collegamento)
  ncTool.components[type=holder].name → holder.name
  tecset dentro tool.tecsets (parametri del tool, non dell'ncTool)
"""
import xml.etree.ElementTree as ET
import sqlite3
import os
import sys

_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

TIPO_MAP = {
    'radiusMill': 'BULL', 'ballMill': 'BALL', 'flatMill': 'FLAT',
    'drill': 'DRILL', 'tap': 'TAP', 'reamer': 'REAM',
    'chamferMill': 'SPOT', 'threadMill': 'THREAD', 'lollipopMill': 'LOLLIPOP',
    'formMill': 'FORM',
}

# Fallback tipo da percorso cartella
FOLDER_TIPO_MAP = {
    'toric': 'BULL', 'sferic': 'BALL', 'piatt': 'FLAT', 'flat': 'FLAT',
    'drill': 'DRILL', 'punta': 'DRILL', 'tap': 'TAP', 'maschi': 'TAP',
    'ream': 'REAM', 'alesat': 'REAM', 'filettare': 'THREAD',
    'lollipop': 'LOLLIPOP', 'chamfer': 'SPOT', 'smussat': 'SPOT',
}


def _param(el, name, default=None):
    """Legge un parametro <param name=X value=Y> da un elemento XML."""
    for p in el:
        pt = p.tag.split('}')[-1] if '}' in p.tag else p.tag
        if pt == 'param' and p.get('name') == name:
            return p.get('value', default)
    return default


def _float(val, default=None):
    if val is None:
        return default
    try:
        return round(float(val), 6)
    except (ValueError, TypeError):
        return default


def _int(val, default=None):
    f = _float(val)
    return int(f) if f is not None else default


def _get_tipo_id(conn, codice):
    """Lookup o crea tipo_utensile, ritorna id."""
    r = conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (codice,)).fetchone()
    if r:
        return r[0]
    conn.execute("INSERT OR IGNORE INTO tipo_utensile (codice, descrizione) VALUES (?,?)",
                 (codice, codice))
    conn.commit()
    r = conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (codice,)).fetchone()
    return r[0] if r else 1


def _get_materiale_id(conn):
    """Ritorna id materiale_utensile default (HM o primo)."""
    r = conn.execute("SELECT id FROM materiale_utensile WHERE codice='HM'").fetchone()
    if r:
        return r[0]
    r = conn.execute("SELECT id FROM materiale_utensile ORDER BY id LIMIT 1").fetchone()
    return r[0] if r else 1


def _tipo_from_folder(path):
    """Indovina il tipo dal percorso cartella come fallback."""
    low = path.lower()
    for k, v in FOLDER_TIPO_MAP.items():
        if k in low:
            return v
    return 'UNKNOWN'


def _ensure_columns(conn):
    """Aggiunge colonne mancanti per compat con DB vecchi."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(utensile)")}
    for col, decl in [
        ('stato', "TEXT DEFAULT 'staging'"),
        ('famiglia_id', 'INTEGER'),
        ('impiego', 'TEXT'),
        ('promosso_da', 'TEXT'),
        ('promosso_il', 'TEXT'),
        ('gage_length_mm', 'REAL'),
        ('fattore_s', 'REAL DEFAULT 1.0'),
        ('fattore_f', 'REAL DEFAULT 1.0'),
        ('fattore_ae', 'REAL DEFAULT 1.0'),
        ('fattore_ap', 'REAL DEFAULT 1.0'),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE utensile ADD COLUMN {col} {decl}")
    conn.commit()


def import_xml(filepath, db_path, dry_run=False):
    """Importa file XML HyperMill nel DB master.

    Returns: dict con utensili_trovati, utensili_importati, nctools_importati,
             condizioni_importate, holders_importati, errori
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Indici per lookup rapido
    # 1) Tutti i tool (geometria) indicizzati per name
    tools_by_name = {}
    tools_by_guid = {}
    for tool_el in root.iter('tool'):
        name = tool_el.get('name', '')
        guid = _param(tool_el, 'objGuid', '')
        if name:
            tools_by_name[name] = tool_el
        if guid:
            tools_by_guid[guid] = tool_el

    # 2) Tutti gli holder indicizzati per name
    holders_by_name = {}
    for h_el in root.iter('holder'):
        name = h_el.get('name', '')
        if name:
            holders_by_name[name] = h_el

    # 3) Raccogli path cartella per ogni ncTool
    parent_map = {c: p for p in root.iter() for c in p}

    def _folder_path(el):
        parts = []
        cur = el
        while cur is not None:
            f = cur.get('folder', '')
            if f:
                parts.append(f)
            cur = parent_map.get(cur)
        return '/'.join(reversed(parts))

    # 4) Tutti gli ncTool
    nctool_list = list(root.iter('ncTool'))

    stats = {
        'utensili_trovati': len(tools_by_name),
        'utensili_importati': 0,
        'nctools_importati': 0,
        'condizioni_importate': 0,
        'holders_importati': 0,
        'errori': [],
    }

    if dry_run:
        print(f"Trovati: {len(tools_by_name)} tool, {len(nctool_list)} ncTool, {len(holders_by_name)} holder")
        print(f"Tecset totali: {len(list(root.iter('tecset')))}")
        count = 0
        for nct in nctool_list[:5]:
            alias = nct.get('name', '?')
            fp = _float(_param(nct, 'clearanceLength'))
            gl = _float(_param(nct, 'gageLength'))
            k_vc = _param(nct, 'spindleSpeedFactor', '1')
            k_fz = _param(nct, 'feedrateFactor', '1')
            tool_name = holder_name = None
            for comp in nct.iter('component'):
                ct = comp.get('type', '')
                if ct == 'tool':
                    tool_name = comp.get('name', '')
                elif ct == 'holder':
                    holder_name = comp.get('name', '')
            tool_el = tools_by_name.get(tool_name)
            if tool_el is None:
                continue
            d = _float(_param(tool_el, 'toolDiameter'))
            cr = _float(_param(tool_el, 'cornerRadius'))
            z = _int(_param(tool_el, 'cuttingEdges'))
            l_tot = _float(_param(tool_el, 'toolTotalLength'))
            l_tagl = _float(_param(tool_el, 'cuttingLength'))
            stelo = _float(_param(tool_el, 'toolShaftDiameter'))
            catalogo = _param(tool_el, 'orderingCode', '—')
            fornitore_v = _param(tool_el, 'manufacturer', '—')
            mat_tagl = _param(tool_el, 'cuttingMaterial', '—')
            ttype = TIPO_MAP.get(tool_el.get('type', ''), 'UNKNOWN')
            tecsets_validi = [ts for ts in tool_el.iter('tecset') if _param(ts, 'material')]
            count += 1
            print(f"\n--- ncTool #{count}: {alias} ---")
            print(f"  Tool: {tool_name}")
            print(f"    tipo={ttype}  D={d}  R={cr}  Z={z}")
            print(f"    L_tot={l_tot}  L_tagl={l_tagl}  stelo={stelo}")
            print(f"    catalogo={catalogo}  fornitore={fornitore_v}  mat_tagl={mat_tagl}")
            print(f"  NCTool: fuori_pinza={fp}  gage={gl}  k_vc={k_vc}  k_fz={k_fz}")
            print(f"  Holder: {holder_name or '(nessuno)'}")
            print(f"  Tecset: {len(tecsets_validi)} condizioni valide (con materiale)")
            for ts in tecsets_validi[:3]:
                mat = _param(ts, 'material')
                purp = _param(ts, 'purpose', '—')
                vc = _param(ts, 'cuttingSpeed', '0')
                fz = _param(ts, 'feedratePerEdge', '0')
                rpm = _param(ts, 'spindleSpeed', '0')
                feed = _param(ts, 'planeFeedrate', '0')
                ae = _param(ts, 'cuttingWidth', '0')
                ap = _param(ts, 'cuttingLength', '0')
                print(f"    [{mat}] {purp}: Vc={vc} fz={fz} rpm={rpm} F={feed} ae={ae} ap={ap}")
            # Campi mancanti
            missing = []
            if z is None: missing.append('cuttingEdges')
            if l_tot is None: missing.append('toolTotalLength')
            if stelo is None: missing.append('toolShaftDiameter')
            if catalogo == '—': missing.append('orderingCode')
            if missing:
                print(f"  WARN: campi mancanti: {', '.join(missing)}")
        stats['nctools_importati'] = len(nctool_list)
        stats['condizioni_importate'] = len(list(root.iter('tecset')))
        return stats

    # --- IMPORT REALE ---
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_columns(conn)
    id_mat_default = _get_materiale_id(conn)

    # A) Importa holders
    for h_name, h_el in holders_by_name.items():
        cod = _param(h_el, 'orderingCode', h_name)
        existing = conn.execute("SELECT id FROM portautensile WHERE codice_interno=?", (h_name,)).fetchone()
        if existing:
            continue
        try:
            conn.execute("""INSERT INTO portautensile (codice_interno, descrizione, cam_sorgente, id_originale_cam)
                VALUES (?,?,?,?)""", (h_name, cod, 'HyperMill', _param(h_el, 'objGuid')))
            stats['holders_importati'] += 1
        except Exception as e:
            stats['errori'].append(f"holder {h_name}: {e}")

    # B) Per ogni ncTool: trova tool collegato, inserisci utensile + condizioni
    tool_ids = {}  # tool_name → utensile.id nel DB

    for nct in nctool_list:
        alias = nct.get('name', '')
        if not alias:
            continue

        # Trova componenti
        tool_name = holder_name = None
        for comp in nct.iter('component'):
            ctype = comp.get('type', '')
            if ctype == 'tool':
                tool_name = comp.get('name', '')
            elif ctype == 'holder':
                holder_name = comp.get('name', '')

        tool_el = tools_by_name.get(tool_name)
        if tool_el is None:
            continue

        folder_path = _folder_path(nct)

        # Dati tool (geometria)
        ttype_xml = tool_el.get('type', '')
        tipo_codice = TIPO_MAP.get(ttype_xml, _tipo_from_folder(folder_path))
        id_tipo = _get_tipo_id(conn, tipo_codice)

        diametro = _float(_param(tool_el, 'toolDiameter'))
        raggio = _float(_param(tool_el, 'cornerRadius'))
        if raggio is None and tipo_codice == 'BALL' and diametro:
            raggio = round(diametro / 2, 3)
        taglienti = _int(_param(tool_el, 'cuttingEdges'))
        l_tot = _float(_param(tool_el, 'toolTotalLength'))
        l_tagl = _float(_param(tool_el, 'cuttingLength'))
        diam_stelo = _float(_param(tool_el, 'toolShaftDiameter'))
        cod_catalogo = _param(tool_el, 'orderingCode')
        fornitore = _param(tool_el, 'manufacturer')
        mat_tagl = _param(tool_el, 'cuttingMaterial')
        tool_guid = _param(tool_el, 'objGuid', alias)

        # Dati ncTool (assemblaggio)
        fuori_pinza = _float(_param(nct, 'clearanceLength'))
        gage_length = _float(_param(nct, 'gageLength'))
        k_vc = _float(_param(nct, 'spindleSpeedFactor'), 1.0)
        k_fz = _float(_param(nct, 'feedrateFactor'), 1.0)
        nctool_guid = _param(nct, 'objGuid', '')

        # Codice interno = alias ncTool (unico per assemblaggio)
        codice_interno = alias

        # Inserisci/aggiorna utensile
        existing = conn.execute("SELECT id FROM utensile WHERE codice_interno=?", (codice_interno,)).fetchone()
        if existing:
            uid = existing[0]
            conn.execute("""UPDATE utensile SET alias=?, id_tipo=?, id_materiale=?,
                diametro_mm=?, raggio_punta_mm=?, num_taglienti=?,
                lunghezza_totale_mm=?, lunghezza_tagl_mm=?, diam_stelo_mm=?,
                codice_catalogo=?, fuori_pinza_mm=?, gage_length_mm=?,
                fattore_s=?, fattore_f=?, nome_pinza=?,
                cam_sorgente=?, id_originale_cam=?, descrizione=?
                WHERE id=?""", (
                alias, id_tipo, id_mat_default,
                diametro or 0, raggio or 0, taglienti,
                l_tot or 0, l_tagl or 0, diam_stelo,
                cod_catalogo, fuori_pinza, gage_length,
                k_vc, k_fz, holder_name,
                'HyperMill', nctool_guid, tool_name, uid))
        else:
            cur = conn.execute("""INSERT INTO utensile (
                codice_interno, alias, id_tipo, id_materiale,
                diametro_mm, raggio_punta_mm, num_taglienti,
                lunghezza_totale_mm, lunghezza_tagl_mm, diam_stelo_mm,
                codice_catalogo, fuori_pinza_mm, gage_length_mm,
                fattore_s, fattore_f, nome_pinza,
                cam_sorgente, id_originale_cam, descrizione, stato)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                codice_interno, alias, id_tipo, id_mat_default,
                diametro or 0, raggio or 0, taglienti,
                l_tot or 0, l_tagl or 0, diam_stelo,
                cod_catalogo, fuori_pinza, gage_length,
                k_vc, k_fz, holder_name,
                'HyperMill', nctool_guid, tool_name, 'staging'))
            uid = cur.lastrowid
            stats['utensili_importati'] += 1

        stats['nctools_importati'] += 1

        # C) Importa condizioni di taglio (tecset del tool collegato)
        for ts in tool_el.iter('tecset'):
            materiale = _param(ts, 'material')
            if not materiale:
                continue
            purpose = _param(ts, 'purpose', '')
            vc = _float(_param(ts, 'cuttingSpeed'))
            if not vc:
                continue  # skip tecset vuoti/template
            fz = _float(_param(ts, 'feedratePerEdge'))
            avanzamento = _float(_param(ts, 'planeFeedrate'))
            rpm = _float(_param(ts, 'spindleSpeed'))
            ae = _float(_param(ts, 'cuttingWidth'))
            ap = _float(_param(ts, 'cuttingLength'))

            try:
                conn.execute("""INSERT OR REPLACE INTO condizioni_taglio
                    (id_utensile, materiale_pezzo, applicazione, cam_sorgente,
                     vc_m_min, rotazione_rpm, fz_mm_z, avanzamento_mm_min, ae_mm, ap_mm)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                    uid, materiale, purpose, 'HyperMill',
                    vc, rpm, fz, avanzamento, ae, ap))
                stats['condizioni_importate'] += 1
            except Exception as e:
                stats['errori'].append(f"tecset {codice_interno}/{materiale}/{purpose}: {e}")

    conn.commit()
    conn.close()

    print(f"Import HyperMill XML: {stats['utensili_importati']} utensili, "
          f"{stats['nctools_importati']} nctools, "
          f"{stats['condizioni_importate']} condizioni, "
          f"{stats['holders_importati']} holders, "
          f"{len(stats['errori'])} errori")
    return stats


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Import HyperMill XML')
    parser.add_argument('filepath', help='Path al file .xml HyperMill')
    parser.add_argument('db_path', nargs='?',
                        default=os.path.join(_BASE, 'database', 'tool_master.db'),
                        help='Path al DB SQLite')
    parser.add_argument('--dry-run', action='store_true', help='Mostra dati senza scrivere')
    args = parser.parse_args()

    if not os.path.exists(args.filepath):
        print(f"File non trovato: {args.filepath}", file=sys.stderr)
        sys.exit(1)

    result = import_xml(args.filepath, args.db_path, dry_run=args.dry_run)
    if args.dry_run:
        print(f"\nRiepilogo dry-run: {result}")
