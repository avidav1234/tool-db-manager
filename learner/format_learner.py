"""
format_learner.py
=================
Punto di ingresso unico per l'analisi di qualsiasi file CAM.

Logica di rilevamento automatico (in ordine di priorita'):
  1. Cimatron ZIP  -> cimatron_parser.leggi_cimatron_zip()
  2. Cimatron XLS  -> cimatron_parser.leggi_cimatron_xls()
  3. Cimatron CSV  -> cimatron_parser.leggi_cimatron_csv()
  4. ZIP generico  -> parsing euristico CSV interno
  5. CSV generico  -> parsing euristico
  6. XLSX/XLS      -> parsing euristico

Nessuna configurazione richiesta: il sistema riconosce il formato
dal contenuto del file, non dall'estensione o dal nome.
"""

import os
import zipfile
import pandas as pd

# ---------------------------------------------------------------
# Campi del DB master (ISO 13399)
# ---------------------------------------------------------------
MASTER_FIELDS = {
    'codice_interno':     {'label': 'Codice interno / Nome utensile',   'tipo': 'string',
                           'keywords': ['name','nome','codice','code','id','number','nummer','bezeichnung'], 'esempio': 'FP-D10-R0-L50'},
    'codice_catalogo':    {'label': 'Codice catalogo fornitore',        'tipo': 'string',
                           'keywords': ['catalog','catalogo','article','articolo','part','sku','ref'], 'esempio': 'R216.34-10030'},
    'descrizione':        {'label': 'Descrizione utensile',             'tipo': 'string',
                           'keywords': ['descri','comment','commento','note','bemerkung','remark'], 'esempio': 'Fresa piatta D10 Z3'},
    'tipo':               {'label': 'Tipo utensile',                    'tipo': 'categoria',
                           'keywords': ['type','tipo','art','cutter','tool_type','tooltype','tip','typ'],
                           'valori_attesi': ['FLAT','BALL','BULL','DRILL','TAP','REAM','SPOT','TAPER'], 'esempio': 'BALL'},
    'diametro_mm':        {'label': 'Diametro [mm]',                    'tipo': 'float',
                           'keywords': ['diam','diameter','durchmesser','dc','d1','d '], 'range': (0.1,500.0), 'esempio': 10.0},
    'raggio_punta_mm':    {'label': 'Raggio punta / corner radius [mm]','tipo': 'float',
                           'keywords': ['corner','radius','raggio','rn','re','r_','nose'], 'range': (0.0,50.0), 'esempio': 1.0},
    'angolo_punta_gradi': {'label': 'Angolo punta [gradi]',             'tipo': 'float',
                           'keywords': ['angle','angolo','point','spitze','tip'], 'range': (0.0,180.0), 'esempio': 118.0},
    'lunghezza_totale_mm':{'label': 'Lunghezza totale [mm]',            'tipo': 'float',
                           'keywords': ['overall','total','length','lunghezza','oal','lt','l '], 'range': (1.0,500.0), 'esempio': 75.0},
    'lunghezza_tagl_mm':  {'label': 'Lunghezza tagliente [mm]',         'tipo': 'float',
                           'keywords': ['flute','cutting','tagliente','schneiden','lc','lf','fl'], 'range': (1.0,300.0), 'esempio': 22.0},
    'num_taglienti':      {'label': 'Numero taglienti',                 'tipo': 'int',
                           'keywords': ['flute','zahn','denti','teeth','taglienti','nf','z '], 'range': (1,20), 'esempio': 4},
    'angolo_elica_gradi': {'label': 'Angolo elica [gradi]',             'tipo': 'float',
                           'keywords': ['helix','elica','spiral','drall'], 'range': (0.0,90.0), 'esempio': 30.0},
    'materiale':          {'label': 'Materiale tagliente',              'tipo': 'categoria',
                           'keywords': ['material','materiale','werkstoff','substrate'],
                           'valori_attesi': ['HM','HSS','HSCo','CBN','PCD','CER'], 'esempio': 'HM'},
    # Parametri taglio di default (dal profilo utensile)
    'vc_default':         {'label': 'Velocita taglio Vc [m/min]',         'tipo': 'float',
                           'keywords': ['vc','vt','cutting speed','cutting_speed','velocita taglio','schnittgeschwindigkeit'],
                           'range': (10.0, 1000.0), 'esempio': 150.0},
    'n_rpm':              {'label': 'Velocita mandrino N [rpm]',           'tipo': 'float',
                           'keywords': ['rpm','spindle','rotaz','rotation','drehzahl','spindle speed','spindle_speed'],
                           'range': (100.0, 30000.0), 'esempio': 5000.0},
    'fz_default':         {'label': 'Avanzamento per dente Fz [mm/z]',    'tipo': 'float',
                           'keywords': ['fz','feed per tooth','feed_per_tooth','avanzamento dente'],
                           'range': (0.001, 1.0), 'esempio': 0.05},
    'vf_mm_min':          {'label': 'Avanzamento tavola Vf [mm/min]',     'tipo': 'float',
                           'keywords': ['feed','feed rate','feedrate','feed_rate','avanz','vorschub','vf','table feed'],
                           'range': (10.0, 10000.0), 'esempio': 1200.0},
    'passo_z_default':    {'label': 'Passata assiale ap [mm]',            'tipo': 'float',
                           'keywords': ['ap','axial','depth','passo z','axial depth','axial_depth','plunge','doc'],
                           'range': (0.1, 50.0), 'esempio': 5.0},
    'passo_lat_default':  {'label': 'Passata radiale ae [mm]',            'tipo': 'float',
                           'keywords': ['ae','radial','lateral','passo lat','radial depth','radial_depth','stepover','woc'],
                           'range': (0.1, 30.0), 'esempio': 3.0},
    'fuori_pinza_mm':     {'label': 'Fuori pinza - distanza punta/pinza', 'tipo': 'float',
                           'keywords': ['gauge','gauge length','fuori pinza','projection','proj_length','reach','auskragung'],
                           'range': (5.0, 300.0), 'esempio': 35.0},
    'nome_pinza':         {'label': 'Nome portautensile / pinza',         'tipo': 'string',
                           'keywords': ['holder','holder name','holder_name','pinza','portautensile','holderref','spannmittel'],
                           'esempio': 'HSK63A_D10'},
}

TIPO_GUESS = {
    # Cimatron ID numerici
    '210201':'FLAT','210202':'BALL','210203':'BULL','210204':'DRILL',
    '210205':'REAM','210206':'TAP','210207':'SPOT','210208':'BALL','210209':'BULL',
    # Numerici generici
    '1':'FLAT','2':'BALL','3':'BULL','4':'DRILL','5':'TAP','6':'REAM','7':'SPOT',
    # Italiano
    'flat':'FLAT','piatta':'FLAT','piana':'FLAT','fresa piatta':'FLAT',
    'mill':'FLAT','endmill':'FLAT','end mill':'FLAT','end_mill':'FLAT',
    'ball':'BALL','ballnose':'BALL','ball nose':'BALL','ball_nose':'BALL',
    'sferica':'BALL','sfera':'BALL','fresa sferica':'BALL',
    'bull':'BULL','bullnose':'BULL','bull nose':'BULL',
    'torica':'BULL','toroidale':'BULL','fresa torica':'BULL',
    # hyperMILL
    'flatendmill':'FLAT','flat end mill':'FLAT',
    'ballendmill':'BALL','ball end mill':'BALL','ball nose':'BALL',
    'bullendmill':'BULL','bull nose end mill':'BULL',
    'toroidalendmill':'BULL','toroidal':'BULL','toroidal end mill':'BULL',
    # WorkNC
    'flatendmill':'FLAT','ballendmill':'BALL','toroidalendmill':'BULL',
    # NX Siemens
    'mill':'FLAT','ball_mill':'BALL','bull_mill':'BULL',
    # Mastercam
    'flat endmill':'FLAT','ball endmill':'BALL','bull endmill':'BULL',
    # PowerMill
    'end_mill':'FLAT','ball_nose':'BALL','bull_nose':'BULL',
    # Foratura
    'drill':'DRILL','punta':'DRILL','foratura':'DRILL',
    'twist drill':'DRILL','twist_drill':'DRILL',
    # Filettatura
    'tap':'TAP','maschio':'TAP','filettatura':'TAP','tapping':'TAP',
    # Alesatura
    'ream':'REAM','reamer':'REAM','alesatore':'REAM','alesatura':'REAM',
    # Centratura
    'spot':'SPOT','spot drill':'SPOT','spotdrill':'SPOT','spot_drill':'SPOT',
    'center':'SPOT','centratura':'SPOT','centering':'SPOT',
    # Conico/Smusso
    'chamfer':'TAPER','taper':'TAPER','conico':'TAPER',
    # Filetto fresa
    'thread mill':'THREAD','threadmill':'THREAD','thread_mill':'THREAD',
    'fresa filetto':'THREAD',
    # Probe/tastatore
    'probe':'PROBE','tastatore':'PROBE',
}
MAT_GUESS = {
    # Numerici
    '1':'HM','2':'HSS','3':'HSCo','4':'CBN','5':'PCD','6':'CER',
    # Metallo duro
    'hm':'HM','carbide':'HM','widia':'HM','vhm':'HM','wc':'HM',
    'metallo duro':'HM','hartmetall':'HM','cemented carbide':'HM',
    'carbidecoated':'HM','coated carbide':'HM','carbide coated':'HM',
    'solid carbide':'HM','integral carbide':'HM',
    # Acciaio rapido
    'hss':'HSS','high speed steel':'HSS','acciaio rapido':'HSS',
    # HSCo
    'hsco':'HSCo','hss-co':'HSCo','cobalt':'HSCo',
    # Superhard
    'cbn':'CBN','pcbn':'CBN',
    'pcd':'PCD','diamond':'PCD','diamante':'PCD',
    'ceramic':'CER','ceramica':'CER',
}


def _score_column(col_name, series, field_key, field_meta):
    score = 0.0
    col_lower = col_name.lower().strip()
    for kw in field_meta.get('keywords', []):
        if kw.lower() in col_lower:
            score += 3.0
            if col_lower.startswith(kw.lower()):
                score += 1.0
    tipo = field_meta.get('tipo')
    non_null = series.dropna()
    if len(non_null) == 0:
        return score
    if tipo in ('float', 'int'):
        nr = pd.to_numeric(non_null, errors='coerce').notna().mean()
        if nr > 0.8:
            score += 2.0
            rng = field_meta.get('range')
            if rng:
                vals = pd.to_numeric(non_null, errors='coerce').dropna()
                if len(vals) > 0 and rng[0] <= vals.mean() <= rng[1]:
                    score += 2.0
    elif tipo == 'string':
        if non_null.apply(lambda x: isinstance(x, str)).mean() > 0.7:
            score += 1.0
    elif tipo == 'categoria':
        if 2 <= non_null.nunique() <= 20 and non_null.nunique() < len(non_null) * 0.5:
            score += 2.0
    return score


def _rileva_mappatura(df):
    mapping = {}
    used_cols = set()
    priority = ['codice_interno','diametro_mm','tipo','materiale',
                'lunghezza_totale_mm','lunghezza_tagl_mm','raggio_punta_mm',
                'num_taglienti','angolo_punta_gradi','angolo_elica_gradi',
                'codice_catalogo','descrizione']
    for fk in priority:
        fm = MASTER_FIELDS[fk]
        best_col, best_score = None, 0.0
        for col in df.columns:
            if col in used_cols:
                continue
            sc = _score_column(col, df[col], fk, fm)
            if sc > best_score:
                best_score = sc
                best_col = col
        if best_col and best_score >= 2.0:
            mapping[fk] = {
                'colonna_file': best_col, 'score': round(best_score,1),
                'tipo': fm['tipo'], 'label': fm['label'],
                'confidenza': 'alta' if best_score >= 5 else 'media' if best_score >= 3 else 'bassa'
            }
            used_cols.add(best_col)
    return mapping


def _rileva_valori_categoria(df, colonna, campo_master):
    guess_map = TIPO_GUESS if campo_master == 'tipo' else MAT_GUESS
    return {str(v): guess_map.get(str(v).strip().lower(), '?')
            for v in df[colonna].dropna().unique()}



def analizza_file(filepath: str, usa_agente: bool = True) -> dict:
    """
    Analizza qualsiasi file CAM. Rilevamento formato completamente automatico.

    Flusso:
      1. Parser deterministico (Cimatron nativo o euristica generica)
      2. Se colonne non mappate e usa_agente=True -> chiama mapping_agent
      3. Ritorna mapping completo con flag 'da_agente' per i suggerimenti AI
    """
    ext = os.path.splitext(filepath)[1].lower()

    try:
        from cimatron_parser import is_cimatron_file, leggi_cimatron_xls, leggi_cimatron_csv, leggi_cimatron_zip
        _cimatron_ok = True
    except ImportError:
        _cimatron_ok = False

    # Routing automatico
    if ext == '.zip' and _cimatron_ok and is_cimatron_file(filepath):
        risultato = leggi_cimatron_zip(filepath)
    elif ext == '.xls' and _cimatron_ok and is_cimatron_file(filepath):
        risultato = leggi_cimatron_xls(filepath)
    elif ext == '.csv' and _cimatron_ok and is_cimatron_file(filepath):
        risultato = leggi_cimatron_csv(filepath)
    else:
        risultato = _analizza_generico(filepath, ext)

    # Arricchimento con agente se ci sono colonne non mappate
    if usa_agente and risultato.get('colonne_non_mappate'):
        try:
            from mapping_agent import arricchisci_mapping
            mapping_arricchito = arricchisci_mapping(
                risultato['mapping'],
                risultato['colonne_non_mappate'],
                risultato['df'],
                usa_agente=True
            )
            # Aggiorna colonne non mappate dopo arricchimento
            nuove_mappate = {v['colonna_file'] for v in mapping_arricchito.values()}
            risultato['mapping'] = mapping_arricchito
            risultato['colonne_non_mappate'] = [
                c for c in risultato['colonne_originali']
                if c not in nuove_mappate
            ]
            risultato['agente_usato'] = True
        except Exception as e:
            risultato['agente_errore'] = str(e)
            risultato['agente_usato'] = False
    else:
        risultato['agente_usato'] = False

    return risultato


def _analizza_generico(filepath: str, ext: str) -> dict:
    """Parser euristico generico per file non Cimatron."""
    if ext == '.zip' or zipfile.is_zipfile(filepath):
        with zipfile.ZipFile(filepath, 'r') as z:
            csv_files = [f for f in z.namelist() if f.lower().endswith('.csv')]
            if not csv_files:
                raise ValueError("Nessun CSV nel ZIP")
            target = next((f for f in csv_files if 'cutter' in f.lower()), csv_files[0])
            with z.open(target) as f:
                content = f.read().decode('utf-8', errors='replace')
        sep = '|' if content.count('|') > content.count(',') else ','
        lines = [l for l in content.splitlines() if not l.startswith('//')]
        from io import StringIO
        df = pd.read_csv(StringIO('\n'.join(lines)), sep=sep, on_bad_lines='skip')
    elif ext == '.csv':
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            raw = f.read()
        sep = '|' if raw.count('|') > raw.count(',') else ','
        lines = [l for l in raw.splitlines() if not l.startswith('//')]
        from io import StringIO
        df = pd.read_csv(StringIO('\n'.join(lines)), sep=sep, on_bad_lines='skip')
    elif ext in ('.xls', '.xlsx'):
        df = pd.read_excel(filepath)
    else:
        raise ValueError(f"Formato non supportato: {ext}")

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how='all').reset_index(drop=True)

    if len(df) == 0:
        raise ValueError(
            "Il file non contiene dati utensili riconoscibili.\n"
            "Assicurati che il file contenga utensili e non sia un template vuoto."
        )

    mapping = _rileva_mappatura(df)
    valori_categoria = {}
    for campo, info in mapping.items():
        if info['tipo'] == 'categoria':
            valori_categoria[campo] = _rileva_valori_categoria(df, info['colonna_file'], campo)

    colonne_mappate = {v['colonna_file'] for v in mapping.values()}
    return {
        'filepath': filepath, 'num_righe': len(df),
        'num_colonne': len(df.columns), 'colonne_originali': list(df.columns),
        'mapping': mapping, 'valori_categoria': valori_categoria,
        'colonne_non_mappate': [c for c in df.columns if c not in colonne_mappate],
        'anteprima': df.head(5).to_dict(orient='records'),
        'df': df, 'software_rilevato': 'sconosciuto',
        'versione_rilevata': '', 'parser_usato': 'generico',
    }




if __name__ == '__main__':
    import argparse, sys
    parser = argparse.ArgumentParser(description='Analizza file CAM - rileva formato automaticamente')
    parser.add_argument('--file', required=True)
    args = parser.parse_args()
    if not os.path.exists(args.file):
        print(f"File non trovato: {args.file}"); sys.exit(1)
    r = analizza_file(args.file)
    sw  = r.get('software_rilevato','?')
    ver = r.get('versione_rilevata','?')
    par = r.get('parser_usato','?')
    print(f"\nFile:     {os.path.basename(r['filepath'])}")
    print(f"Software: {sw} {ver}  (parser: {par})")
    print(f"Utensili: {r['num_righe']}  |  Colonne: {r['num_colonne']}")
    if r.get('extra_info'):
        for k,v in r['extra_info'].items():
            print(f"Extra:    {v}")
    print(f"\nMappatura ({len(r['mapping'])} campi su 12 possibili):")
    for campo, info in r['mapping'].items():
        print(f"  {info['colonna_file']:35} -> {campo:25} [{info['confidenza']}]")
    if r['valori_categoria']:
        print("\nValori tipo utensile rilevati:")
        for campo, vals in r['valori_categoria'].items():
            for vf, vm in list(vals.items())[:8]:
                print(f"  {vf:15} -> {vm}")
