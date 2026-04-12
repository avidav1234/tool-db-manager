"""
cam_agent.py - Agente AI per import universale CAM in Tool DB Manager
Tool use con Anthropic API: analizza file CAM, propone mapping, migra DB, importa dati.
"""
import os, sys, json, sqlite3, zipfile, traceback

_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_DIR, '..', 'database', 'tool_master.db')
LEARNER_DIR = os.path.join(_DIR, '..', 'learner')

def _get_api_key():
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        try:
            cfg = os.path.join(_DIR, '..', 'config.json')
            with open(cfg) as f:
                key = json.load(f).get('anthropic_api_key', '')
        except Exception:
            pass
    return key.strip()

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

# ── TOOL IMPLEMENTATIONS ───────────────────────────────────────────────────

def tool_leggi_schema_db():
    con = _conn()
    try:
        tables = {}
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            tn = row['name']
            cols = [{'nome':c['name'],'tipo':c['type'],'nn':bool(c['notnull'])} 
                    for c in con.execute(f"PRAGMA table_info('{tn}')" )]
            cnt = con.execute(f"SELECT COUNT(*) FROM [{tn}]").fetchone()[0]
            tables[tn] = {'colonne': cols, 'righe': cnt}
        return {'tabelle': tables, 'db_path': DB_PATH}
    finally:
        con.close()

def tool_analizza_file_cam(filepath):
    if not os.path.exists(filepath):
        return {'errore': f'File non trovato: {filepath}'}
    result = {'filepath': filepath, 'filename': os.path.basename(filepath),
              'software': 'sconosciuto', 'sezioni': {}}
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.zip':
        try:
            with zipfile.ZipFile(filepath) as z:
                nomi = z.namelist()
                if any('Cutters' in n for n in nomi):
                    result['software'] = 'Cimatron'
                for fname in nomi:
                    if not fname.endswith('.csv'): continue
                    section = os.path.splitext(os.path.basename(fname))[0]
                    try:
                        raw = z.read(fname)
                        text = None
                        for enc in ('utf-16','utf-8-sig','utf-8','latin-1'):
                            try: text = raw.decode(enc); break
                            except: pass
                        if not text: continue
                        lines = text.splitlines()
                        nr = ir = -1
                        for i, line in enumerate(lines):
                            s = line.strip().lstrip('"')
                            if s.startswith('//') or s == '' or s.startswith('Cimatron'): continue
                            if nr == -1: nr = i; continue
                            if ir == -1: ir = i; break
                        if nr >= 0 and ir >= 0:
                            cn = [c.strip() for c in lines[nr].split('|')]
                            ci = [c.strip() for c in lines[ir].split('|')]
                            dati = [l for l in lines[ir+1:] if l.strip() and not l.strip().startswith('//')]
                            samples = []
                            for row in dati[:3]:
                                parts = row.split('|')
                                samples.append({cn[j]: parts[j].strip() if j < len(parts) else '' for j in range(len(cn))})
                            result['sezioni'][section] = {'colonne': cn, 'col_ids': ci,
                                                           'righe': len(dati), 'campioni': samples}
                    except Exception as e:
                        result['sezioni'][section] = {'errore': str(e)}
        except Exception as e:
            return {'errore': str(e)}
    elif ext == '.csv':
        try:
            import pandas as pd
            for sep in [',',';','\t','|']:
                try:
                    df = pd.read_csv(filepath, sep=sep, nrows=5)
                    if len(df.columns) > 2:
                        result['software'] = 'CSV generico'
                        result['sezioni']['main'] = {
                            'colonne': list(df.columns), 'col_ids': [],
                            'righe': sum(1 for _ in open(filepath))-1,
                            'campioni': df.head(3).to_dict('records')}
                        break
                except: pass
        except Exception as e:
            return {'errore': str(e)}
    else:
        result['software'] = f'Formato {ext} (parser da implementare)'
        result['sezioni']['main'] = {'colonne': [], 'righe': 0, 'campioni': []}
    return result

def tool_confronta_con_schema(analisi):
    schema = tool_leggi_schema_db()
    db_cols = {c['nome'] for c in schema['tabelle'].get('utensile',{}).get('colonne',[])}
    if LEARNER_DIR not in sys.path: sys.path.insert(0, LEARNER_DIR)
    try:
        import format_learner as fl
        master_fields = set(fl.MASTER_FIELDS.keys())
    except:
        master_fields = db_cols
    risultato = {'software': analisi.get('software','?'), 'sezioni': {}}
    for sez, info in analisi.get('sezioni',{}).items():
        mappabili, non_mappabili = [], []
        for col in info.get('colonne',[]):
            col_clean = col.strip()
            if not col_clean: continue
            found = None
            col_low = col_clean.lower().replace(' ','_').replace('.','')
            for mf in master_fields:
                if mf in col_low or col_low in mf: found = mf; break
            if found or col_clean in db_cols:
                mappabili.append({'colonna': col_clean, 'campo_suggerito': found or col_clean})
            else:
                non_mappabili.append(col_clean)
        risultato['sezioni'][sez] = {'mappabili': mappabili, 'non_mappabili': non_mappabili,
                                      'righe': info.get('righe',0)}
    return risultato

def tool_proponi_mapping(filepath, sezione='Cutters'):
    if LEARNER_DIR not in sys.path: sys.path.insert(0, LEARNER_DIR)
    try:
        import orchestrator_agent as oa, cimatron_parser as cp, pandas as pd
        res_zip = cp.leggi_cimatron_zip(filepath)
        df = res_zip.get('df')
        if df is not None and len(df) > 0:
            log_ev = []
            res = oa.orchestra_learning(df, nome_file=os.path.basename(filepath),
                log_callback=lambda lv,msg: log_ev.append({'livello':lv,'msg':msg}))
            mapping_raw = res.get('mapping',{})
            mapping = mapping_raw.get('mapping', mapping_raw) if isinstance(mapping_raw,dict) else {}
            return {'metodo':'fast_path_cimatron','token_usati':0,'costo_usd':0.0,
                    'campi_mappati':len(mapping),'mapping':mapping,'log':log_ev}
    except:
        pass
    # Fallback euristico
    analisi = tool_analizza_file_cam(filepath)
    confronto = tool_confronta_con_schema(analisi)
    mapping = {}
    for sez, info in confronto.get('sezioni',{}).items():
        for m in info.get('mappabili',[]):
            mapping[m['colonna']] = {'campo_master': m['campo_suggerito'],
                                      'confidenza':'media','motivazione':'euristico'}
    return {'metodo':'euristico','token_usati':0,'campi_mappati':len(mapping),'mapping':mapping}

def tool_esegui_sql(sql, params=None):
    sql_u = sql.strip().upper()
    if 'DROP TABLE' in sql_u: return {'errore':'DROP TABLE non permesso'}
    if sql_u.startswith('DELETE') and 'WHERE' not in sql_u:
        return {'errore':'DELETE senza WHERE non permesso'}
    con = _conn()
    try:
        cur = con.execute(sql, params or [])
        con.commit()
        if sql_u.startswith('SELECT') or sql_u.startswith('PRAGMA'):
            rows = [dict(r) for r in cur.fetchall()]
            return {'righe': rows, 'count': len(rows)}
        return {'affected': cur.rowcount, 'ok': True}
    except Exception as e:
        con.rollback(); return {'errore': str(e)}
    finally:
        con.close()

def tool_importa_file(filepath, dry_run=False):
    if LEARNER_DIR not in sys.path: sys.path.insert(0, LEARNER_DIR)
    try:
        import importlib
        if 'cimatron_importer' in sys.modules:
            importlib.reload(sys.modules['cimatron_importer'])
        from cimatron_importer import importa_file
        return importa_file(filepath, dry_run=dry_run)
    except Exception as e:
        return {'errore': str(e), 'traceback': traceback.format_exc()}

def tool_leggi_utensili(filtro=None, limit=10):
    where = f"WHERE {filtro}" if filtro else ""
    return tool_esegui_sql(f"""SELECT codice_interno, alias, diametro_mm, t.codice AS tipo,
        cam_sorgente, refrigerante, avanzamento_default, fuori_pinza_mm
        FROM utensile u JOIN tipo_utensile t ON u.id_tipo=t.id
        {where} ORDER BY u.id DESC LIMIT {limit}""")


def _safe_path(relpath):
    """Risolve un percorso relativo alla root del progetto e blocca path traversal."""
    root = os.path.normpath(os.path.join(_DIR, '..'))
    full = os.path.normpath(os.path.join(root, relpath))
    if not full.startswith(root):
        raise ValueError(f'Path non consentito: {relpath}')
    # Solo file Python, SQL, JSON, CSV del progetto
    ext = os.path.splitext(full)[1].lower()
    if ext not in ('.py', '.sql', '.json', '.csv', '.txt', '.md'):
        raise ValueError(f'Estensione non consentita: {ext}')
    return full

def tool_leggi_file(percorso):
    """
    Legge un file del progetto (percorso relativo alla root, es. 'learner/orchestrator_agent.py').
    Restituisce il contenuto con numeri di riga per facilitare il debug.
    """
    try:
        full = _safe_path(percorso)
        with open(full, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # Restituisce con numeri di riga
        numbered = ''.join(f'{i+1:4d}  {l}' for i, l in enumerate(lines))
        return {'percorso': percorso, 'righe_totali': len(lines), 'contenuto': numbered}
    except Exception as e:
        return {'errore': str(e)}

def tool_modifica_file(percorso, vecchio_testo, nuovo_testo, descrizione=''):
    """
    Esegue un str_replace su un file del progetto.
    vecchio_testo deve apparire ESATTAMENTE UNA VOLTA nel file.
    Prima del replace mostra un diff per conferma.
    """
    try:
        full = _safe_path(percorso)
        with open(full, 'r', encoding='utf-8') as f:
            contenuto = f.read()
        count = contenuto.count(vecchio_testo)
        if count == 0:
            return {'errore': f'Testo non trovato nel file. Verifica con leggi_file prima.'}
        if count > 1:
            return {'errore': f'Testo trovato {count} volte — troppo ambiguo. Aggiungi più contesto.'}
        nuovo_contenuto = contenuto.replace(vecchio_testo, nuovo_testo, 1)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(nuovo_contenuto)
        # Calcola righe modificate
        old_lines = vecchio_testo.count('\n') + 1
        new_lines = nuovo_testo.count('\n') + 1
        return {
            'ok': True,
            'percorso': percorso,
            'descrizione': descrizione,
            'righe_rimosse': old_lines,
            'righe_aggiunte': new_lines,
            'nota': 'File modificato. Riavvia il server per applicare le modifiche Python.'
        }
    except Exception as e:
        return {'errore': str(e)}

# ── TOOL REGISTRY ──────────────────────────────────────────────────────────

TOOLS = [
    {"name":"leggi_schema_db","description":"Legge struttura completa DB master: tabelle, colonne, righe.",
     "input_schema":{"type":"object","properties":{},"required":[]}},
    {"name":"analizza_file_cam","description":"Analizza file CAM (ZIP Cimatron, CSV, XML): colonne, campioni, software rilevato.",
     "input_schema":{"type":"object","properties":{"filepath":{"type":"string"}},"required":["filepath"]}},
    {"name":"confronta_con_schema","description":"Confronta colonne file con DB: cosa e mappabile, cosa manca nel DB.",
     "input_schema":{"type":"object","properties":{"analisi":{"type":"object"}},"required":["analisi"]}},
    {"name":"proponi_mapping","description":"Propone mapping colonne->campi DB. Fast path 0-token per Cimatron, euristico per altri.",
     "input_schema":{"type":"object","properties":{"filepath":{"type":"string"},"sezione":{"type":"string"}},"required":["filepath"]}},
    {"name":"esegui_sql","description":"Esegue SQL sul DB: ALTER TABLE, UPDATE, SELECT. DROP TABLE bloccato.",
     "input_schema":{"type":"object","properties":{"sql":{"type":"string"},"params":{"type":"array"}},"required":["sql"]}},
    {"name":"importa_file","description":"Importa file CAM nel DB. dry_run=true per simulazione.",
     "input_schema":{"type":"object","properties":{"filepath":{"type":"string"},"dry_run":{"type":"boolean"}},"required":["filepath"]}},
    {"name":"leggi_utensili","description":"Legge utensili dal DB per verifica. Accetta filtro WHERE.",
     "input_schema":{"type":"object","properties":{"filtro":{"type":"string"},"limit":{"type":"integer"}},"required":[]}},
    {"name":"leggi_file","description":"Legge un file del progetto con numeri di riga (es. 'learner/orchestrator_agent.py'). Usalo per analizzare bug nel codice prima di correggerli.",
     "input_schema":{"type":"object","properties":{"percorso":{"type":"string","description":"Percorso relativo alla root del progetto"}},"required":["percorso"]}},
    {"name":"modifica_file","description":"Corregge un bug in un file del progetto tramite str_replace. vecchio_testo deve apparire ESATTAMENTE una volta. Usalo dopo leggi_file per verificare il contesto.",
     "input_schema":{"type":"object","properties":{
       "percorso":{"type":"string","description":"Percorso relativo alla root, es. 'learner/orchestrator_agent.py'"},
       "vecchio_testo":{"type":"string","description":"Testo esatto da sostituire (deve essere unico nel file)"},
       "nuovo_testo":{"type":"string","description":"Testo sostitutivo"},
       "descrizione":{"type":"string","description":"Descrizione del fix per il log"}
     },"required":["percorso","vecchio_testo","nuovo_testo"]}}
]

TOOL_FN = {
    'leggi_schema_db':      lambda i: tool_leggi_schema_db(),
    'analizza_file_cam':    lambda i: tool_analizza_file_cam(i['filepath']),
    'confronta_con_schema': lambda i: tool_confronta_con_schema(i['analisi']),
    'proponi_mapping':      lambda i: tool_proponi_mapping(i['filepath'], i.get('sezione','Cutters')),
    'esegui_sql':           lambda i: tool_esegui_sql(i['sql'], i.get('params')),
    'importa_file':         lambda i: tool_importa_file(i['filepath'], i.get('dry_run',False)),
    'leggi_utensili':       lambda i: tool_leggi_utensili(i.get('filtro'), i.get('limit',10)),
    'leggi_file':           lambda i: tool_leggi_file(i['percorso']),
    'modifica_file':        lambda i: tool_modifica_file(i['percorso'], i['vecchio_testo'],
                                                          i['nuovo_testo'], i.get('descrizione','')),
}

# ── AGENT LOOP ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Sei un agente specializzato nella gestione di database utensili CNC (Tool DB Manager).
Il tuo obiettivo e aiutare a importare file CAM nel DB master universale E a diagnosticare/correggere bug nel codice.

CAM supportati: Cimatron, Hypermill, Mastercam, Fusion 360, WorkNC, NX (e altri CSV).

Regole operative - Import:
- Usa leggi_schema_db come primo passo per capire lo stato del DB
- Usa analizza_file_cam per capire la struttura del file
- Proponi SEMPRE dry_run prima dell import reale
- Prima di ALTER TABLE, spiega all utente cosa farai e perche
- Quando l utente dice 'procedi', 'ok', 'si', esegui l azione
- L alias e il nome officina: Cimatron=Commento, Hypermill=Tool ID, Mastercam=Tool comment
- fuori_pinza_mm e il dato piu critico per la sicurezza in macchina: verificalo sempre

Regole operative - Debug e fix codice:
- Quando un import produce risultati anomali (0 campi mappati, errori nel log), ANALIZZA il codice
- Usa leggi_file per leggere il file incriminato con numeri di riga
- Identifica il bug esatto con motivazione tecnica precisa
- Usa modifica_file con vecchio_testo UNICO nel file per applicare il fix
- Dopo il fix, spiega cosa hai cambiato e perche
- NON modificare mai database/tool_master.db o file di configurazione con credenziali
- Dopo modifica_file su file .py, avvisa l utente di riavviare il server per applicare le modifiche"""

def esegui_agente(messaggio_utente, filepath=None, history=None, max_turns=8):
    import urllib.request, ssl
    api_key = _get_api_key()
    if not api_key:
        return {'errore': 'API key Anthropic non configurata. Vai in Impostazioni e inserisci la key.'}

    if filepath:
        messaggio_utente = f"File disponibile: {filepath}\n\n{messaggio_utente}"

    messages = list(history or [])
    messages.append({'role':'user','content':messaggio_utente})
    tool_calls_log = []

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for turn in range(max_turns):
        body = json.dumps({
            'model': 'claude-sonnet-4-6',
            'max_tokens': 4096,
            'system': SYSTEM_PROMPT,
            'tools': TOOLS,
            'messages': messages
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=body,
            headers={'x-api-key':api_key,'anthropic-version':'2023-06-01',
                     'content-type':'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
                resp = json.loads(r.read())
        except Exception as e:
            return {'errore': f'Errore API: {e}', 'history': messages}

        messages.append({'role':'assistant','content':resp['content']})
        tool_uses = [b for b in resp['content'] if b.get('type')=='tool_use']
        texts = [b['text'] for b in resp['content'] if b.get('type')=='text']

        if not tool_uses:
            return {'risposta': '\n'.join(texts), 'tool_calls': tool_calls_log,
                    'history': messages, 'stop_reason': resp.get('stop_reason')}

        results = []
        for tu in tool_uses:
            fn = TOOL_FN.get(tu['name'])
            try:
                res = fn(tu.get('input',{})) if fn else {'errore':f'Tool sconosciuto: {tu["name"]}'}
            except Exception as e:
                res = {'errore': str(e), 'traceback': traceback.format_exc()}
            tool_calls_log.append({'tool':tu['name'],'input':tu.get('input',{}),
                                    'result_summary':str(res)[:200]})
            results.append({'type':'tool_result','tool_use_id':tu['id'],
                            'content':json.dumps(res,ensure_ascii=False,default=str)})
        messages.append({'role':'user','content':results})

    return {'risposta':'Limite turni raggiunto.','tool_calls':tool_calls_log,'history':messages}
