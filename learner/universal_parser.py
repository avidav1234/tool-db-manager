"""
universal_parser.py  v1.0
=========================
Parser universale AI-assisted per qualsiasi file CAM.
Layer 1: rilevamento formato (deterministico)
Layer 2: mapping colonne via Claude AI (singola chiamata)  
Layer 3: mapping euristico fallback
"""
from __future__ import annotations
import csv, io, json, os, re, sys, zipfile
from pathlib import Path
from typing import Any

ISO_FIELDS = {
    'codice_interno':         ('string', 'Codice/nome univoco'),
    'codice_catalogo':        ('string', 'Codice catalogo fornitore'),
    'descrizione':            ('string', 'Descrizione/commento'),
    'tipo':                   ('enum',   'FLAT|BALL|BULL|DRILL|TAP|REAM|TAPER|THREAD|SPOT|FORM'),
    'diametro_mm':            ('float',  'Diametro nominale mm'),
    'raggio_punta_mm':        ('float',  'Raggio punta/corner radius mm'),
    'angolo_punta_gradi':     ('float',  'Angolo punta gradi'),
    'lunghezza_totale_mm':    ('float',  'Lunghezza totale mm'),
    'lunghezza_tagl_mm':      ('float',  'Lunghezza utile/taglio mm'),
    'lunghezza_tagl2_mm':     ('float',  'Lunghezza tagliente secondaria mm'),
    'num_taglienti':          ('int',    'Numero taglienti/flutes'),
    'conico':                 ('bool',   '1=conico 0=cilindrico'),
    'angolo_conico_gradi':    ('float',  'Angolo conicita gradi'),
    'passo_mm':               ('float',  'Passo filettatura mm'),
    'nome_pinza':             ('string', 'Codice portautensile/holder'),
    'fuori_pinza_mm':         ('float',  'Distanza punta->inizio pinza mm (gauge length)'),
    'lungh_presa_mm':         ('float',  'Lunghezza inserimento in pinza mm'),
    'diam_stelo_mm':          ('float',  'Diametro gambo/stelo mm'),
    'vc_default':             ('float',  'Velocita di taglio default m/min'),
    'rotazione_default':      ('float',  'RPM mandrino default'),
    'avanzamento_default':    ('float',  'Avanzamento default mm/min'),
    'fz_default':             ('float',  'Avanzamento per dente mm/z'),
    'passo_z_default':        ('float',  'Passo assiale ap mm'),
    'passo_lat_default':      ('float',  'Passo laterale ae mm'),
    'vita_utensile':          ('int',    'Vita utensile min/colpi'),
    'materiale_tagliente':    ('string', 'HM, HSS, CBN, PKD, Cermet'),
    'rivestimento':           ('string', 'TiAlN, TiCN, DLC, uncoated...'),
    'tecnologia':             ('string', 'Fresatura, Foratura, Filettatura...'),
    'refrigerante':           ('string', 'Through, Flood, Mist, Air, OFF'),
    'dir_rotazione':          ('string', 'CW, CCW'),
    'num_magazzino':          ('int',    'Posizione magazzino'),
    'sito_web':               ('string', 'URL scheda tecnica'),
}

KNOWN_FORMATS = {
    'cimatron':   {'detect': lambda r,e: b'CimatronE' in r or b'Cimatron' in r or b'Utensile' in r or (e=='.zip' and b'Cutters' in r), 'software':'Cimatron'},
    'hypermill':  {'detect': lambda r,e: b'hyperMILL' in r or b'OPEN MIND' in r,  'software':'hyperMILL'},
    'worknc':     {'detect': lambda r,e: b'WorkNC' in r or b'Sescoi' in r,          'software':'WorkNC'},
    'mastercam':  {'detect': lambda r,e: b'Mastercam' in r or b'MCAM' in r,        'software':'Mastercam'},
    'catia':      {'detect': lambda r,e: b'CATIA' in r,                             'software':'CATIA'},
    'nx_siemens': {'detect': lambda r,e: b'Siemens' in r or b'NX_TOOL' in r,      'software':'NX/Siemens'},
}

_SYSTEM = """Sei un esperto di utensili CNC e ISO 13399. Mappa ogni colonna al campo ISO corretto.
Rispondi SOLO con JSON valido, nessun testo extra, niente backtick."""

def _detect_enc(raw):
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'): return 'utf-16'
    if raw[:3] == b'\xef\xbb\xbf': return 'utf-8-sig'
    try:
        import chardet
        r = chardet.detect(raw[:4096])
        if r.get('confidence',0) > 0.65 and r.get('encoding'): return r['encoding']
    except ImportError: pass
    for e in ('utf-8','latin-1','cp1252'):
        try: raw.decode(e); return e
        except: pass
    return 'latin-1'

def _detect_sep(sample):
    return max(('|',';','\t',','), key=lambda s: sample.count(s))

def _cast(v, tipo):
    if v is None or str(v).strip() in ('','nan','None','NULL'): return None
    if tipo == 'float':
        try: return float(str(v).replace(',','.').replace(' ',''))
        except: return None
    if tipo == 'int':
        try: return int(round(float(str(v).replace(',','.'))))
        except: return None
    if tipo == 'bool':
        return 1 if str(v).strip() in ('1','true','True','yes') else 0
    return str(v).strip() or None

def _read_raw(path):
    ext = Path(path).suffix.lower()
    with open(path,'rb') as f: raw = f.read(8192)
    if ext == '.zip':
        try:
            with zipfile.ZipFile(path) as zf:
                csvs = sorted([(zi.file_size,zi.filename) for zi in zf.infolist() if zi.filename.lower().endswith('.csv')], reverse=True)
                if csvs: raw = zf.read(csvs[0][1])[:8192]
        except: pass
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        try: raw = raw.decode('utf-16','replace').encode('utf-8','replace')
        except: pass
    return raw, ext

def _identify_sw(raw, ext):
    for fmt in KNOWN_FORMATS.values():
        try:
            if fmt['detect'](raw, ext): return fmt['software']
        except: pass
    return 'unknown'

def _load_cimatron(path):
    import pandas as pd
    ext = Path(path).suffix.lower()
    csv_files = {}
    if ext == '.zip':
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                fname = name.replace('\\','/').split('/')[-1]
                if fname.lower().endswith('.csv') and 'Cutters' in fname:
                    csv_files[fname] = zf.read(name)
    else:
        with open(path,'rb') as f: csv_files[Path(path).name] = f.read()
    if not csv_files: raise ValueError('Nessun file Cutters nel ZIP Cimatron')
    fname, raw = next(iter(csv_files.items()))
    enc = _detect_enc(raw)
    text = raw.decode(enc,'replace').lstrip('\ufeff')
    lines = text.splitlines()
    data_start = None
    for i, ln in enumerate(lines):
        if i < 5: continue
        if not ln.startswith('//') and not ln.startswith('"//') and not ln.startswith('CimatronE') and ln.strip():
            data_start = i; break
    if data_start is None: return pd.DataFrame()
    header = lines[data_start].split('|')
    rows = []
    for raw_line in lines[data_start+2:]:
        if not raw_line.strip(): continue
        try: row = next(csv.reader(io.StringIO(raw_line), delimiter='|', quoting=csv.QUOTE_NONE, escapechar='\\'))
        except: row = raw_line.split('|')
        rows.append({h.strip():v for h,v in zip(header,row) if h.strip()})
    return pd.DataFrame(rows)

def _load_df(path):
    import pandas as pd
    raw, ext = _read_raw(path)
    sw = _identify_sw(raw, ext)
    if sw == 'Cimatron' or (ext == '.zip' and (b'CimatronE' in raw or b'Utensile' in raw)):
        return _load_cimatron(path), 'Cimatron'
    if ext in ('.xlsx','.xls'):
        df = pd.read_excel(path, header=None, dtype=str)
        best = df.apply(lambda r: r.notna().sum(), axis=1).idxmax()
        df.columns = df.iloc[best].fillna('').astype(str)
        return df.iloc[best+1:].reset_index(drop=True), sw
    enc = _detect_enc(raw)
    text = raw.decode(enc,'replace').lstrip('\ufeff')
    sep = _detect_sep(text[:2000])
    if ext in ('.csv','.txt','.tsv',''):
        try: return pd.read_csv(path, sep=sep, encoding=enc, on_bad_lines='skip', dtype=str, low_memory=False), sw
        except:
            lines = [l for l in text.splitlines() if l.strip() and not l.startswith('//') and not l.startswith('#')]
            return pd.read_csv(io.StringIO('\n'.join(lines)), sep=sep, on_bad_lines='skip', dtype=str), sw
    if ext == '.zip':
        with zipfile.ZipFile(path) as zf:
            csvs = sorted([(zi.file_size,zi.filename) for zi in zf.infolist() if zi.filename.lower().endswith('.csv')], reverse=True)
            if csvs:
                raw_csv = zf.read(csvs[0][1]); enc2 = _detect_enc(raw_csv)
                txt2 = raw_csv.decode(enc2,'replace').lstrip('\ufeff'); sep2 = _detect_sep(txt2[:2000])
                return pd.read_csv(io.StringIO(txt2), sep=sep2, on_bad_lines='skip', dtype=str), sw
    raise ValueError(f'Formato non supportato: {ext}')

def _ai_mapping(df, sw, fname, api_key):
    sample = df.head(15).iloc[:,:80]
    cols = list(sample.columns)
    rows = [{str(c):str(v) for c,v in row.items() if str(v).strip() and str(v)!='nan'} for _,row in sample.iterrows()]
    fields_desc = '\n'.join(f'  {k}: {v[1]} (tipo:{v[0]})' for k,v in ISO_FIELDS.items())
    prompt = f"""Analizza questo file di libreria utensili CAM.
SOFTWARE: {sw}
FILE: {fname}
COLONNE ({len(cols)}): {json.dumps(cols, ensure_ascii=False)}
CAMPIONE ({len(rows)} righe): {json.dumps(rows, ensure_ascii=False, indent=2)}
CAMPI ISO 13399 disponibili:
{fields_desc}

Per ogni colonna mappa al campo ISO piu probabile. Se nessun campo corrisponde usa null.
Rispondi con JSON:
{{"software_rilevato":"...", "versione":null, "unita_principali":"mm", "confidence_globale":0.85,
  "mapping":{{"NomeColonna":{{"campo_iso":"nome_campo","confidence":0.9,"unita":"mm","note":""}}}},
  "colonne_non_mappate":[], "avvertenze":[]}}"""
    import ssl, urllib.request
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    payload = json.dumps({'model':'claude-sonnet-4-20250514','max_tokens':4000,'system':_SYSTEM,'messages':[{'role':'user','content':prompt}]}).encode()
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=payload,
        headers={'Content-Type':'application/json','x-api-key':api_key,'anthropic-version':'2023-06-01'}, method='POST')
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        d = json.loads(resp.read())
    txt = d['content'][0]['text']
    start = txt.find('{'); depth=0
    for i,ch in enumerate(txt[start:],start):
        if ch=='{': depth+=1
        elif ch=='}': 
            depth-=1
            if depth==0:
                try: return json.loads(txt[start:i+1])
                except: break
    return {}

def _heuristic(cols):
    KW = {
        'codice_interno':      ['name','nome','codice','code','id','tool','utensile','werkzeug','bezeichnung'],
        'descrizione':         ['comment','commento','descrizione','description','note','remark','bemerkung'],
        'tipo':                ['type','tipo','punta','shape','form','typ'],
        'diametro_mm':         ['diam','diameter','d_mm','dc','durchm'],
        'raggio_punta_mm':     ['radius','raggio','corner','r_mm','nose_radius','eckenradius'],
        'lunghezza_totale_mm': ['total_length','lungh_tot','lt','overall','gesamt','lc','length'],
        'lunghezza_tagl_mm':   ['flute_length','lungh_tagl','lf','cut_length','tagliente'],
        'num_taglienti':       ['flutes','taglienti','zahne','z_','num_cut','nof'],
        'fuori_pinza_mm':      ['gauge','fuori','stickout','uberhang','lout','l3','lh'],
        'nome_pinza':          ['holder','pinza','portautensile','aufnahme','chuck','collet'],
        'vc_default':          ['vc','cutting_speed','velocita','schnittgeschwindigkeit'],
        'fz_default':          ['fz','feed_per_tooth','vorschub_z','chipload'],
        'avanzamento_default': ['feed','avanzamento','vf','vorschub','feed_rate'],
        'rotazione_default':   ['rpm','speed','n_rpm','drehzahl'],
        'vita_utensile':       ['life','vita','standzeit','tool_life'],
        'materiale_tagliente': ['material','materiale','werkstoff','grade','substrate'],
        'diam_stelo_mm':       ['shank','gambo','stelo','schaft','ds'],
    }
    out = {}
    for col in cols:
        cl = col.lower().strip(); matched=None; best=0
        for campo,kws in KW.items():
            for kw in kws:
                if kw in cl:
                    s = len(kw)/len(cl)
                    if s>best: best=s; matched=campo
        out[col]={'campo_iso':matched,'confidence':round(best*0.8,2) if matched else 0.0,'unita':'mm' if matched and 'mm' in matched else None,'note':'euristico'}
    return out

def _apply(df, mapping):
    col_iso = {col:info['campo_iso'] for col,info in mapping.items() if isinstance(info,dict) and info.get('campo_iso')}
    records=[]
    for _,row in df.iterrows():
        rec={}
        for col,iso in col_iso.items():
            if col not in df.columns: continue
            val=row.get(col)
            if val is None or str(val).strip() in ('','nan','None'): continue
            val=_cast(val, ISO_FIELDS.get(iso,('string',))[0])
            if val is not None: rec[iso]=val
        if rec.get('codice_interno') or rec.get('diametro_mm'): records.append(rec)
    return records

def parse_any_file(path, api_key=None, log_callback=None):
    def log(m):
        if log_callback: log_callback(m)
    if api_key is None: api_key=os.environ.get('ANTHROPIC_API_KEY')
    errori=[]; ai_usato=False
    log(f'[L1] Caricamento: {Path(path).name}')
    df, sw = _load_df(path)
    log(f'[L1] Rilevato: {sw} - {len(df)} righe x {len(df.columns)} colonne')
    if df.empty:
        return {'errore':'File vuoto','records':[],'software':sw}
    mapping={}; conf=0.0
    if api_key:
        log('[L2] AI mapping...')
        try:
            analisi=_ai_mapping(df, sw, Path(path).name, api_key)
            if analisi:
                mapping=analisi.get('mapping',{}); conf=float(analisi.get('confidence_globale',0.7))
                sw=analisi.get('software_rilevato',sw) or sw; ai_usato=True
                log(f'[L2] AI: {len(mapping)} colonne, conf={conf:.2f}, sw={sw}')
            else: errori.append('AI JSON non parsabile')
        except Exception as e:
            errori.append(f'AI: {e}'); log(f'[L2] AI fallita: {e}')
    else:
        log('[L2] No API key - euristico')
    if not mapping:
        mapping=_heuristic(list(df.columns)); conf=0.5
    log('[L3] Normalizzazione...')
    records=_apply(df,mapping)
    log(f'[L3] {len(records)} record prodotti')
    return {'software':sw,'confidence':conf,'mapping':mapping,'records':records,
            'colonne_totali':len(df.columns),'righe_totali':len(df),
            'errori':errori,'ai_usato':ai_usato,'colonne_originali':list(df.columns)}

if __name__=='__main__':
    if len(sys.argv)<2: print('Uso: python universal_parser.py <file> [api_key]'); sys.exit(1)
    res=parse_any_file(sys.argv[1], api_key=sys.argv[2] if len(sys.argv)>2 else None, log_callback=print)
    print(f'\nSOFTWARE: {res["software"]}')
    print(f'CONFIDENCE: {res["confidence"]:.2f}')
    print(f'RECORD: {len(res["records"])}')
    if res['records']: print(json.dumps(res['records'][0],indent=2,ensure_ascii=False))
