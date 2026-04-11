import os, sys, sqlite3, zipfile

_BASE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
_LEARNER = os.path.join(_BASE, 'learner')

# Aggiungi i path subito all'import del modulo, non dentro le funzioni
for _p in [_BASE, _LEARNER]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

DB_PATH = os.path.join(_BASE, 'database', 'tool_master.db')


def _is_cimatron(filepath):
    """Rileva se il file e' un export Cimatron tramite magic bytes UTF-16."""
    # UTF-16 magic bytes: FF FE (little-endian) o FE FF (big-endian)
    # Cimatron e' l'unico CAM che esporta CSV in UTF-16
    try:
        with open(filepath, 'rb') as f:
            magic = f.read(2)
        if magic in (b'\xff\xfe', b'\xfe\xff'):
            return True
    except Exception:
        pass
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.xls':
        try:
            import xlrd
            return 'Cutters' in xlrd.open_workbook(filepath).sheet_names()
        except Exception:
            pass
    if ext == '.zip':
        try:
            with zipfile.ZipFile(filepath) as z:
                return any('Cutters' in os.path.basename(n) and n.endswith('.csv')
                           for n in z.namelist())
        except Exception:
            pass
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


def importa(filepath, dry_run=False):
    if _is_cimatron(filepath):
        return _importa_cimatron(filepath, dry_run)
    return _importa_generico(filepath, dry_run)


def _importa_cimatron(filepath, dry_run):
    try:
        from cimatron_importer import importa_file
        r = importa_file(filepath, dry_run=dry_run)
        return {
            'inseriti':          r.get('utensili_inseriti', 0),
            'aggiornati':        r.get('utensili_aggiornati', 0),
            'errori':            r.get('utensili_errori', []),
            'dry_run':           dry_run,
            'versione':          r.get('versione', ''),
            'taglio_inserite':   r.get('taglio_inserite', 0),
            'taglio_aggiornate': r.get('taglio_aggiornate', 0),
        }
    except Exception as e:
        return {'inseriti': 0, 'aggiornati': 0, 'errori': [str(e)], 'dry_run': dry_run}


def _importa_generico(filepath, dry_run):
    import pandas as pd
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext in ('.xlsx', '.xls'):
            df = pd.read_excel(filepath)
        elif ext == '.csv':
            df = None
            for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
                try:
                    df = pd.read_csv(filepath, encoding=enc, sep=None, engine='python')
                    break
                except Exception:
                    continue
            if df is None:
                raise ValueError("Encoding CSV non riconosciuto")
        else:
            raise ValueError(f"Formato non supportato: {ext}")
    except Exception as e:
        return {'inseriti': 0, 'aggiornati': 0, 'errori': [f"Lettura file: {e}"], 'dry_run': dry_run}

    df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
    ALIAS = {'codice': 'codice_interno', 'nome': 'codice_interno', 'name': 'codice_interno',
             'type': 'tipo', 'diameter': 'diametro_mm', 'diam': 'diametro_mm'}
    for a, c in ALIAS.items():
        if a in df.columns and c not in df.columns:
            df.rename(columns={a: c}, inplace=True)

    if 'codice_interno' not in df.columns:
        return {'inseriti': 0, 'aggiornati': 0, 'dry_run': dry_run,
                'errori': [f"Colonna 'codice_interno' non trovata. Colonne: {list(df.columns)}"]}

    inseriti = aggiornati = 0
    errori = []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        tid = conn.execute("SELECT id FROM tipo_utensile WHERE codice='FLAT'").fetchone()['id']
        mid = conn.execute("SELECT id FROM materiale_utensile WHERE codice='HM'").fetchone()['id']
        for i, row in df.iterrows():
            codice = str(row.get('codice_interno', '')).strip()
            if not codice or codice == 'nan':
                continue
            try:
                def flt(k, d=0.0):
                    v = row.get(k)
                    s = str(v).strip()
                    if s in ('', 'nan', 'None'): return d
                    try: return float(s.replace(',', '.'))
                    except: return d
                esiste = conn.execute("SELECT id FROM utensile WHERE codice_interno=?", (codice,)).fetchone()
                if not dry_run:
                    if esiste:
                        conn.execute("UPDATE utensile SET diametro_mm=?,lunghezza_totale_mm=?,lunghezza_tagl_mm=? WHERE codice_interno=?",
                            (flt('diametro_mm'), flt('lunghezza_totale_mm'), flt('lunghezza_tagl_mm'), codice))
                        aggiornati += 1
                    else:
                        conn.execute("INSERT INTO utensile (codice_interno,id_tipo,id_materiale,diametro_mm,lunghezza_totale_mm,lunghezza_tagl_mm,num_taglienti) VALUES (?,?,?,?,?,?,?)",
                            (codice, tid, mid, flt('diametro_mm'), flt('lunghezza_totale_mm'), flt('lunghezza_tagl_mm'), int(flt('num_taglienti', 2))))
                        inseriti += 1
                else:
                    if esiste: aggiornati += 1
                    else: inseriti += 1
            except Exception as e:
                errori.append(f"Riga {i+2} ({codice}): {e}")
        if not dry_run:
            conn.commit()
    except Exception as e:
        errori.insert(0, str(e))
    finally:
        conn.close()
    return {'inseriti': inseriti, 'aggiornati': aggiornati, 'errori': errori, 'dry_run': dry_run, 'versione': ''}
