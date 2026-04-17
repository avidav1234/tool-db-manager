import xml.etree.ElementTree as ET
import sqlite3
import os
import json

def load_profile(profile_path="learner/profiles/hypermill_omtdx_v34.json"):
    if not os.path.exists(profile_path):
        # Fallback se avviato da altre directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        profile_path = os.path.join(base_dir, "learner", "profiles", "hypermill_omtdx_v34.json")

    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Errore caricamento profilo: {e}")
        return None

def apply_type_fallback(path_string, profile):
    path_lower = path_string.lower()
    for fallback in profile.get('tipo_da_percorso', []):
        if fallback['keyword'].lower() in path_lower:
            return fallback['tipo']
    return 'UNKNOWN'

def parse_nctools_recursive(node, current_path, profile, tools_data):
    """
    Traverse recursively the <ncTools> elements.
    If a node has no <ncTools> children, it is considered a leaf (an actual tool).
    """
    children_nctools = node.findall('ncTools')

    # Se ha figli <ncTools>, esploriamo e aggiorniamo il path
    if children_nctools:
        folder_name = node.get('folder', '')
        new_path = current_path
        if folder_name:
            new_path = f"{current_path}/{folder_name}" if current_path else folder_name

        for child in children_nctools:
            parse_nctools_recursive(child, new_path, profile, tools_data)
    else:
        # È una foglia, elaboriamo l'utensile
        tool_dict = {}
        tool_dict['codice_interno'] = node.get('objGuid', '')
        tool_dict['alias'] = node.get('folder', '')
        tool_dict['cam_sorgente'] = 'HyperMill'

        # Default initialization based on mapping
        for json_key, map_info in profile.get('param_mapping', {}).items():
            db_field = map_info['campo_master']
            if map_info['tipo'] in ['float', 'int'] and db_field not in tool_dict:
                tool_dict[db_field] = 0.0 if map_info['tipo'] == 'float' else 0
            elif map_info['tipo'] == 'string' and db_field not in tool_dict:
                tool_dict[db_field] = ''

        # Parse params
        for param in node.findall('param'):
            name = param.get('name')
            val = param.get('value')

            if not name or val is None:
                continue

            if name in profile.get('param_mapping', {}):
                map_info = profile['param_mapping'][name]
                db_field = map_info['campo_master']
                val_type = map_info['tipo']

                try:
                    if val_type == 'float':
                        tool_dict[db_field] = float(val)
                    elif val_type == 'int':
                        tool_dict[db_field] = int(float(val)) # float conversion first to handle '4.0'
                    else:
                        tool_dict[db_field] = val
                except ValueError:
                    pass

        # Determine Type
        tipo_str = tool_dict.get('tipo', '')
        if tipo_str in profile.get('tipo_mapping', {}):
            tool_dict['tipo'] = profile['tipo_mapping'][tipo_str]
        elif not tipo_str or tipo_str == 'UNKNOWN':
            # Use fallback from path
            tool_dict['tipo'] = apply_type_fallback(current_path + "/" + tool_dict['alias'], profile)
        else:
            tool_dict['tipo'] = tipo_str.upper()

        tools_data.append(tool_dict)


def parse_xml_to_dict(filepath: str, profile: dict):
    """Parses the XML and returns a list of dictionaries with extracted tool data."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except FileNotFoundError:
        return {"error": f"File non trovato: {filepath}"}
    except ET.ParseError as e:
        return {"error": f"XML malformato: {str(e)}"}

    tools_data = []

    # Trova il nodo radice <ncTools> o itera su tutti
    for top_nctools in root.findall('ncTools'):
        parse_nctools_recursive(top_nctools, "", profile, tools_data)

    # Compatibilità all'indietro: se ci sono <ncTool> nel vecchio formato (non strutturati sotto <ncTools>)
    # gestiamoli, altrimenti restituiamo
    if not tools_data:
        # Codice legacy per <ncTool> (non ricorsivo)
        tools_def = {}
        for t in root.findall('.//tool'):
            name = t.get('name')
            if name:
                d = 0.0
                for p in t.findall('param'):
                    if p.get('name') in ['toolDiameter', 'Diameter']:
                        try:
                            d = float(p.get('value'))
                        except ValueError:
                            pass
                tools_def[name] = {'type': t.get('type', 'UNKNOWN'), 'diam': d}

        type_map = profile.get('tipo_mapping', {
            'radiusMill': 'BULL',
            'flatMill': 'FLAT',
            'ballMill': 'BALL',
            'chamferMill': 'CHAMFER',
            'drill': 'DRILL',
            'tap': 'TAP',
            'reamer': 'REAM'
        })

        for nctool in root.findall('.//ncTool'):
            tool_dict = {}

            tool_dict['codice_interno'] = nctool.get('id', '')
            tool_dict['alias'] = nctool.get('name', '')

            tool_dict['diametro_mm'] = 0.0
            tool_dict['fuori_pinza_mm'] = 0.0
            tool_dict['tipo'] = 'UNKNOWN'
            tool_dict['cam_sorgente'] = 'HyperMill'

            for param in nctool.findall('.//param'):
                name = param.get('name', '')
                val = param.get('value', '0')

                if name in ('clearanceLength', 'Length', 'OverallLength', 'FluteLenght'):
                    try:
                        tool_dict['fuori_pinza_mm'] = float(val)
                    except ValueError:
                        pass

            tool_comp = nctool.find('.//component[@type="tool"]')
            if tool_comp is not None:
                t_name = tool_comp.get('name')
                if t_name and t_name in tools_def:
                    t_def = tools_def[t_name]
                    tool_dict['diametro_mm'] = round(t_def['diam'], 3)
                    xml_type = t_def['type']
                    tool_dict['tipo'] = type_map.get(xml_type, xml_type.upper())

            if tool_dict['diametro_mm'] == 0.0:
                for param in nctool.findall('.//param'):
                    if param.get('name') in ('toolDiameter', 'Diameter'):
                        try:
                            tool_dict['diametro_mm'] = round(float(param.get('value')), 3)
                        except ValueError:
                            pass

            tools_data.append(tool_dict)

    return {"tools": tools_data}


def import_xml(filepath: str, db_path: str, dry_run: bool = False) -> dict:
    """
    Main entry point for importing an XML into the DB.
    Reads the v34 profile, parses the XML, and inserts tools.
    """
    result = {"righe_processate": 0, "inserite": 0, "errori": []}

    profile = load_profile()
    if not profile:
        result["errori"].append("Impossibile caricare il profilo v34. Esecuzione annullata.")
        return result

    parsed = parse_xml_to_dict(filepath, profile)
    if "error" in parsed:
        result["errori"].append(parsed["error"])
        return result

    tools = parsed.get("tools", [])
    result["righe_processate"] = len(tools)

    if not tools:
        result["errori"].append("Nessun utensile trovato nel file XML.")
        return result

    if dry_run:
        print(f"[DRY RUN] Trovati {len(tools)} utensili. Stampo i primi 10:")
        for t in tools[:10]:
            print(f"  - {t.get('codice_interno', '')} (Alias: {t.get('alias', '')}, Diam: {t.get('diametro_mm', 0)}, Tipo: {t.get('tipo', '')}, L: {t.get('fuori_pinza_mm', 0)})")
        return result

    # Database connection
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for t in tools:
            # We skip if no codice_interno
            if not t.get('codice_interno'):
                continue

            # Need to get id_tipo from tipo string
            cursor.execute("SELECT id FROM tipo_utensile WHERE codice = ?", (t.get('tipo', 'UNKNOWN'),))
            row = cursor.fetchone()
            id_tipo = row[0] if row else 1  # Default to UNKNOWN id or 1

            cursor.execute("""
                INSERT OR IGNORE INTO utensile
                (codice_interno, alias, diametro_mm, fuori_pinza_mm, id_tipo, cam_sorgente)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                t.get('codice_interno', ''),
                t.get('alias', ''),
                t.get('diametro_mm', 0.0),
                t.get('fuori_pinza_mm', 0.0),
                id_tipo,
                t.get('cam_sorgente', 'HyperMill')
            ))
            if cursor.rowcount > 0:
                result["inserite"] += 1

        conn.commit()

    except Exception as e:
        result["errori"].append(f"Errore DB: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Importa utensili da HyperMill XML (omtdx v34) a SQLite usando profilo.')
    parser.add_argument('filepath', help='Percorso del file XML (.omtdx)')
    parser.add_argument('db_path', help='Percorso del database SQLite')
    parser.add_argument('--dry-run', action='store_true', help='Esegue un test senza scrivere nel DB')

    args = parser.parse_args()

    res = import_xml(args.filepath, args.db_path, args.dry_run)
    print(res)
