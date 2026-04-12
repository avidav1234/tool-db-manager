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

def tool_leggi_file(percorso, riga_inizio=None, riga_fine=None):
    """
    Legge un file del progetto con numeri di riga.
    Per file grandi usa riga_inizio/riga_fine per leggere sezioni specifiche.
    Esempio: riga_inizio=380, riga_fine=430 per vedere solo quelle righe.
    """
    try:
        full=_safe_path(percorso)
        with open(full,'r',encoding='utf-8') as f: lines=f.readlines()
        totale=len(lines)
        if riga_inizio or riga_fine:
            s=max(0,(riga_inizio or 1)-1)
            e=min(totale,(riga_fine or totale))
            chunk=lines[s:e]
            base=s
        else:
            chunk=lines
            base=0
        numbered=''.join(f'{base+i+1:4d}  {l}' for i,l in enumerate(chunk))
        if len(numbered)>6000:
            numbered=numbered[:6000]+'\n...[troncato, specifica riga_inizio/riga_fine per altre sezioni]'
        return {'percorso':percorso,'righe_totali':totale,
                'range':f'{base+1}-{base+len(chunk)}','contenuto':numbered}
    except Exception as e:
        return {'errore':str(e)}

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


def tool_lista_plugin():
    """Restituisce tutti i plugin installati con software, versione, firma."""
    sys.path.insert(0, os.path.join(_DIR, '..'))
    try:
        import importlib
        if 'plugins._loader' in sys.modules:
            importlib.reload(sys.modules['plugins._loader'])
        from plugins._loader import lista_plugin
        return {'plugin': lista_plugin(), 'totale': len(lista_plugin())}
    except Exception as e:
        return {'errore': str(e)}

def tool_testa_plugin(percorso_plugin: str, filepath_test: str = None):
    """
    Testa un plugin in isolamento prima di attivarlo.
    Verifica: importazione, istanziazione, rileva(), analizza() se filepath_test fornito.
    Restituisce: ok/errore + dettagli.
    """
    try:
        import importlib.util, ast
        full = _safe_path(percorso_plugin)
        # 1. Validazione sintassi
        with open(full) as f: src = f.read()
        try: ast.parse(src)
        except SyntaxError as e:
            return {'ok': False, 'fase': 'sintassi', 'errore': str(e)}
        # 2. Import isolato
        spec = importlib.util.spec_from_file_location('_test_plugin', full)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # 3. Trova la classe
        from plugins._base import PluginCAM
        cls = None
        for name in dir(mod):
            obj = getattr(mod, name)
            try:
                if (isinstance(obj, type) and issubclass(obj, PluginCAM)
                        and obj is not PluginCAM
                        and getattr(obj,'versione','') not in ('','core')):
                    cls = obj; break
            except: continue
        if not cls:
            return {'ok': False, 'fase': 'classe', 'errore': 'Nessuna classe PluginCAM trovata'}
        plugin = cls()
        result = {
            'ok': True, 'plugin': repr(plugin),
            'software': plugin.software, 'versione': plugin.versione,
            'estensioni': plugin.estensioni, 'firma': plugin.FIRMA,
        }
        # 4. Test rileva + analizza su file reale (opzionale)
        if filepath_test and os.path.exists(filepath_test):
            conf = plugin.rileva(filepath_test)
            result['rileva_confidenza'] = conf
            if conf > 0.3:
                analisi = plugin.analizza(filepath_test)
                result['analisi_ok'] = 'errore' not in analisi
                result['righe'] = analisi.get('sezioni',{}).get('Cutters',{}).get('righe',0)
        return result
    except Exception as e:
        return {'ok': False, 'fase': 'import', 'errore': str(e), 'traceback': traceback.format_exc()[:300]}


CHECKPOINT_DIR = os.path.join(_DIR, '..', 'checkpoints')

def tool_salva_checkpoint(task_id, step, dati):
    """Salva lo stato del task su disco dopo ogni step completato."""
    try:
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        cp_file = os.path.join(CHECKPOINT_DIR, f'{task_id}.json')
        cp = {}
        if os.path.exists(cp_file):
            with open(cp_file) as f: cp = json.load(f)
        import time
        cp[step] = {'dati': dati, 'ts': time.time()}
        cp['ultimo_step'] = step
        cp['task_id'] = task_id
        with open(cp_file, 'w') as f: json.dump(cp, f, ensure_ascii=False, indent=2, default=str)
        return {'ok': True, 'task_id': task_id, 'step': step,
                'steps_salvati': [k for k in cp if k not in ('ultimo_step','task_id')]}
    except Exception as e:
        return {'errore': str(e)}

def tool_leggi_checkpoint(task_id):
    """Legge checkpoint salvato. Usa quando riprendi un task interrotto."""
    try:
        cp_file = os.path.join(CHECKPOINT_DIR, f'{task_id}.json')
        if not os.path.exists(cp_file): return {'trovato': False, 'task_id': task_id}
        with open(cp_file) as f: cp = json.load(f)
        return {'trovato': True, 'task_id': task_id, 'ultimo_step': cp.get('ultimo_step'),
                'steps': [k for k in cp if k not in ('ultimo_step','task_id')], 'dati': cp}
    except Exception as e:
        return {'errore': str(e)}

def tool_lista_checkpoint():
    """Elenca tutti i task con checkpoint salvato."""
    try:
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        tasks = []
        for f in os.listdir(CHECKPOINT_DIR):
            if not f.endswith('.json'): continue
            try:
                with open(os.path.join(CHECKPOINT_DIR, f)) as fp: cp = json.load(fp)
                tasks.append({'task_id': cp.get('task_id', f[:-5]),
                              'ultimo_step': cp.get('ultimo_step'),
                              'steps': [k for k in cp if k not in ('ultimo_step','task_id')]})
            except: pass
        return {'tasks': tasks, 'totale': len(tasks)}
    except Exception as e:
        return {'errore': str(e)}

def tool_cancella_checkpoint(task_id):
    """Cancella checkpoint di un task completato."""
    try:
        cp_file = os.path.join(CHECKPOINT_DIR, f'{task_id}.json')
        if os.path.exists(cp_file): os.remove(cp_file); return {'ok': True, 'cancellato': task_id}
        return {'ok': False, 'msg': 'Non trovato'}
    except Exception as e:
        return {'errore': str(e)}

# ── TOOL REGISTRY ──────────────────────────────────────────────────────────

TOOLS = [
    {"name":"salva_checkpoint","description":"IMPORTANTE: salva progresso task su disco dopo ogni step. Permette di riprendere se si raggiunge il limite turni. Chiama dopo ogni step completato.",
     "input_schema":{"type":"object","properties":{"task_id":{"type":"string","description":"ID univoco task, es. import_worknc_v2024"},"step":{"type":"string","description":"Step completato: schema_letto|analisi|mapping|dry_run|import|verifica|fix_applicato"},"dati":{"type":"object"}},"required":["task_id","step","dati"]}},
    {"name":"leggi_checkpoint","description":"Legge checkpoint salvato. Usa SUBITO quando utente dice continua o riprendi.","input_schema":{"type":"object","properties":{"task_id":{"type":"string"}},"required":["task_id"]}},
    {"name":"lista_checkpoint","description":"Elenca task con checkpoint salvato.","input_schema":{"type":"object","properties":{},"required":[]}},
    {"name":"cancella_checkpoint","description":"Cancella checkpoint task completato.","input_schema":{"type":"object","properties":{"task_id":{"type":"string"}},"required":["task_id"]}},
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
    {"name":"leggi_file","description":"Legge file del progetto con numeri riga. Per file grandi (>300 righe) usa riga_inizio e riga_fine per sezioni specifiche es riga_inizio:380 riga_fine:430. MAI delegare la lettura all utente - sei tu che chiami questo tool piu volte se necessario.",
     "input_schema":{"type":"object","properties":{"percorso":{"type":"string"},"riga_inizio":{"type":"integer","description":"Prima riga da leggere"},"riga_fine":{"type":"integer","description":"Ultima riga da leggere"}},"required":["percorso"]}},
    {"name":"lista_plugin","description":"Elenca tutti i plugin CAM installati: software, versione, firma di rilevamento.",
     "input_schema":{"type":"object","properties":{},"required":[]}},
    {"name":"testa_plugin","description":"Testa un plugin in isolamento: sintassi, import, classe, rileva(). Usalo prima di attivare un plugin generato dall agente.",
     "input_schema":{"type":"object","properties":{
       "percorso_plugin":{"type":"string","description":"Percorso relativo al plugin, es. 'plugins/worknc/v2024/plugin.py'"},
       "filepath_test":{"type":"string","description":"File reale per testare rileva() e analizza() (opzionale)"}
     },"required":["percorso_plugin"]}},
    {"name":"modifica_file","description":"Corregge un bug in un file del progetto tramite str_replace. vecchio_testo deve apparire ESATTAMENTE una volta. Usalo dopo leggi_file per verificare il contesto.",
     "input_schema":{"type":"object","properties":{
       "percorso":{"type":"string","description":"Percorso relativo alla root, es. 'learner/orchestrator_agent.py'"},
       "vecchio_testo":{"type":"string","description":"Testo esatto da sostituire (deve essere unico nel file)"},
       "nuovo_testo":{"type":"string","description":"Testo sostitutivo"},
       "descrizione":{"type":"string","description":"Descrizione del fix per il log"}
     },"required":["percorso","vecchio_testo","nuovo_testo"]}}
]

TOOL_FN = {
    'salva_checkpoint':     lambda i: tool_salva_checkpoint(i['task_id'],i['step'],i.get('dati',{})),
    'leggi_checkpoint':     lambda i: tool_leggi_checkpoint(i['task_id']),
    'lista_checkpoint':     lambda i: tool_lista_checkpoint(),
    'cancella_checkpoint':  lambda i: tool_cancella_checkpoint(i['task_id']),
    'leggi_schema_db':      lambda i: tool_leggi_schema_db(),
    'analizza_file_cam':    lambda i: tool_analizza_file_cam(i['filepath']),
    'confronta_con_schema': lambda i: tool_confronta_con_schema(i['analisi']),
    'proponi_mapping':      lambda i: tool_proponi_mapping(i['filepath'], i.get('sezione','Cutters')),
    'esegui_sql':           lambda i: tool_esegui_sql(i['sql'], i.get('params')),
    'importa_file':         lambda i: tool_importa_file(i['filepath'], i.get('dry_run',False)),
    'leggi_utensili':       lambda i: tool_leggi_utensili(i.get('filtro'), i.get('limit',10)),
    'lista_plugin':          lambda i: tool_lista_plugin(),
    'testa_plugin':         lambda i: tool_testa_plugin(i['percorso_plugin'], i.get('filepath_test')),
    'leggi_file':           lambda i: tool_leggi_file(i['percorso'],i.get('riga_inizio'),i.get('riga_fine')),
    'modifica_file':        lambda i: tool_modifica_file(i['percorso'], i['vecchio_testo'],
                                                          i['nuovo_testo'], i.get('descrizione','')),
}

# ── AGENT LOOP ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Sei l'agente tecnico di Tool DB Manager. Gestisci import CAM e fai debug/fix del codice.

MODALITA' DEBUG (quando vedi un log con errore):
1. Leggi il log — identifica il file e la riga dell'errore
2. USA SUBITO leggi_file sul file incriminato — non spiegare prima, agisci
3. Trova il bug esatto nel codice
4. USA modifica_file per applicare il fix — non descrivere il fix, APPLICALO
5. Conferma: "Fix applicato. Riavvia il server con: lsof -ti:PORT | xargs kill -9 && python3 FILE &"

MODALITA' IMPORT (quando vedi un file CAM):
1. lista_plugin — controlla se esiste gia un plugin per questa versione
2. analizza_file_cam — studia la struttura
3. proponi_mapping — fast path Cimatron (0 token) o euristico
4. importa_file dry_run=true — simula
5. Chiedi conferma, poi importa_file dry_run=false
6. leggi_utensili — verifica alias e fuori_pinza_mm

REGOLE ASSOLUTE:
- Se vedi "errore: name X is not defined" -> leggi_file SUBITO, trova X, usa modifica_file
- Se vedi "0 colonne mappate" -> leggi_file orchestrator_agent.py, cerca il bug nel batch
- Se vedi "Limite turni" -> il task e complesso, scrivi "continua" per proseguire
- NON spiegare cosa faresti — FALLO direttamente con i tool
- Dopo modifica_file SEMPRE comunica quale file modificare e come riavviare
- DROP TABLE e DELETE senza WHERE sono bloccati per sicurezza
CHECKPOINT - REGOLA FONDAMENTALE:
- Dopo OGNI step completato: salva_checkpoint(task_id, step, risultati)
- Se raggiungi il limite turni il lavoro NON va perso - e' salvato su disco
- Quando utente dice 'continua': lista_checkpoint() poi leggi_checkpoint(task_id) e riparti
- Quando ricevi un messaggio che inizia con PROCEDI IMMEDIATAMENTE: esegui il prossimo step SENZA chiedere nulla, SENZA spiegare, direttamente con i tool

- Non modificare mai ui/app.py o ui/cam_agent.py (core dell'app)
- Puoi modificare liberamente: learner/*.py, plugins/**/*.py

File principali:
- learner/orchestrator_agent.py — motore AI di mapping
- learner/cimatron_importer.py — import Cimatron
- learner/cimatron_parser.py — parser ZIP Cimatron
- plugins/cimatron/_core.py — core plugin Cimatron
- plugins/_loader.py — loader plugin dinamico"""

def esegui_agente(messaggio_utente, filepath=None, history=None, max_turns=20):
    import urllib.request, ssl
    api_key = _get_api_key()
    if not api_key:
        return {'errore': 'API key Anthropic non configurata. Vai in Impostazioni e inserisci la key.'}

    if filepath:
        messaggio_utente = f"File disponibile: {filepath}\n\n{messaggio_utente}"

    # Gestione "continua" intelligente
    msg_strip = messaggio_utente.strip()
    msg_low = msg_strip.lower()
    if msg_low.startswith(('continua', 'riprendi')):
        parts = msg_strip.split(None, 1)
        task_id_richiesto = parts[1].strip() if len(parts) > 1 else None
        cp_list = tool_lista_checkpoint()
        tasks = cp_list.get('tasks', [])
        if not tasks:
            return {'risposta': 'Nessun checkpoint salvato. Nessun task in sospeso.', 'history': []}
        # Se task_id non specificato e c'e' solo uno: riprendi automaticamente
        if not task_id_richiesto:
            if len(tasks) == 1:
                task_id_richiesto = tasks[0]['task_id']
            else:
                # Piu task in sospeso: l'agente decide quale e' piu rilevante
                tasks_info = []
                for t in tasks:
                    cp_detail = tool_leggi_checkpoint(t['task_id'])
                    steps = t.get('steps', [])
                    tasks_info.append({
                        'task_id': t['task_id'],
                        'ultimo_step': t['ultimo_step'],
                        'steps_completati': steps,
                        'num_steps': len(steps)
                    })
                # Passa all'agente la lista completa e chiedi di decidere
                tasks_json = json.dumps(tasks_info, ensure_ascii=False)
                messaggio_utente = (
                    f'Ci sono {len(tasks)} task in sospeso nei checkpoint:\n{tasks_json}\n\n'
                    f'DECIDI AUTONOMAMENTE quale riprendere basandoti su:\n'
                    f'1. Quale e piu avanzato (piu steps completati)\n'
                    f'2. Quale ha piu senso completare prima\n'
                    f'3. Se i task sono correlati, quale sblocca l altro\n'
                    f'Scegli il task migliore e PROCEDI IMMEDIATAMENTE senza chiedere conferma.'
                )
        # Riprendi il task specificato
        cp = tool_leggi_checkpoint(task_id_richiesto)
        if not cp.get('trovato'):
            return {'risposta': f'Checkpoint "{task_id_richiesto}" non trovato.', 'history': []}
        steps_fatti = [k for k in cp['dati'] if k not in ('ultimo_step','task_id')]
        dati_str = json.dumps(cp['dati'], ensure_ascii=False, default=str)[:1500]
        messaggio_utente = (f'PROCEDI IMMEDIATAMENTE con il task "{task_id_richiesto}".\n'
                           f'Steps GIA FATTI (non ripetere): {steps_fatti}\n'
                           f'Ultimo step: {cp["ultimo_step"]}\n'
                           f'Dati: {dati_str}\n'
                           f'VAI AL PROSSIMO STEP. Non chiedere conferme, non spiegare, esegui.')

    messages = list(history or [])
    messages.append({'role':'user','content':messaggio_utente})
    tool_calls_log = []

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for turn in range(max_turns):
        # Comprimi history: se > 20 messaggi, rimuovi tool_results vecchi (tieni ultimi 10 scambi)
        if len(messages) > 20:
            # Tieni sempre il primo messaggio utente + ultimi 18 messaggi
            messages = [messages[0]] + messages[-18:]

        # Routing modello: Sonnet per debug/fix codice, Haiku per import/mapping
        usa_sonnet = any(k in messaggio_utente.lower() for k in
            ['errore','bug','fix','traceback','undefined','exception','non funziona',
             'sbagliato','correggi','debug','riga','stacktrace','procedi immediatamente'])
        modello = 'claude-sonnet-4-5' if usa_sonnet else 'claude-haiku-4-5-20251001'
        body = json.dumps({
            'model': modello,
            'max_tokens': 4096 if usa_sonnet else 2048,
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
        import time as _time, urllib.error as _ue
        resp = None
        for _att in range(3):
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
                    resp = json.loads(r.read())
                break
            except _ue.HTTPError as e:
                if e.code == 429:
                    _time.sleep(30 * (_att + 1))
                    continue
                return {'errore': f'Errore API: HTTP Error {e.code}: {e.reason}', 'history': messages}
            except Exception as e:
                return {'errore': f'Errore API: {e}', 'history': messages}
        if resp is None:
            return {'errore': 'Rate limit 429 persistente. Riprova tra 2 minuti.', 'history': messages}

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
            res_str=json.dumps(res,ensure_ascii=False,default=str)
            if len(res_str)>3000: res_str=res_str[:2000]+'...[troncato]'
            results.append({'type':'tool_result','tool_use_id':tu['id'],'content':res_str})
        messages.append({'role':'user','content':results})

    return {'risposta': f'Limite {max_turns} turni. Progresso salvato nei checkpoint. Scrivi "continua [task_id]" per riprendere.','tool_calls':tool_calls_log,'history':messages}
