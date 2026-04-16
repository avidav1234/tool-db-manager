import xml.etree.ElementTree as ET
import sqlite3
import os

def parse_xml_to_dict(filepath: str):
    """Parses the XML and returns a list of dictionaries with extracted tool data."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except FileNotFoundError:
        return {"error": f"File non trovato: {filepath}"}
    except ET.ParseError as e:
        return {"error": f"XML malformato: {str(e)}"}

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

    type_map = {
        'radiusMill': 'BULL',
        'flatMill': 'FLAT',
        'ballMill': 'BALL',
        'chamferMill': 'CHAMFER',
        'drill': 'DRILL',
        'tap': 'TAP',
        'reamer': 'REAM'
    }

    tools_data = []

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
    result = {"righe_processate": 0, "inserite": 0, "errori": []}

    parsed = parse_xml_to_dict(filepath)
    if "error" in parsed:
        result["errori"].append(parsed["error"])
        return result

    tools = parsed.get("tools", [])
    result["righe_processate"] = len(tools)

    if not tools:
        result["errori"].append("Nessun utensile (ncTool) trovato nel file XML.")
        return result

    if dry_run:
        print(f"[DRY RUN] Trovati {len(tools)} utensili. Stampo i primi 10:")
        for t in tools[:10]:
            print(f"  - {t['codice_interno']} (Alias: {t['alias']}, Diam: {t['diametro_mm']}, Tipo: {t['tipo']}, L: {t['fuori_pinza_mm']})")
        return result

    # Database connection
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()


        for t in tools:
            # We skip if no codice_interno
            if not t['codice_interno']:
                continue

            cursor.execute("""
                INSERT OR IGNORE INTO Utensili
                (codice_interno, alias, diametro_mm, fuori_pinza_mm, tipo, cam_sorgente)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                t['codice_interno'],
                t['alias'],
                t['diametro_mm'],
                t['fuori_pinza_mm'],
                t['tipo'],
                t['cam_sorgente']
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
    parser = argparse.ArgumentParser(description='Importa utensili da HyperMill XML a SQLite.')
    parser.add_argument('filepath', help='Percorso del file XML (.omtdx)')
    parser.add_argument('db_path', help='Percorso del database SQLite')
    parser.add_argument('--dry-run', action='store_true', help='Esegue un test senza scrivere nel DB')

    args = parser.parse_args()

    res = import_xml(args.filepath, args.db_path, args.dry_run)
    print(res)
