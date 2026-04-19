#!/usr/bin/env python3
"""
import_geometria_xml.py — Estrai geometria cont2D da XML HyperMill (OMTDX v34)

Salva:
  - portautensile.geometria_json, lunghezza_totale_mm, diametro_attacco_mm
  - geometria_fresa: profilo_esterno + area_taglio per ogni tool
"""
import xml.etree.ElementTree as ET
import sqlite3
import json
import os
import sys

_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def _estrai_gola(elementi):
    """Analizza il profilo cont2D e trova la gola (neck).

    La gola e' la zona tra la fine del corpo tagliente e l'inizio del gambo
    dove il raggio e' minimo e stabile.

    Ritorna: (d_gola_mm, h_gola_mm) oppure (None, None) se non trovata.
    """
    if not elementi or len(elementi) < 4:
        return None, None

    punti = []
    for e in elementi:
        r = e.get('ex', e.get('sx'))
        z = e.get('ey', e.get('sy'))
        if r is not None and z is not None:
            punti.append((float(r), float(z)))

    if len(punti) < 4:
        return None, None

    r_max = max(r for r, z in punti)
    positive_r = [r for r, z in punti if r > 0]
    if not positive_r:
        return None, None
    r_min = min(positive_r)

    # Se r_min molto vicino a r_max -> nessuna gola significativa
    if r_max - r_min < r_max * 0.1:
        return None, None

    # Trova zona a raggio minimo (< 80% del raggio max)
    r_gola_candidates = [(r, z) for r, z in punti if 0 < r < r_max * 0.8]
    if not r_gola_candidates:
        return None, None

    r_gola = min(r for r, z in r_gola_candidates)
    z_gola_punti = [z for r, z in r_gola_candidates if abs(r - r_gola) < 0.5]

    if len(z_gola_punti) < 2:
        return None, None

    h_gola = max(z_gola_punti) - min(z_gola_punti)
    d_gola = r_gola * 2

    if h_gola < 0.5:
        return None, None

    return round(d_gola, 3), round(h_gola, 3)


def _parse_cont2d(cont_el):
    """Converte un <cont2D> in lista di dict con tutti gli attributi elem2D."""
    elements = []
    last_ex, last_ey = None, None
    for e in cont_el:
        tag = e.tag.split('}')[-1] if '}' in e.tag else e.tag
        if tag != 'elem2D':
            continue
        elem = {'type': e.get('type', 'line')}
        # Coordinate start: usa attributo se presente, altrimenti punto precedente
        if e.get('sx') is not None:
            elem['sx'] = float(e.get('sx'))
            elem['sy'] = float(e.get('sy', '0'))
        elif last_ex is not None:
            elem['sx'] = last_ex
            elem['sy'] = last_ey
        # Coordinate end (sempre presenti)
        elem['ex'] = float(e.get('ex', '0'))
        elem['ey'] = float(e.get('ey', '0'))
        # Centro arco (per cwarc/ccwarc)
        if e.get('cx') is not None:
            elem['cx'] = float(e.get('cx'))
            elem['cy'] = float(e.get('cy', '0'))
        # Flag area di taglio
        if e.get('cuttingArea'):
            elem['cuttingArea'] = int(e.get('cuttingArea'))
        last_ex = elem['ex']
        last_ey = elem['ey']
        elements.append(elem)
    return elements


def import_geometria(filepath, db_path):
    """Importa geometria cont2D dal file XML nel DB."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    stats = {'holders_geo': 0, 'tools_geo': 0, 'errori': []}

    # --- HOLDER ---
    for h_el in root.iter('holder'):
        h_name = h_el.get('name', '')
        if not h_name:
            continue
        # Trova cont2D nella geometry
        elements = []
        for geo in h_el.iter('geometry'):
            for cont in geo:
                ct = cont.tag.split('}')[-1] if '}' in cont.tag else cont.tag
                if ct == 'cont2D':
                    elements = _parse_cont2d(cont)
                    break
            if elements:
                break
        if not elements:
            continue
        # Calcola lunghezza e diametro
        max_y = max((e.get('ey', 0) for e in elements), default=0)
        max_x = max((max(e.get('ex', 0), e.get('sx', 0)) for e in elements), default=0)
        geo_json = json.dumps(elements, ensure_ascii=False)
        # Aggiorna portautensile
        existing = conn.execute("SELECT id FROM portautensile WHERE codice_interno=?", (h_name,)).fetchone()
        if existing:
            conn.execute("""UPDATE portautensile SET geometria_json=?, lunghezza_totale_mm=?,
                diametro_attacco_mm=? WHERE id=?""", (geo_json, round(max_y, 6), round(max_x * 2, 6), existing[0]))
            stats['holders_geo'] += 1
        else:
            stats['errori'].append(f"holder '{h_name}' non trovato in portautensile")

    # --- TOOL ---
    for tool_el in root.iter('tool'):
        tool_name = tool_el.get('name', '')
        if not tool_name:
            continue
        # Trova utensile_id: cerca per descrizione (che contiene tool_name) o alias
        row = conn.execute("SELECT id FROM utensile WHERE descrizione=? OR alias=?",
                           (tool_name, tool_name)).fetchone()
        if not row:
            # Fallback: cerca parziale
            row = conn.execute("SELECT id FROM utensile WHERE descrizione LIKE ?",
                               (f'%{tool_name[:30]}%',)).fetchone()
        if not row:
            continue
        uid = row[0]
        # Elimina geometrie precedenti per questo utensile
        conn.execute("DELETE FROM geometria_fresa WHERE utensile_id=?", (uid,))
        # Mappa geometry.name → tipo DB
        GEO_NAME_MAP = {'freeShaft': 'profilo_gambo', 'freeTip': 'profilo_taglio'}
        # Raccogli cont2D dai blocchi geometry
        geos = list(tool_el.iter('geometry'))
        for gi, geo in enumerate(geos):
            geo_name = geo.get('name', '')
            for cont in geo:
                ct = cont.tag.split('}')[-1] if '}' in cont.tag else cont.tag
                if ct != 'cont2D':
                    continue
                elements = _parse_cont2d(cont)
                if not elements:
                    continue
                # Determina tipo da geometry.name o dal contenuto
                if geo_name in GEO_NAME_MAP:
                    tipo = GEO_NAME_MAP[geo_name]
                elif any(e.get('cuttingArea') for e in elements):
                    tipo = 'area_taglio'
                elif gi == 0:
                    tipo = 'profilo_esterno'
                else:
                    tipo = 'gambo'
                geo_json = json.dumps(elements, ensure_ascii=False)
                conn.execute("INSERT INTO geometria_fresa (utensile_id, tipo, elementi_json) VALUES (?,?,?)",
                             (uid, tipo, geo_json))
                stats['tools_geo'] += 1
                # Estrai gola dal profilo esterno — solo se coerente
                if tipo == 'profilo_esterno':
                    d_gola, h_gola = _estrai_gola(elements)
                    if d_gola is not None:
                        # Verifica coerenza: d_gola deve essere > diam_stelo
                        u_row = conn.execute("SELECT diam_stelo_mm, d_gola_mm FROM utensile WHERE id=?", (uid,)).fetchone()
                        d_stelo = u_row[0] if u_row else None
                        existing_gola = u_row[1] if u_row else None
                        # Non sovrascrivere se scalare gia presente (piu affidabile)
                        if existing_gola is not None:
                            d_gola = None  # scalare ha priorita
                        elif d_stelo and d_gola < d_stelo:
                            d_gola = None  # artefatto cont2D
                    if d_gola is not None:
                        conn.execute("UPDATE utensile SET d_gola_mm=?, h_gola_mm=? WHERE id=?",
                                     (d_gola, h_gola, uid))

    # --- EXTENSION (prolunghe) ---
    n_ext = 0
    conn.execute("""CREATE TABLE IF NOT EXISTS geometria_extension (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE NOT NULL,
        lunghezza_mm REAL, diametro_max_mm REAL, diametro_min_mm REAL,
        lunghezza_scarico_mm REAL, elementi_json TEXT)""")
    for ext_el in root.iter('extension'):
        ext_name = ext_el.get('name', '').strip()
        if not ext_name:
            continue
        cont2d = ext_el.find('.//cont2D')
        if cont2d is None:
            continue
        elementi = _parse_cont2d(cont2d)
        if not elementi:
            continue
        rs = [float(e.get('ex', e.get('sx', 0))) for e in elementi]
        zs = [float(e.get('ey', e.get('sy', 0))) for e in elementi]
        rs_pos = [r for r in rs if r > 0.01]
        d_max = max(rs_pos) * 2 if rs_pos else 0
        d_min = min(rs_pos) * 2 if rs_pos else 0
        lung = max(zs) - min(zs) if zs else 0
        # Lunghezza scarico: z dove r passa da min a max
        lung_scarico = 0
        if len(elementi) >= 2 and d_max > d_min:
            r_soglia = (d_min / 2 + d_max / 2) / 2
            for e in elementi:
                r = float(e.get('ex', 0))
                z = float(e.get('ey', 0))
                if r > r_soglia:
                    lung_scarico = z
                    break
        try:
            conn.execute("""INSERT OR REPLACE INTO geometria_extension
                (nome, lunghezza_mm, diametro_max_mm, diametro_min_mm,
                 lunghezza_scarico_mm, elementi_json)
                VALUES (?,?,?,?,?,?)""",
                (ext_name, round(lung, 3), round(d_max, 3), round(d_min, 3),
                 round(lung_scarico, 3), json.dumps(elementi, ensure_ascii=False)))
            n_ext += 1
        except Exception as e:
            stats['errori'].append(f"extension {ext_name}: {e}")

    conn.commit()
    conn.close()

    print(f"Geometria importata: {stats['holders_geo']} holders, {stats['tools_geo']} profili fresa, {n_ext} extensions")
    if stats['errori']:
        print(f"Errori: {len(stats['errori'])}")
        for e in stats['errori'][:5]:
            print(f"  {e}")
    stats['extensions_geo'] = n_ext
    return stats


if __name__ == '__main__':
    fp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_BASE, 'db esempi', 'Dino Series.xml')
    db = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_BASE, 'database', 'tool_master.db')
    if not os.path.exists(fp):
        print(f"File non trovato: {fp}", file=sys.stderr)
        sys.exit(1)
    import_geometria(fp, db)
