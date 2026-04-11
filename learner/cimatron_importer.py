"""
cimatron_importer.py
====================
Importa utensili Cimatron nel database master SQLite.

Importa:
  - Geometria utensili (da Cutters_*.csv o file CSV singolo)
  - Dati di taglio Vc/Fz per materiale (da Material_*.csv nel ZIP)

Uso:
    python cimatron_importer.py --file export.zip
    python cimatron_importer.py --file Cutters.csv
    python cimatron_importer.py --file export.csv   # CSV singolo
    python cimatron_importer.py --file export.xls   # XLS nativo
    python cimatron_importer.py --file export.zip --dry-run
"""

import os
import sys
import sqlite3
import argparse

# Aggiunge il percorso del progetto al path
_BASE = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.dirname(__file__))   # learner/
sys.path.insert(0, _BASE)                        # root/

DB_PATH = os.path.join(_BASE, 'database', 'tool_master.db')

# Mapping Tipo Cimatron ID -> tipo master
TIPO_ID_MAP = {
    '210201': 'FLAT', '210202': 'BALL', '210203': 'BULL',
    '210204': 'DRILL','210205': 'REAM', '210206': 'TAP',
    '210207': 'SPOT', '210208': 'BALL','210209': 'BULL',
}
TIPO_STR_MAP = {
    'flat':'FLAT','piana':'FLAT','ball':'BALL','sferica':'BALL',
    'bull':'BULL','torica':'BULL','drilling':'DRILL','foratura':'DRILL',
    'ream':'REAM','tap':'TAP','filettatura':'TAP','center':'SPOT','centratura':'SPOT',
}


def _to_float(v, default=None):
    if v is None or str(v).strip() in ('', 'nan', 'None'):
        return default
    try:
        return float(str(v).replace(',', '.'))
    except Exception:
        return default


def _to_int(v, default=None):
    f = _to_float(v)
    return int(f) if f is not None else default


def _decode_tipo(val):
    v = str(val).strip()
    return TIPO_ID_MAP.get(v, TIPO_STR_MAP.get(v.lower(), 'FLAT'))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db(conn):
    schema = os.path.join(_BASE, 'database', 'schema.sql')
    with open(schema, encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()


def _get_or_create_tipo(conn, codice):
    row = conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (codice,)).fetchone()
    if row:
        return row['id']
    # Inserisci se non esiste (es. THREAD, TAPER)
    conn.execute("INSERT OR IGNORE INTO tipo_utensile (codice,descrizione) VALUES (?,?)",
                 (codice, codice))
    return conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (codice,)).fetchone()['id']


def importa_utensili(df_cutters, conn, dry_run=False):
    """
    Importa il DataFrame Cutters nel DB master.
    Ritorna (inseriti, aggiornati, errori).
    """
    inseriti = aggiornati = 0
    errori = []

    # Identifica le colonne per nome (le colonne sono in italiano)
    COL = {
        'nome':       next((c for c in df_cutters.columns if 'nome utensile' in c.lower() or 'cutter name' in c.lower()), None),
        'commento':   next((c for c in df_cutters.columns if 'commento' in c.lower() or 'comment' in c.lower()), None),
        'catalogo':   next((c for c in df_cutters.columns if 'catalogo' in c.lower() or 'catalog' in c.lower()), None),
        'tipo':       next((c for c in df_cutters.columns if 'punta/tipo' in c.lower() or 'tip/type' in c.lower()), None),
        'diam':       next((c for c in df_cutters.columns if c.lower() == 'diametro' or c.lower() == 'diameter'), None),
        'raggio':     next((c for c in df_cutters.columns if 'raggio base' in c.lower() or 'corner radius' in c.lower()), None),
        'l_tot':      next((c for c in df_cutters.columns if 'lunghezza totale' in c.lower() or 'full cutter length' in c.lower()), None),
        'l_utile':    next((c for c in df_cutters.columns if 'lunghezza utile' in c.lower() or 'clear length' in c.lower()), None),
        'num_tagl':   next((c for c in df_cutters.columns if c.lower() in ('denti','num. denti','flutes','num flutes','num_taglienti','number of flutes')), None),
        'ang_punta':  next((c for c in df_cutters.columns if 'angolo punta' in c.lower() or 'tip angle' in c.lower()), None),
    }

    if not COL['nome']:
        raise ValueError("Colonna 'Nome Utensile' non trovata nel file Cutters")

    # Materiale default HM (Cimatron non esporta il materiale nel CSV Cutters)
    mat_id = conn.execute("SELECT id FROM materiale_utensile WHERE codice='HM'").fetchone()['id']

    for i, row in df_cutters.iterrows():
        codice = str(row.get(COL['nome'], '')).strip()
        if not codice:
            continue
        try:
            tipo_raw = str(row.get(COL['tipo'], 'FLAT')).strip() if COL['tipo'] else 'FLAT'
            tipo_cod = _decode_tipo(tipo_raw)
            tipo_id  = _get_or_create_tipo(conn, tipo_cod)

            params = dict(
                codice_catalogo   = str(row.get(COL['catalogo'],'') or '').strip() or None,
                descrizione       = str(row.get(COL['commento'],'') or '').strip() or None,
                id_tipo           = tipo_id,
                id_materiale      = mat_id,
                diametro_mm       = _to_float(row.get(COL['diam'])) or 0,
                raggio_punta_mm   = _to_float(row.get(COL['raggio'])) or 0,
                lunghezza_totale_mm = _to_float(row.get(COL['l_tot'])) or 0,
                lunghezza_tagl_mm = _to_float(row.get(COL['l_utile'])) or 0,
                angolo_punta_gradi = _to_float(row.get(COL['ang_punta'])) if COL['ang_punta'] else None,
                num_taglienti      = _to_int(row.get(COL.get('num_tagl', ''), 2), 2) if COL.get('num_tagl') else 2,
            )

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
                        angolo_punta_gradi=:angolo_punta_gradi,
                        num_taglienti=:num_taglienti
                        WHERE codice_interno=?""", (*params.values(), codice))
                    aggiornati += 1
                else:
                    conn.execute("""INSERT INTO utensile
                        (codice_interno, codice_catalogo, descrizione, id_tipo, id_materiale,
                         diametro_mm, raggio_punta_mm, lunghezza_totale_mm, lunghezza_tagl_mm,
                         angolo_punta_gradi)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (codice, params['codice_catalogo'], params['descrizione'],
                         params['id_tipo'], params['id_materiale'],
                         params['diametro_mm'], params['raggio_punta_mm'],
                         params['lunghezza_totale_mm'], params['lunghezza_tagl_mm'],
                         params['angolo_punta_gradi']))
                    inseriti += 1
            else:
                if esistente: aggiornati += 1
                else: inseriti += 1

        except Exception as e:
            errori.append(f"Riga {i+1} ({codice}): {e}")

    if not dry_run:
        conn.commit()

    return inseriti, aggiornati, errori


def importa_condizioni_taglio(df_material, conn, dry_run=False):
    """
    Importa i dati Vc/Fz dalla tabella Material nel DB master.
    Tabella target: condizioni_taglio (id_utensile, materiale_pezzo, vc_m_min, fz_mm, n_rpm, vf_mm_min)
    Ritorna (inserite, aggiornate, errori).
    """
    inserite = aggiornate = 0
    errori = []

    COL = {
        'nome':     next((c for c in df_material.columns if 'nome utensile' in c.lower()), None),
        'mat':      next((c for c in df_material.columns if 'nome materiale' in c.lower()), None),
        'avanz':    next((c for c in df_material.columns if 'avanz' in c.lower()), None),
        'rotaz':    next((c for c in df_material.columns if 'rotaz' in c.lower()), None),
        'vt':       next((c for c in df_material.columns if c.strip().lower() in ('vt','vc')), None),
        'fz':       next((c for c in df_material.columns if c.strip().lower() == 'fz'), None),
        'passo_z':  next((c for c in df_material.columns if 'passo in z' in c.lower()), None),
        'passo_l':  next((c for c in df_material.columns if 'passo laterale' in c.lower()), None),
    }

    if not COL['nome'] or not COL['mat']:
        raise ValueError("Colonne 'Nome Utensile' o 'Nome Materiale' non trovate nel file Material")

    for i, row in df_material.iterrows():
        codice    = str(row.get(COL['nome'], '')).strip()
        materiale = str(row.get(COL['mat'],  '')).strip()
        if not codice or not materiale:
            continue
        try:
            utensile = conn.execute(
                "SELECT id FROM utensile WHERE codice_interno=?", (codice,)
            ).fetchone()
            if not utensile:
                continue  # Salta materiali di utensili non presenti nel DB

            vc  = _to_float(row.get(COL['vt']))
            fz  = _to_float(row.get(COL['fz']))
            n   = _to_float(row.get(COL['rotaz']))
            vf  = _to_float(row.get(COL['avanz']))
            ap  = _to_float(row.get(COL['passo_z']))
            ae  = _to_float(row.get(COL['passo_l']))

            esistente = conn.execute(
                "SELECT id FROM condizioni_taglio WHERE id_utensile=? AND materiale_pezzo=?",
                (utensile['id'], materiale)
            ).fetchone()

            if not dry_run:
                if esistente:
                    conn.execute("""UPDATE condizioni_taglio SET
                        vc_m_min=?, n_rpm=?, fz_mm=?, vf_mm_min=?, ap_mm=?, ae_mm=?
                        WHERE id=?""",
                        (vc, n, fz, vf, ap, ae, esistente['id']))
                    aggiornate += 1
                else:
                    conn.execute("""INSERT INTO condizioni_taglio
                        (id_utensile, materiale_pezzo, vc_m_min, n_rpm, fz_mm, vf_mm_min, ap_mm, ae_mm)
                        VALUES (?,?,?,?,?,?,?,?)""",
                        (utensile['id'], materiale, vc, n, fz, vf, ap, ae))
                    inserite += 1
            else:
                if esistente: aggiornate += 1
                else: inserite += 1

        except Exception as e:
            errori.append(f"Riga {i+1} ({codice}/{materiale}): {e}")

    if not dry_run:
        conn.commit()

    return inserite, aggiornate, errori


def importa_file(filepath: str, dry_run: bool = False) -> dict:
    """
    Punto di ingresso principale. Accetta qualsiasi formato Cimatron.
    Ritorna un dizionario con il riepilogo dell'import.
    """
    from cimatron_parser import is_cimatron_file, leggi_cimatron_csv, leggi_cimatron_xls, leggi_cimatron_zip
    import zipfile

    ext = os.path.splitext(filepath)[1].lower()

    # Rilevamento formato - magic bytes UTF-16 per CSV, struttura per XLS/ZIP
    def _e_cimatron(fp):
        try:
            with open(fp, 'rb') as f:
                magic = f.read(2)
            if magic in (b'\xff\xfe', b'\xfe\xff'):
                return True
        except Exception:
            pass
        if fp.lower().endswith('.xls'):
            try:
                import xlrd
                return 'Cutters' in xlrd.open_workbook(fp).sheet_names()
            except Exception:
                pass
        if fp.lower().endswith('.zip'):
            try:
                import zipfile as _zf
                with _zf.ZipFile(fp) as z:
                    return any('Cutters' in os.path.basename(n) and n.endswith('.csv')
                               for n in z.namelist())
            except Exception:
                pass
        return False

    if not _e_cimatron(filepath):
        raise ValueError(f"File non riconosciuto come export Cimatron: {filepath}")

    # Leggi con il parser appropriato
    if ext == '.zip':
        risultato = leggi_cimatron_zip(filepath)
    elif ext == '.xls':
        risultato = leggi_cimatron_xls(filepath)
    elif ext == '.csv':
        risultato = leggi_cimatron_csv(filepath)
    else:
        raise ValueError(f"Formato non supportato: {ext}")

    df_cutters  = risultato['df']
    df_material = risultato.get('df_material')
    versione    = risultato.get('versione_rilevata', '?')

    conn = get_conn()
    _init_db(conn)

    # Import utensili
    ins_u, agg_u, err_u = importa_utensili(df_cutters, conn, dry_run)

    # Import condizioni di taglio
    ins_c = agg_c = 0
    err_c = []
    if df_material is not None and len(df_material) > 0:
        ins_c, agg_c, err_c = importa_condizioni_taglio(df_material, conn, dry_run)

    conn.close()

    return {
        'versione':          versione,
        'dry_run':           dry_run,
        'utensili_inseriti': ins_u,
        'utensili_aggiornati': agg_u,
        'utensili_errori':   err_u,
        'taglio_inserite':   ins_c,
        'taglio_aggiornate': agg_c,
        'taglio_errori':     err_c,
        'totale_utensili':   ins_u + agg_u,
        'totale_taglio':     ins_c + agg_c,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Importa utensili Cimatron nel DB master')
    parser.add_argument('--file',    required=True, help='File Cimatron (CSV, XLS, ZIP)')
    parser.add_argument('--dry-run', action='store_true', help='Simula senza scrivere nel DB')
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"File non trovato: {args.file}"); sys.exit(1)

    print(f"\nImport Cimatron: {args.file}")
    if args.dry_run:
        print("MODALITA SIMULAZIONE - nessun dato scritto nel DB")
    print()

    r = importa_file(args.file, dry_run=args.dry_run)

    print(f"Versione rilevata:  {r['versione']}")
    print(f"Utensili:           {r['utensili_inseriti']} inseriti, {r['utensili_aggiornati']} aggiornati")
    if r['utensili_errori']:
        print(f"  Errori utensili:  {len(r['utensili_errori'])}")
        for e in r['utensili_errori'][:5]: print(f"    {e}")
    print(f"Condiz. taglio:     {r['taglio_inserite']} inserite, {r['taglio_aggiornate']} aggiornate")
    if r['taglio_errori']:
        print(f"  Errori taglio:    {len(r['taglio_errori'])}")
    print()
    if not args.dry_run:
        print("Import completato nel database master.")
    else:
        print("Simulazione completata. Esegui senza --dry-run per importare.")
