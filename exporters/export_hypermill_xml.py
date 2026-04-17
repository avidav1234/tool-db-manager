import xml.etree.ElementTree as ET
from xml.dom import minidom
import sqlite3
import os
import json
import uuid

def load_profile(profile_path="learner/profiles/hypermill_omtdx_v34.json"):
    if not os.path.exists(profile_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        profile_path = os.path.join(base_dir, "learner", "profiles", "hypermill_omtdx_v34.json")

    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Errore caricamento profilo: {e}")
        return None

def get_utensili_da_esportare(db_path):
    utensili = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Read all tools (assumes filtering could be applied via WHERE if 'stato' was explicitly managed,
        # but for now we get all or active ones, here we just get all for simplicity as per standard DB)

        # In this specific context we need to match the type back as a string, let's join
        query = """
        SELECT u.*, tu.codice as tipo_str
        FROM utensile u
        LEFT JOIN tipo_utensile tu ON u.id_tipo = tu.id
        WHERE u.attivo = 1
        """
        cursor.execute(query)
        utensili = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Errore lettura DB: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

    return utensili

def utensile_to_nctool_xml(utensile, profile, parent_node):
    """
    Crea un nodo ncTools foglia per l'utensile.
    """
    tool_guid = str(uuid.uuid4())

    nctool = ET.SubElement(parent_node, 'ncTools', {
        'folder': utensile.get('alias') or utensile.get('codice_interno') or 'Sconosciuto',
        'objGuid': tool_guid
    })

    # Reverse mapping for param_mapping
    # A db_field might map to multiple XML params (like "Diameter" and "toolDiameter").
    # We output the primary ones found in param_mapping.

    # Per semplicità, e per evitare duplicati, estraiamo chiavi uniche da param_mapping
    # dove il tipo db coincide.

    handled_fields = set()
    for xml_param, map_info in profile.get('param_mapping', {}).items():
        db_field = map_info['campo_master']
        val_type = map_info['tipo']

        if db_field in handled_fields:
            continue

        if db_field == 'tipo':
            # Handle type specially
            tipo_db = utensile.get('tipo_str', 'UNKNOWN')
            xml_type = next((k for k, v in profile.get('tipo_mapping', {}).items() if v == tipo_db), 'unknown')
            ET.SubElement(nctool, 'param', {'name': xml_param, 'value': xml_type})
            handled_fields.add(db_field)
            continue

        if db_field in utensile and utensile[db_field] is not None:
            val = utensile[db_field]
            if val_type == 'float':
                val_str = f"{float(val):.3f}"
            else:
                val_str = str(val)

            ET.SubElement(nctool, 'param', {'name': xml_param, 'value': val_str})
            handled_fields.add(db_field)

def export_xml(db_path, output_path, dry_run=False) -> dict:
    result = {"utensili_esportati": 0, "errori": []}

    profile = load_profile()
    if not profile:
        result["errori"].append("Profilo mancante")
        return result

    utensili = get_utensili_da_esportare(db_path)

    if not utensili:
        result["errori"].append("Nessun utensile da esportare")
        return result

    if dry_run:
        result["utensili_esportati"] = len(utensili)
        print(f"[DRY RUN] Pronti per esportare {len(utensili)} utensili in {output_path}")
        return result

    # Costruisci XML radice
    root = ET.Element('omtdx', {
        'version': profile.get('versione', '34'),
        'srcURL': f'sqlite://{os.path.abspath(db_path)}'
    })

    # Strutturiamo per tipo
    tipi_folders = {}
    main_nctools = ET.SubElement(root, 'ncTools')

    for ut in utensili:
        tipo = ut.get('tipo_str', 'UNKNOWN')

        if tipo not in tipi_folders:
            tipi_folders[tipo] = ET.SubElement(main_nctools, 'ncTools', {
                'folder': f"Utensili {tipo}",
                'objGuid': str(uuid.uuid4())
            })

        utensile_to_nctool_xml(ut, profile, tipi_folders[tipo])
        result["utensili_esportati"] += 1

    # Scrivi il file ben formattato
    try:
        xml_str = ET.tostring(root, encoding='utf-8')
        parsed_xml = minidom.parseString(xml_str)
        pretty_xml = parsed_xml.toprettyxml(indent="  ")

        # Elimina le righe vuote generate da minidom in alcuni casi
        pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip()])

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            f.write(pretty_xml[pretty_xml.find('\n')+1:]) # Skip the minidom XML declaration

    except Exception as e:
        result["errori"].append(f"Errore salvataggio: {e}")

    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Esporta utensili verso HyperMill XML (omtdx v34).')
    parser.add_argument('db_path', help='Percorso del database SQLite')
    parser.add_argument('output_path', help='Percorso del file XML da generare')
    parser.add_argument('--dry-run', action='store_true', help='Esegue un test senza scrivere su disco')

    args = parser.parse_args()

    res = export_xml(args.db_path, args.output_path, args.dry_run)
    print(res)
