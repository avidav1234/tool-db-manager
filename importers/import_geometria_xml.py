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
        # Raccogli cont2D dai blocchi geometry
        geos = list(tool_el.iter('geometry'))
        for gi, geo in enumerate(geos):
            for cont in geo:
                ct = cont.tag.split('}')[-1] if '}' in cont.tag else cont.tag
                if ct != 'cont2D':
                    continue
                elements = _parse_cont2d(cont)
                if not elements:
                    continue
                # Determina tipo: se ha cuttingArea=1 -> area_taglio, altrimenti ordine
                has_cutting = any(e.get('cuttingArea') for e in elements)
                if has_cutting:
                    tipo = 'area_taglio'
                elif gi == 0:
                    tipo = 'profilo_esterno'
                else:
                    tipo = 'gambo'
                geo_json = json.dumps(elements, ensure_ascii=False)
                conn.execute("INSERT INTO geometria_fresa (utensile_id, tipo, elementi_json) VALUES (?,?,?)",
                             (uid, tipo, geo_json))
                stats['tools_geo'] += 1

    conn.commit()
    conn.close()

    print(f"Geometria importata: {stats['holders_geo']} holders, {stats['tools_geo']} profili fresa")
    if stats['errori']:
        print(f"Errori: {len(stats['errori'])}")
        for e in stats['errori'][:5]:
            print(f"  {e}")
    return stats


if __name__ == '__main__':
    fp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_BASE, 'db esempi', 'Dino Series.xml')
    db = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_BASE, 'database', 'tool_master.db')
    if not os.path.exists(fp):
        print(f"File non trovato: {fp}", file=sys.stderr)
        sys.exit(1)
    import_geometria(fp, db)
