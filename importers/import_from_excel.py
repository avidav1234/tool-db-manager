"""
import_from_excel.py
====================
Importa utensili nel DB master da file Excel o CSV generico.

Riconosce automaticamente:
  - File Cimatron (CSV UTF-16, XLS nativo, ZIP) -> usa cimatron_importer
  - Excel .xlsx / .xls generico
  - CSV UTF-8 / UTF-16 generico con colonne standard

Uso:
    python importers/import_from_excel.py --file utensili.xlsx
    python importers/import_from_excel.py --file Cimatron_2025.csv
    python importers/import_from_excel.py --file Cimatron_2025.zip
"""

import os
import sys
import sqlite3

_BASE    = os.path.join(os.path.dirname(__file__), '..')
_LEARNER = os.path.join(_BASE, 'learner')
sys.path.insert(0, _LEARNER)
sys.path.insert(0, _BASE)

DB_PATH = os.path.join(_BASE, 'database', 'tool_master.db')


def _is_cimatron(filepath: str) -> bool:
    """
    Rileva se il file e' un export Cimatron.

    Logica:
      - CSV/XLS con magic bytes UTF-16 (FF FE o FE FF) -> Cimatron
        (Cimatron e' l'unico CAM che esporta CSV in UTF-16 pipe-separato)
      - XLS con foglio 'Cutters' -> Cimatron
      - ZIP con file Cutters_*.csv -> Cimatron
      - CSV con contenuto CimatronE (legge fino a 2KB) -> Cimatron
    """
    ext = os.path.splitext(filepath)[1].lower()

    # Magic bytes UTF-16: FF FE (little-endian) o FE FF (big-endian)
    # Cimatron e' l'unico CAM mainstream che usa UTF-16 per i CSV
    try:
        with open(filepath, 'rb') as f:
            magic = f.read(2)
        if magic in (b'\xff\xfe', b'\xfe\xff'):
            return True
    except Exception:
        pass

    # XLS con foglio Cutters
    if ext == '.xls':
        try:
            import xlrd
            return 'Cutters' in xlrd.open_workbook(filepath).sheet_names()
        except Exception:
            pass

    # ZIP con Cutters_*.csv
    if ext == '.zip':
        try:
            import zipfile
            with zipfile.ZipFile(filepath) as z:
                return any('Cutters' in os.path.basename(n) and n.endswith('.csv')
                           for n in z.namelist())
        except Exception:
            pass

    # CSV: legge 2KB e cerca CimatronE
    if ext == '.csv':
        try:
            with open(filepath, 'rb') as f:
                raw = f.read(2048)
            for enc in ('utf-16', 'utf-8-sig', 'utf-8', 'latin-1'):
                try:
                    text = raw.decode(enc)
                    if 'CimatronE' in text or ('1101' in text and '//' in text and '|' in text):
                        return True
                    break
                except Exception:
                    continue
        except Exception:
            pass

    return False


def importa(filepath: str, dry_run: bool = False) -> dict:
    """
    Importa utensili da qualsiasi file supportato.

    Rileva automaticamente il formato:
      - Cimatron (CSV UTF-16, XLS, ZIP) -> cimatron_importer
      - Excel/CSV generico -> parser euristico

    Ritorna: { inseriti, aggiornati, errori, dry_run, versione }
    """
    if _is_cimatron(filepath):
        return _importa_cimatron(filepath, dry_run)
    return _importa_generico(filepath, dry_run)


def _importa_cimatron(filepath: str, dry_run: bool) -> dict:
    """Usa il cimatron_importer dedicato."""
    try:
        from cimatron_importer import importa_file
        r = importa_file(filepath, dry_run=dry_run)
        return {
            'inseriti':    r.get('utensili_inseriti', 0),
            'aggiornati':  r.get('utensili_aggiornati', 0),
            'errori':      r.get('utensili_errori', []),
            'dry_run':     dry_run,
            'versione':    r.get('versione', ''),
            'taglio_inserite':  r.get('taglio_inserite', 0),
            'taglio_aggiornate': r.get('taglio_aggiornate', 0),
        }
    except Exception as e:
        return {'inseriti': 0, 'aggiornati': 0, 'errori': [str(e)], 'dry_run': dry_run}


def _importa_generico(filepath: str, dry_run: bool) -> dict:
    """Parser generico per Excel/CSV con colonne standard."""
    import pandas as pd

    ext = os.path.splitext(filepath)[1].lower()

    # Leggi il file
    try:
        if ext in ('.xlsx',):
            df = pd.read_excel(filepath)
        elif ext in ('.xls',):
            df = pd.read_excel(filepath)
        elif ext == '.csv':
            # Prova vari encoding
            df = None
            for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
                try:
                    df = pd.read_csv(filepath, encoding=enc, sep=None, engine='python')
                    break
                except Exception:
                    continue
            if df is None:
                raise ValueError("Impossibile leggere il CSV - encoding non riconosciuto")
        else:
            raise ValueError(f"Formato non supportato: {ext}")
    except Exception as e:
        return {'inseriti': 0, 'aggiornati': 0, 'errori': [f"Lettura file: {e}"], 'dry_run': dry_run}

    # Normalizza nomi colonne
    df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

    # Mappatura nomi colonne standard
    ALIAS = {
        'codice':           'codice_interno',
        'nome':             'codice_interno',
        'name':             'codice_interno',
        'tool_name':        'codice_interno',
        'catalog':          'codice_catalogo',
        'type':             'tipo',
        'diameter':         'diametro_mm',
        'diam':             'diametro_mm',
        'corner_radius':    'raggio_punta_mm',
        'overall_length':   'lunghezza_totale_mm',
        'flute_length':     'lunghezza_tagl_mm',
        'cutting_length':   'lunghezza_tagl_mm',
        'num_flutes':       'num_taglienti',
        'flutes':           'num_taglienti',
    }
    for alias, campo in ALIAS.items():
        if alias in df.columns and campo not in df.columns:
            df.rename(columns={alias: campo}, inplace=True)

    # Verifica colonne obbligatorie
    if 'codice_interno' not in df.columns:
        return {
            'inseriti': 0, 'aggiornati': 0, 'dry_run': dry_run,
            'errori': [
                "Colonna 'codice_interno' non trovata nel file.\n"
                f"Colonne disponibili: {list(df.columns)}\n"
                "Rinomina la colonna con il codice utensile in 'codice_interno'."
            ]
        }

    # Scrivi nel DB
    inseriti = aggiornati = 0
    errori = []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Valori di default per lookup
        tipo_default = conn.execute(
            "SELECT id FROM tipo_utensile WHERE codice='FLAT'"
        ).fetchone()
        mat_default  = conn.execute(
            "SELECT id FROM materiale_utensile WHERE codice='HM'"
        ).fetchone()

        if not tipo_default or not mat_default:
            raise ValueError("DB non inizializzato - esegui prima: python ui/app.py")

        tipo_id_default = tipo_default['id']
        mat_id_default  = mat_default['id']

        TIPO_MAP = {
            'flat':'FLAT','piatta':'FLAT','mill':'FLAT',
            'ball':'BALL','sferica':'BALL',
            'bull':'BULL','torica':'BULL',
            'drill':'DRILL','punta':'DRILL',
            'tap':'TAP','maschio':'TAP',
            'ream':'REAM',
            'spot':'SPOT','center':'SPOT',
        }

        for i, row in df.iterrows():
            codice = str(row.get('codice_interno', '')).strip()
            if not codice or codice == 'nan':
                continue

            try:
                def flt(k, default=0.0):
                    v = row.get(k)
                    if v is None or str(v).strip() in ('', 'nan', 'None'):
                        return default
                    try: return float(str(v).replace(',', '.'))
                    except: return default

                def intt(k, default=2):
                    v = flt(k, default)
                    return int(v)

                # Tipo utensile
                tipo_str = str(row.get('tipo', '')).strip().lower()
                tipo_cod = TIPO_MAP.get(tipo_str, 'FLAT')
                tipo_row = conn.execute(
                    "SELECT id FROM tipo_utensile WHERE codice=?", (tipo_cod,)
                ).fetchone()
                tipo_id = tipo_row['id'] if tipo_row else tipo_id_default

                # Materiale
                mat_str = str(row.get('materiale', '')).strip().upper()
                mat_row = conn.execute(
                    "SELECT id FROM materiale_utensile WHERE codice=?", (mat_str,)
                ).fetchone() if mat_str else None
                mat_id = mat_row['id'] if mat_row else mat_id_default

                params = {
                    'codice_catalogo':    str(row.get('codice_catalogo', '') or '').strip() or None,
                    'descrizione':         str(row.get('descrizione', '') or '').strip() or None,
                    'id_tipo':             tipo_id,
                    'id_materiale':        mat_id,
                    'diametro_mm':         flt('diametro_mm'),
                    'raggio_punta_mm':     flt('raggio_punta_mm'),
                    'lunghezza_totale_mm': flt('lunghezza_totale_mm'),
                    'lunghezza_tagl_mm':   flt('lunghezza_tagl_mm'),
                    'num_taglienti':       intt('num_taglienti'),
                    'angolo_punta_gradi':  flt('angolo_punta_gradi') or None,
                    'angolo_elica_gradi':  flt('angolo_elica_gradi') or None,
                }

                esistente = conn.execute(
                    "SELECT id FROM utensile WHERE codice_interno=?", (codice,)
                ).fetchone()

                if not dry_run:
                    if esistente:
                        conn.execute("""UPDATE utensile SET
                            codice_catalogo=:codice_catalogo, descrizione=:descrizione,
                            id_tipo=:id_tipo, id_materiale=:id_materiale,
                            diametro_mm=:diametro_mm, raggio_punta_mm=:raggio_punta_mm,
                            lunghezza_totale_mm=:lunghezza_totale_mm,
                            lunghezza_tagl_mm=:lunghezza_tagl_mm,
                            num_taglienti=:num_taglienti,
                            angolo_punta_gradi=:angolo_punta_gradi,
                            angolo_elica_gradi=:angolo_elica_gradi
                            WHERE codice_interno=?""",
                            {**params, 'codice': codice})
                        aggiornati += 1
                    else:
                        conn.execute("""INSERT INTO utensile
                            (codice_interno, codice_catalogo, descrizione,
                             id_tipo, id_materiale, diametro_mm, raggio_punta_mm,
                             lunghezza_totale_mm, lunghezza_tagl_mm, num_taglienti,
                             angolo_punta_gradi, angolo_elica_gradi)
                            VALUES (:codice_interno,:codice_catalogo,:descrizione,
                                    :id_tipo,:id_materiale,:diametro_mm,:raggio_punta_mm,
                                    :lunghezza_totale_mm,:lunghezza_tagl_mm,:num_taglienti,
                                    :angolo_punta_gradi,:angolo_elica_gradi)""",
                            {'codice_interno': codice, **params})
                        inseriti += 1
                else:
                    if esistente: aggiornati += 1
                    else: inseriti += 1

            except Exception as e:
                errori.append(f"Riga {i+2} ({codice}): {e}")

        if not dry_run:
            conn.commit()

    except Exception as e:
        errori.insert(0, str(e))
    finally:
        conn.close()

    return {'inseriti': inseriti, 'aggiornati': aggiornati,
            'errori': errori, 'dry_run': dry_run, 'versione': ''}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--file',    required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    r = importa(args.file, dry_run=args.dry_run)
    print(f"Inseriti: {r['inseriti']} | Aggiornati: {r['aggiornati']} | Errori: {len(r['errori'])}")
    for e in r['errori'][:5]:
        print(f"  ERRORE: {e}")
