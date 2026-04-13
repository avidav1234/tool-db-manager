"""
cimatron_importer.py
====================
Importa TUTTI i dati Cimatron nel DB master:
  - Cutters:  geometria, stelo, pinza, parametri taglio default, vita utensile
  - Holders:  portautensili con geometria multi-segmento
  - Material: condizioni taglio Vc/Fz per materiale (287 combinazioni)
  - Contour:  profili sagomati (coordinate)

Mappatura ID verificata su file reale Cimatron 2025 SP5.
"""

import os, sys, sqlite3, zipfile, json

_BASE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
_LEARNER = os.path.join(_BASE, 'learner')
sys.path.insert(0, _LEARNER)
sys.path.insert(0, _BASE)

DB_PATH = os.path.join(_BASE, 'database', 'tool_master.db')

# ---------------------------------------------------------------
# Mappatura completa ID Cimatron -> campo Python
# Fonte: analisi reale file Cimatron_2025.zip
# ---------------------------------------------------------------
CUTTERS_MAP = {
    # Identificazione
    '1101': 'codice_interno',
    '1102': 'alias',           # Commento Cimatron = NOME OFFICINA
    '1103': 'sito_web',
    '1201': 'num_magazzino',
    '1202': 'comp_diametro',       # non importato nel DB (offset macchina)
    '1203': 'comp_lunghezza',      # non importato nel DB (offset macchina)
    # Tipo e tecnologia
    '2101': 'tecnologia_id',
    '2102': 'tipo_id',
    '2103': 'codice_catalogo',
    # Geometria principale
    '2105': 'diametro_mm',
    '2106': 'raggio_punta_mm',
    '2107': 'usa_lunghezza_completa',
    '2108': 'lunghezza_totale_mm',
    '2109': 'lunghezza_tagl_mm',
    '2110': 'lunghezza_tagl2_mm',
    '2111': 'conico',
    '2112': 'angolo_conico_gradi',
    '2113': 'angolo_punta_gradi',
    # Stelo principale
    '2201': 'stelo1_tipo',
    '2202': 'diam_stelo_mm',
    '2203': 'diam_stelo_inf_mm',
    '2204': 'usa_angolo_cono_stelo',
    '2205': 'angolo_cono_stelo_gradi',
    '2206': 'lungh_cono_stelo_mm',
    '2207': 'lungh_libera_stelo_mm',
    # Stelo2
    '2208': 'stelo2_tipo',
    '2209': 'diam_stelo2_mm',
    '2210': 'diam_stelo2_inf_mm',
    '2211': 'angolo_cono_stelo2_gradi',
    '2212': 'lungh_cono_stelo2_mm',
    '2213': 'lungh_libera_stelo2_mm',
    # Pinza inline
    '3101': 'nome_pinza',
    '3102': 'lungh_presa_mm',
    '3103': 'fuori_pinza_mm',         # DISTANZA PUNTA->INIZIO PINZA (dato critico CAM)
    # Parametri taglio di default
    '4101': 'avanzamento_default',
    '4102': 'rotazione_default',
    '4103': 'vc_default',
    '4104': 'fz_default',
    '4106': 'num_taglienti',
    '4202': 'vita_utensile',
    '4203': 'dir_rotazione_id',
    '4204': 'refrigerante_id',
    # Parametri moto default
    '5101': 'passo_z_default',
    '5102': 'passo_lat_default',
    '5106': 'tolleranza',
}

HOLDERS_MAP = {
    '7001': 'codice_interno',
    '7002': 'descrizione',
    '7003': 'num_segmenti',
    '7004': 'num_seg_mandrino',
    '7010': 'tipo_attacco',
    '7901': 'tipo_visualiz',
}
# Segmenti 1-20: ID 70N1..70N4 dove N = numero segmento (1=11, 2=21, ...)
for seg in range(1, 21):
    base = 7000 + seg * 10
    HOLDERS_MAP[str(base + 1)] = f'seg{seg}_diam_inf'
    HOLDERS_MAP[str(base + 2)] = f'seg{seg}_diam_sup'
    HOLDERS_MAP[str(base + 3)] = f'seg{seg}_alt_cono'
    HOLDERS_MAP[str(base + 4)] = f'seg{seg}_alt_tot'

MATERIAL_MAP = {
    '8001': 'nome_utensile',
    '8002': 'materiale_pezzo',
    '8101': 'vf_mm_min',
    '8102': 'n_rpm',
    '8103': 'vc_m_min',
    '8104': 'fz_mm',
    '8105': 'passo',
    '8201': 'ap_mm',
    '8202': 'ae_mm',
    '8301': 'rompitruciolo',
    '8302': 'decrementa',
    '8401': 'refrigerante',
}

CONTOUR_MAP = {
    '9001': 'nome_utensile',
    '9002': 'dati',
}

# Valori categorici
TIPO_ID_MAP = {
    '210201': 'FLAT',  '210202': 'BALL',  '210203': 'BULL',
    '210204': 'DRILL', '210205': 'REAM',  '210206': 'TAP',
    '210207': 'SPOT',  '210208': 'BALL',  '210209': 'BULL',
    '210210': 'TAPER',
}
TECNOLOGIA_MAP = {
    '210101': 'Fresatura', '210102': 'Foratura',
    '210103': 'Lollipop',  '210104': 'Slot Mill',
}
DIR_ROT_MAP = {
    '420301': 'CW', '420302': 'CCW', '420303': 'OFF',
}
REFRIG_MAP = {
    '420401': 'OFF',     '420402': 'FLOOD',   '420403': 'MIST',
    '420404': 'AIR',     '420405': 'THROUGH',
    # Valori gia decodificati dal parser (passthrough)
    'OFF': 'OFF', 'FLOOD': 'FLOOD', 'MIST': 'MIST', 'AIR': 'AIR', 'THROUGH': 'THROUGH',
}


def _to_float(v, default=None):
    if v is None or str(v).strip() in ('', 'nan', 'None'): return default
    try: return round(float(str(v).replace(',', '.').replace('E-0', 'e-0')), 6)
    except: return default

def _to_int(v, default=None):
    f = _to_float(v)
    return int(f) if f is not None else default

def _to_str(v):
    s = str(v).strip()
    return s if s and s != 'nan' else None


def _leggi_csv(content_bytes):
    for enc in ('utf-16', 'utf-8-sig', 'utf-8', 'latin-1'):
        try:
            text = content_bytes.decode(enc)
            if '|' in text: break
        except Exception: continue
    lines = text.splitlines()
    nome_riga = id_riga = -1
    versione = ''
    for i, line in enumerate(lines):
        s = line.strip().lstrip('"')
        if s.startswith('CimatronE') and '//' not in s[:3]:
            versione = s.split('|')[0]; continue
        if s.startswith('//') or s == '': continue
        if nome_riga == -1: nome_riga = i; continue
        if id_riga == -1:   id_riga = i;  break
    col_names = [c.strip() for c in lines[nome_riga].split('|')]
    col_ids   = [c.strip() for c in lines[id_riga].split('|')]
    rows = []
    for line in lines[id_riga+1:]:
        if not line.strip() or line.strip().startswith('//'): continue
        parts = line.split('|')
        row = {}
        for j in range(min(len(col_ids), len(parts))):
            cid = col_ids[j]
            val = parts[j].strip()
            if cid and val: row[cid] = val
        if row: rows.append(row)
    return rows, versione


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


def _get_tipo_id(conn, codice):
    r = conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (codice,)).fetchone()
    if r: return r['id']
    conn.execute("INSERT OR IGNORE INTO tipo_utensile (codice,descrizione) VALUES (?,?)", (codice, codice))
    return conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (codice,)).fetchone()['id']


def _get_mat_id(conn, codice='HM'):
    r = conn.execute("SELECT id FROM materiale_utensile WHERE codice=?", (codice,)).fetchone()
    return r['id'] if r else 1


# ---------------------------------------------------------------
# IMPORT HOLDERS
# ---------------------------------------------------------------
def importa_holders(rows, conn, dry_run=False):
    ins = agg = 0
    errori = []
    for row in rows:
        codice = _to_str(row.get('7001', ''))
        if not codice: continue
        try:
            params = {
                'codice_interno':   codice,
            'alias':            _to_str(row.get('1102')),   # Commento = nome officina
            'cam_sorgente':     'Cimatron',
            'id_originale_cam': codice,
                'descrizione':      _to_str(row.get('7002', '')),  # descrizione tecnica (non l'alias)
                'tipo_attacco':  _to_str(row.get('7010')),
                'num_segmenti':     _to_int(row.get('7003'), 0),
                'num_seg_mandrino': _to_int(row.get('7004'), 0),
                'tipo_visualiz':    _to_int(row.get('7901'), 0),
            }
            esiste = conn.execute("SELECT id FROM portautensile WHERE codice_interno=?", (codice,)).fetchone()
            if not dry_run:
                if esiste:
                    conn.execute("""UPDATE portautensile SET descrizione=:descrizione,
                        tipo_attacco=:tipo_attacco, num_segmenti=:num_segmenti
                        WHERE codice_interno=:codice_interno""", params)
                    pid = esiste['id']
                    agg += 1
                else:
                    conn.execute("""INSERT INTO portautensile
                        (codice_interno,descrizione,tipo_attacco,num_segmenti,num_seg_mandrino,tipo_visualiz)
                        VALUES (:codice_interno,:descrizione,:tipo_attacco,:num_segmenti,:num_seg_mandrino,:tipo_visualiz)""", params)
                    pid = conn.execute("SELECT id FROM portautensile WHERE codice_interno=?", (codice,)).fetchone()['id']
                    ins += 1
                # Inserisci segmenti
                conn.execute("DELETE FROM portautensile_segmento WHERE id_portautensile=?", (pid,))
                for seg in range(1, 21):
                    base = str(7000 + seg * 10)
                    di = _to_float(row.get(str(base + 1)))
                    ds = _to_float(row.get(str(base + 2)))
                    ac = _to_float(row.get(str(base + 3)))
                    at = _to_float(row.get(str(base + 4)))
                    if at and at > 0:
                        conn.execute("""INSERT OR REPLACE INTO portautensile_segmento
                            (id_portautensile,numero_segmento,diametro_inf_mm,diametro_sup_mm,lunghezza_mm)
                            VALUES (?,?,?,?,?)""", (pid, seg, di, ds, at))
            else:
                if esiste: agg += 1
                else: ins += 1
        except Exception as e:
            errori.append(f"Holder {codice}: {e}")
    if not dry_run: conn.commit()
    return ins, agg, errori


# ---------------------------------------------------------------
# IMPORT CUTTERS
# ---------------------------------------------------------------
def importa_cutters(rows, conn, dry_run=False):
    ins = agg = 0
    errori = []
    mat_id_hm = _get_mat_id(conn, 'HM')

    for row in rows:
        codice = _to_str(row.get('1101', ''))
        if not codice: continue
        try:
            tipo_raw = row.get('2102', '')
            tipo_cod = TIPO_ID_MAP.get(tipo_raw, 'FLAT')
            tipo_id  = _get_tipo_id(conn, tipo_cod)
            tecnologia = TECNOLOGIA_MAP.get(row.get('2101', ''), None)
            dir_rot    = DIR_ROT_MAP.get(row.get('4203', ''), None)
            refrig     = REFRIG_MAP.get(row.get('4204', ''), None)

            # Cerca portautensile per nome pinza
            nome_pinza = _to_str(row.get('3101'))
            pid = None
            if nome_pinza:
                r = conn.execute("SELECT id FROM portautensile WHERE codice_interno=?", (nome_pinza,)).fetchone()
                if r: pid = r['id']

            params = dict(
                cam_sorgente   = 'Cimatron',
                # Identificazione
                codice_catalogo          = _to_str(row.get('2103')),
                descrizione              = None,                          # campo libero (1102=alias, non descrizione)
                sito_web                 = _to_str(row.get('1103')),
                num_magazzino            = _to_int(row.get('1201')),
                # Classificazione
                id_tipo                  = tipo_id,
                id_materiale             = mat_id_hm,
                id_portautensile         = pid,
                tecnologia               = tecnologia,
                # Geometria corpo
                diametro_mm              = _to_float(row.get('2105'), 0),
                raggio_punta_mm          = _to_float(row.get('2106'), 0),
                angolo_punta_gradi       = _to_float(row.get('2113')),
                lunghezza_totale_mm      = _to_float(row.get('2108'), 0),
                lunghezza_tagl_mm        = _to_float(row.get('2109'), 0),
                lunghezza_tagl2_mm       = _to_float(row.get('2110')),
                num_taglienti            = _to_int(row.get('4106'), 2),
                conico                   = _to_int(row.get('2111'), 0),
                angolo_conico_gradi      = _to_float(row.get('2112')),
                # Assemblaggio pinza - DATI CRITICI
                nome_pinza               = nome_pinza,
                lungh_presa_mm           = _to_float(row.get('3102')),
                fuori_pinza_mm           = _to_float(row.get('3103')),   # distanza punta -> inizio pinza
                lungh_libera_prolunga_mm = _to_float(row.get('3105')),
                # Stelo principale
                diam_stelo_sup_mm        = _to_float(row.get('2202')),
                diam_stelo_inf_mm        = _to_float(row.get('2203')),
                lungh_cono_stelo_mm      = _to_float(row.get('2206')),
                lungh_libera_stelo_mm    = _to_float(row.get('2207')),
                angolo_cono_stelo_gradi  = _to_float(row.get('2205')),
                usa_angolo_cono_stelo    = _to_int(row.get('2204'), 0),
                # Stelo secondario
                diam_stelo2_sup_mm       = _to_float(row.get('2209')),
                diam_stelo2_inf_mm       = _to_float(row.get('2210')),
                lungh_cono_stelo2_mm     = _to_float(row.get('2212')),
                lungh_libera_stelo2_mm   = _to_float(row.get('2213')),
                angolo_cono_stelo2_gradi = _to_float(row.get('2211')),
                # Parametri taglio default
                avanzamento_default      = _to_float(row.get('4101')),
                rotazione_default        = _to_float(row.get('4102')),
                vc_default               = _to_float(row.get('4103')),
                fz_default               = _to_float(row.get('4104')),
                passo_z_default          = _to_float(row.get('5101')),
                passo_lat_default        = _to_float(row.get('5102')),
                tolleranza_default       = _to_float(row.get('5106')),
                vita_utensile            = _to_int(row.get('4202')),
                # Macchina
                dir_rotazione            = dir_rot,
                refrigerante             = refrig,
                distanza_pivot           = _to_float(row.get('4205')),
                # Filettatura
                passo_mm                 = _to_float(row.get('2123')),
            )

            esiste = conn.execute("SELECT id FROM utensile WHERE codice_interno=?", (codice,)).fetchone()
            if not dry_run:
                if esiste:
                    sets = ', '.join(f"{k}=:{k}" for k in params)
                    conn.execute(f"UPDATE utensile SET {sets} WHERE codice_interno=:codice_interno",
                                 {**params, 'codice_interno': codice})
                    agg += 1
                else:
                    cols = 'codice_interno, ' + ', '.join(params.keys())
                    vals = ':codice_interno, ' + ', '.join(f':{k}' for k in params)
                    conn.execute(f"INSERT INTO utensile ({cols}) VALUES ({vals})",
                                 {'codice_interno': codice, **params})
                    ins += 1
            else:
                if esiste: agg += 1
                else: ins += 1

        except Exception as e:
            errori.append(f"Cutter {codice}: {e}")

    if not dry_run: conn.commit()
    return ins, agg, errori


# ---------------------------------------------------------------
# IMPORT MATERIAL (Vc/Fz per materiale)
# ---------------------------------------------------------------
def importa_material(rows, conn, dry_run=False):
    ins = agg = 0
    errori = []
    # Crea tabella se non esiste (DB fresh o prima importazione)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS condizioni_taglio (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            id_utensile     INTEGER NOT NULL REFERENCES utensile(id) ON DELETE CASCADE,
            materiale_pezzo TEXT NOT NULL,
            applicazione    TEXT,
            cam_sorgente        TEXT,
            vc_m_min            REAL,
            rotazione_rpm       REAL,
            fz_mm_z             REAL,
            avanzamento_mm_min  REAL,
            ap_mm               REAL,
            ae_mm               REAL,
            rompitruciolo       REAL,
            decrementa          REAL,
            refrigerante        TEXT,
            note                TEXT,
            UNIQUE(id_utensile, materiale_pezzo, applicazione)
        )
    """)
    conn.commit()

    for row in rows:
        nome  = _to_str(row.get('8001', ''))
        mater = _to_str(row.get('8002', ''))
        if not nome or not mater: continue
        try:
            u = conn.execute("SELECT id FROM utensile WHERE codice_interno=?", (nome,)).fetchone()
            if not u: continue
            params = dict(
                id_utensile   = u['id'],
                materiale_pezzo = mater,
                applicazione  = None,
                avanzamento_mm_min = _to_float(row.get('8101')),
                rotazione_rpm      = _to_float(row.get('8102')),
                vc_m_min      = _to_float(row.get('8103')),
                fz_mm_z            = _to_float(row.get('8104')),
                ap_mm         = _to_float(row.get('8201')),
                ae_mm         = _to_float(row.get('8202')),
                rompitruciolo = _to_float(row.get('8301')),
                decrementa    = _to_float(row.get('8302')),
                
                refrigerante  = _to_str(row.get('8401')),
            )
            esiste = conn.execute(
                "SELECT id FROM condizioni_taglio WHERE id_utensile=? AND materiale_pezzo=? AND applicazione IS NULL",
                (u['id'], mater)
            ).fetchone()
            if not dry_run:
                if esiste:
                    conn.execute("""UPDATE condizioni_taglio SET
                        cam_sorgente=:cam_sorgente, vc_m_min=:vc_m_min, rotazione_rpm=:rotazione_rpm, fz_mm_z=:fz_mm_z, avanzamento_mm_min=:avanzamento_mm_min,
                        ap_mm=:ap_mm, ae_mm=:ae_mm, rompitruciolo=:rompitruciolo,
                        decrementa=:decrementa, refrigerante=:refrigerante
                        WHERE id=?""", {**params, 'id': esiste['id']})
                    agg += 1
                else:
                    conn.execute("""INSERT INTO condizioni_taglio
                        (id_utensile,materiale_pezzo,applicazione,vc_m_min,n_rpm,fz_mm,vf_mm_min,ap_mm,ae_mm,rompitruciolo,decrementa,refrigerante)
                        VALUES (:id_utensile,:materiale_pezzo,:applicazione,:vc_m_min,:n_rpm,:fz_mm,:vf_mm_min,:ap_mm,:ae_mm,:rompitruciolo,:decrementa,:refrigerante)""", params)
                    ins += 1
            else:
                if esiste: agg += 1
                else: ins += 1
        except Exception as e:
            errori.append(f"Material {nome}/{mater}: {e}")
    if not dry_run: conn.commit()
    return ins, agg, errori


# ---------------------------------------------------------------
# IMPORT CONTOUR
# ---------------------------------------------------------------
def importa_contour(rows, conn, dry_run=False):
    ins = 0
    errori = []
    for row in rows:
        nome = _to_str(row.get('9001', ''))
        if not nome: continue
        try:
            u = conn.execute("SELECT id FROM utensile WHERE codice_interno=?", (nome,)).fetchone()
            if not u: continue
            dati = {k: v for k, v in row.items() if k != '9001'}
            if not dry_run:
                conn.execute("DELETE FROM profilo_sagomato WHERE id_utensile=?", (u['id'],))
                conn.execute("INSERT INTO profilo_sagomato (id_utensile, dati_json) VALUES (?,?)",
                             (u['id'], json.dumps(dati)))
                ins += 1
        except Exception as e:
            errori.append(f"Contour {nome}: {e}")
    if not dry_run: conn.commit()
    return ins, 0, errori


# ---------------------------------------------------------------
# ENTRY POINT PRINCIPALE
# ---------------------------------------------------------------
def importa_file(filepath: str, dry_run: bool = False) -> dict:
    # Rilevamento formato
    def _e_cimatron(fp):
        try:
            with open(fp, 'rb') as f:
                magic = f.read(2)
            if magic in (b'\xff\xfe', b'\xfe\xff'): return True
        except Exception: pass
        if fp.lower().endswith('.xls'):
            try:
                import xlrd
                return 'Cutters' in xlrd.open_workbook(fp).sheet_names()
            except Exception: pass
        if fp.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(fp) as z:
                    return any('Cutters' in os.path.basename(n) and n.endswith('.csv') for n in z.namelist())
            except Exception: pass
        return False

    if not _e_cimatron(filepath):
        raise ValueError(f"File non riconosciuto come export Cimatron: {filepath}")

    conn = get_conn()
    _init_db(conn)
    versione = '?'
    risultato = {}

    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.zip':
        with zipfile.ZipFile(filepath) as z:
            nomi = z.namelist()

            def leggi(key):
                f = next((n for n in nomi if key in os.path.basename(n) and n.endswith('.csv')), None)
                if not f: return [], ''
                with z.open(f) as fh: return _leggi_csv(fh.read())

            holders_rows,  _ = leggi('Holders')
            cutters_rows, versione = leggi('Cutters')
            material_rows, _ = leggi('Material')
            contour_rows,  _ = leggi('Contour')

    elif ext == '.csv':
        with open(filepath, 'rb') as f: content = f.read()
        cutters_rows, versione = _leggi_csv(content)
        holders_rows = material_rows = contour_rows = []

    elif ext == '.xls':
        from cimatron_parser import leggi_cimatron_xls
        r = leggi_cimatron_xls(filepath)
        cutters_rows = r['df'].to_dict('records') if 'df' in r else []
        versione = r.get('versione_rilevata', '?')
        holders_rows = material_rows = contour_rows = []
    else:
        raise ValueError(f"Formato non supportato: {ext}")

    # Importa nell'ordine corretto (holders prima di cutters per FK)
    h_ins, h_agg, h_err = importa_holders(holders_rows, conn, dry_run)
    c_ins, c_agg, c_err = importa_cutters(cutters_rows, conn, dry_run)
    m_ins, m_agg, m_err = importa_material(material_rows, conn, dry_run)
    k_ins, _,     k_err = importa_contour(contour_rows, conn, dry_run)

    conn.close()

    return {
        'versione':              versione,
        'dry_run':               dry_run,
        'utensili_inseriti':     c_ins,
        'utensili_aggiornati':   c_agg,
        'utensili_errori':       c_err,
        'holders_inseriti':      h_ins,
        'holders_aggiornati':    h_agg,
        'taglio_inserite':       m_ins,
        'taglio_aggiornate':     m_agg,
        'contour_inseriti':      k_ins,
        'totale_utensili':       c_ins + c_agg,
        'totale_taglio':         m_ins + m_agg,
        'totale_holders':        h_ins + h_agg,
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--file',    required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    r = importa_file(args.file, dry_run=args.dry_run)
    print(f"Versione:  {r['versione']}")
    print(f"Utensili:  {r['utensili_inseriti']} inseriti, {r['utensili_aggiornati']} aggiornati")
    print(f"Holders:   {r['holders_inseriti']} inseriti, {r['holders_aggiornati']} aggiornati")
    print(f"Vc/Fz:     {r['taglio_inserite']} inserite, {r['taglio_aggiornate']} aggiornate")
    print(f"Contour:   {r['contour_inseriti']} inseriti")
    if r['utensili_errori']:
        print(f"Errori:    {len(r['utensili_errori'])}")
        for e in r['utensili_errori'][:5]: print(f"  {e}")
