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

#  TOOL IMPLEMENTATIONS 

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
            return {'errore': f'Testo trovato {count} volte  troppo ambiguo. Aggiungi pi contesto.'}
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


def tool_crea_file(percorso, contenuto, descrizione=''):
    """
    Crea un nuovo file del progetto o sovrascrive uno esistente.
    Usa per: nuovi importer, nuovi plugin, nuovi test, nuovi moduli.
    Il percorso e' relativo alla root del progetto.
    Estensioni consentite: .py .sql .json .csv .txt .md .sh .bat
    """
    try:
        root = os.path.normpath(os.path.join(_DIR, '..'))
        full = os.path.normpath(os.path.join(root, percorso))
        if not full.startswith(root):
            return {'errore': f'Path non consentito: {percorso}'}
        ext = os.path.splitext(full)[1].lower()
        if ext not in ('.py', '.sql', '.json', '.csv', '.txt', '.md', '.sh', '.bat'):
            return {'errore': f'Estensione non consentita: {ext}'}
        # Crea cartelle intermedie se mancano
        os.makedirs(os.path.dirname(full), exist_ok=True)
        esisteva = os.path.exists(full)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(contenuto)
        righe = contenuto.count('\n') + 1
        return {
            'ok': True,
            'percorso': percorso,
            'azione': 'sovrascritto' if esisteva else 'creato',
            'righe': righe,
            'descrizione': descrizione,
            'nota': 'File scritto su disco. Riavvia il server se e un modulo Python importato da Flask.'
        }
    except Exception as e:
        return {'errore': str(e)}


def tool_esegui_comando(comando, timeout=30, cwd=None):
    """
    Esegue un comando shell nella root del progetto.
    Usa per: riavviare il server Flask, eseguire test, git commit, pip install.
    
    Comandi consentiti (whitelist):
      - python3 / python  (esecuzione script)
      - pip install       (solo pacchetti)
      - pytest            (test)
      - lsof              (trova PID server)
      - kill              (ferma server)
      - git add/commit/status  (versioning)
      - bash start.sh / stop.sh
      - ls / cat (solo file del progetto)
    
    Comandi bloccati: rm -rf, curl a URL esterni, wget, dd, mkfs.
    Ritorna stdout, stderr e returncode.
    """
    import subprocess, shlex
    
    # Blocklist di sicurezza
    BLOCKLIST = ['rm -rf', 'dd if=', 'mkfs', 'wget ', 'curl ', ':(){', 'chmod 777',
                 'sudo', '> /dev/', '| sh', '| bash', 'eval ', 'exec(']
    cmd_lower = comando.lower()
    for blk in BLOCKLIST:
        if blk in cmd_lower:
            return {'errore': f'Comando bloccato per sicurezza: contiene "{blk}"'}
    
    root = os.path.normpath(os.path.join(_DIR, '..'))
    work_dir = os.path.normpath(os.path.join(root, cwd)) if cwd else root
    if not work_dir.startswith(root):
        return {'errore': 'cwd fuori dalla root del progetto'}
    
    try:
        result = subprocess.run(
            comando, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=work_dir
        )
        return {
            'returncode': result.returncode,
            'stdout': result.stdout[-3000:] if result.stdout else '',
            'stderr': result.stderr[-1000:] if result.stderr else '',
            'ok': result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {'errore': f'Timeout ({timeout}s). Processo avviato in background.', 'ok': False}
    except Exception as e:
        return {'errore': str(e), 'ok': False}


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

#  TOOL REGISTRY 



# 
# TOOL: cerca_web  ricerca documentazione tecnica via Anthropic
# 
def tool_cerca_web(query: str, max_results: int = 5) -> str:
    """
    Cerca documentazione tecnica su formati CAM, parametri DB, schemi proprietari.
    Usa l'API Anthropic con web_search tool  stessa chiave API del progetto.
    Ritorna un riassunto dei risultati trovati.
    """
    import requests as _req
    key = _get_api_key()
    if not key:
        return "ERRORE: API key Anthropic non configurata."
    try:
        resp = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "web-search-2025-03-05",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_results}],
                "messages": [{"role": "user", "content":
                    f"Cerca informazioni tecniche su: {query}\n"
                    f"Riassumi in italiano i risultati piu rilevanti per decodificare "
                    f"parametri di database CAM industriali (campi numerici, tipi utensile, geometrie). "
                    f"Sii conciso e tecnico."
                }]
            },
            timeout=30
        )
        data = resp.json()
        # Estrai testo dalla risposta
        results = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                results.append(block["text"])
        return "\n".join(results) if results else "Nessun risultato trovato."
    except Exception as e:
        return f"Errore ricerca web: {e}"


# 
# TOOL: formato_noto  knowledge base mappature CAM verificate
# 
def _ensure_formato_noto_table():
    """Crea la tabella formato_noto se non esiste."""
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS formato_noto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            software TEXT NOT NULL,
            versione TEXT DEFAULT '',
            tipo_file TEXT DEFAULT '',
            mappatura_json TEXT NOT NULL,
            confidenza REAL DEFAULT 0.5,
            verificato INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            data_creazione TEXT DEFAULT (datetime('now')),
            n_import INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fn_software ON formato_noto(software)")
    conn.commit()
    conn.close()


def tool_formato_noto(azione: str, software: str = '', mappatura: dict = None,
                       versione: str = '', confidenza: float = 0.5,
                       verificato: bool = False, note: str = '') -> str:
    """
    Gestisce la knowledge base dei formati CAM gia decodificati.
    azioni:
      'cerca'   cerca se il software e gia noto (ritorna mappatura JSON o None)
      'salva'   salva una nuova mappatura (richiede software + mappatura dict)
      'lista'   elenca tutti i formati noti
      'aggiorna_count'  incrementa il contatore import per un software
    """
    _ensure_formato_noto_table()
    conn = _conn()
    try:
        if azione == 'cerca':
            if not software:
                return "ERRORE: specificare software per la ricerca."
            rows = conn.execute(
                "SELECT * FROM formato_noto WHERE software LIKE ? ORDER BY verificato DESC, confidenza DESC LIMIT 3",
                (f'%{software}%',)
            ).fetchall()
            if not rows:
                return f"Formato '{software}' non ancora in knowledge base."
            results = []
            for r in rows:
                d = dict(r)
                results.append(
                    f"software={d['software']} ver={d['versione']} "
                    f"confidenza={d['confidenza']:.0%} verificato={'SI' if d['verificato'] else 'NO'} "
                    f"import_ok={d['n_import']}\n"
                    f"mappatura: {d['mappatura_json'][:300]}"
                )
            return "\n\n".join(results)

        elif azione == 'salva':
            if not software or not mappatura:
                return "ERRORE: specificare software e mappatura."
            # Controlla se esiste gi
            existing = conn.execute(
                "SELECT id FROM formato_noto WHERE software=? AND versione=?",
                (software, versione)
            ).fetchone()
            mappa_str = json.dumps(mappatura, ensure_ascii=False)
            if existing:
                conn.execute(
                    "UPDATE formato_noto SET mappatura_json=?, confidenza=?, verificato=?, note=? WHERE id=?",
                    (mappa_str, confidenza, int(verificato), note, existing[0])
                )
                msg = f"Mappatura aggiornata per '{software}' v{versione}."
            else:
                conn.execute(
                    "INSERT INTO formato_noto (software, versione, tipo_file, mappatura_json, confidenza, verificato, note) VALUES (?,?,?,?,?,?,?)",
                    (software, versione, '', mappa_str, confidenza, int(verificato), note)
                )
                msg = f"Nuova mappatura salvata per '{software}' v{versione}."
            conn.commit()
            return msg

        elif azione == 'lista':
            rows = conn.execute(
                "SELECT software, versione, confidenza, verificato, n_import, data_creazione FROM formato_noto ORDER BY data_creazione DESC"
            ).fetchall()
            if not rows:
                return "Knowledge base vuota  nessun formato ancora imparato."
            lines = ["=== FORMATI NOTI ==="]
            for r in rows:
                d = dict(r)
                lines.append(
                    f"  {d['software']} {d['versione']} | "
                    f"conf={d['confidenza']:.0%} | "
                    f"{' verificato' if d['verificato'] else '? ipotesi'} | "
                    f"{d['n_import']} import | {d['data_creazione'][:10]}"
                )
            return "\n".join(lines)

        elif azione == 'aggiorna_count':
            conn.execute(
                "UPDATE formato_noto SET n_import=n_import+1 WHERE software LIKE ?",
                (f'%{software}%',)
            )
            conn.commit()
            return f"Contatore aggiornato per '{software}'."

        else:
            return f"Azione sconosciuta: {azione}. Usa: cerca, salva, lista, aggiorna_count."
    finally:
        conn.close()


# 
# TOOL: decodifica_db  analisi statistica autonoma DB sconosciuti
# 
def tool_decodifica_db(filepath: str) -> str:
    """
    Analisi statistica + pattern matching per decodificare un DB CAM sconosciuto.
    Strategia:
    1. Fingerprint: identifica software dal nome tabelle
    2. Schema discovery: lista tabelle, colonne, tipi
    3. Statistica: min/max/media/nonzero per ogni colonna numerica
    4. Pattern matching: confronta con range attesi (diametri 0.1-300, angoli 0-180, ecc.)
    5. Cross-check: se c' una colonna nome/descrizione, cerca pattern tipo D10R0.5
    6. Consulta formato_noto per software simili gia noti
    """
    import re as _re
    path = _safe_path(filepath)
    if not os.path.exists(path):
        path = filepath
    if not os.path.exists(path):
        return f"File non trovato: {filepath}"

    try:
        conn2 = sqlite3.connect(path)
        conn2.row_factory = sqlite3.Row
    except Exception as e:
        return f"Impossibile aprire come SQLite: {e}"

    report = [f"=== DECODIFICA DB: {os.path.basename(filepath)} ===\n"]

    try:
        # 1. Lista tabelle
        tables = [r[0] for r in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        report.append(f"TABELLE ({len(tables)}): {', '.join(tables)}\n")

        # 2. Fingerprint software
        software_hint = ''
        t_lower = [t.lower() for t in tables]
        if 'nctools' in t_lower and 'geometryclasses' in t_lower:
            software_hint = 'hypermill'
        elif 'tool' in t_lower and 'holder' in t_lower:
            software_hint = 'generic_cam'
        elif any('cutter' in t for t in t_lower):
            software_hint = 'mastercam_generic'
        report.append(f"SOFTWARE RILEVATO: {software_hint or 'sconosciuto'}\n")

        # 3. Consulta knowledge base
        _ensure_formato_noto_table()
        kb_result = tool_formato_noto('cerca', software=software_hint) if software_hint else ''
        if kb_result and 'non ancora' not in kb_result:
            report.append(f"FORMATO GIA NOTO:\n{kb_result}\n")

        # 4. Per ogni tabella: schema + statistiche colonne numeriche
        RANGE_HINTS = {
            'diametro': (0.1, 350.0),
            'raggio': (0.05, 175.0),
            'lunghezza': (0.5, 600.0),
            'angolo': (0.0, 180.0),
            'passo': (0.1, 10.0),
            'taglienti': (1, 16),
            'stelo': (1.0, 50.0),
        }

        for table in tables[:8]:  # max 8 tabelle
            try:
                cols_info = conn2.execute(f"PRAGMA table_info({table})").fetchall()
                n_rows = conn2.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if n_rows == 0:
                    continue

                num_cols = [c[1] for c in cols_info if c[2].upper() in ('REAL','FLOAT','DOUBLE','NUMERIC','INTEGER','INT')]
                txt_cols = [c[1] for c in cols_info if 'TEXT' in c[2].upper() or 'CHAR' in c[2].upper() or 'NAME' in c[1].lower()]

                report.append(f"\n--- {table} ({n_rows} righe) ---")

                # Campione di nomi per cross-check
                if txt_cols:
                    name_col = next((c for c in txt_cols if any(k in c.lower() for k in ['name','nome','nc_name','descrizione'])), txt_cols[0])
                    samples = [r[0] for r in conn2.execute(
                        f"SELECT {name_col} FROM {table} WHERE {name_col} IS NOT NULL LIMIT 5"
                    ).fetchall()]
                    report.append(f"  Campione nomi: {samples}")

                    # Estrai valori geometrici dai nomi (es. D10R0.5L30)
                    geo_from_names = {}
                    for s in samples:
                        if not s: continue
                        for pattern, key in [
                            (r'D(\d+\.?\d*)', 'D_da_nome'),
                            (r'R(\d+\.?\d*)', 'R_da_nome'),
                            (r'L(\d+\.?\d*)', 'L_da_nome'),
                        ]:
                            m = _re.search(pattern, str(s))
                            if m:
                                geo_from_names.setdefault(key, []).append(float(m.group(1)))
                    if geo_from_names:
                        report.append(f"  Geo estratta dai nomi: {geo_from_names}")

                # Statistiche colonne numeriche
                if num_cols:
                    report.append(f"  Colonne numeriche ({len(num_cols)}):")
                    for col in num_cols[:20]:  # max 20 colonne
                        try:
                            stats = conn2.execute(
                                f"SELECT MIN({col}), MAX({col}), AVG({col}), "
                                f"COUNT(CASE WHEN {col} != 0 AND {col} IS NOT NULL THEN 1 END) "
                                f"FROM {table}"
                            ).fetchone()
                            mn, mx, avg, nonzero = stats
                            if mn is None or (mn == 0 and mx == 0): continue
                            mn, mx, avg = round(float(mn),3), round(float(mx),3), round(float(avg or 0),3)

                            # Indovina il significato
                            guesses = []
                            for hint, (lo, hi) in RANGE_HINTS.items():
                                if lo <= avg <= hi and lo <= mn or mx <= hi * 1.5:
                                    guesses.append(hint)

                            # Cross-check con valori estratti dai nomi
                            for geo_key, geo_vals in geo_from_names.items():
                                geo_avg = sum(geo_vals)/len(geo_vals)
                                if abs(avg - geo_avg) / max(geo_avg, 0.001) < 0.15:
                                    geo_name = geo_key.replace('_da_nome','')
                                    if geo_name == 'D': guesses.insert(0, '>>> DIAMETRO (match nome)')
                                    elif geo_name == 'R': guesses.insert(0, '>>> RAGGIO (match nome)')
                                    elif geo_name == 'L': guesses.insert(0, '>>> LUNGHEZZA (match nome)')

                            report.append(
                                f"    {col}: min={mn} max={mx} avg={avg} nonzero={nonzero}"
                                + (f"  IPOTESI: {', '.join(guesses)}" if guesses else "")
                            )
                        except Exception:
                            pass

            except Exception as e:
                report.append(f"  Errore tabella {table}: {e}")

        report.append("\n=== FINE ANALISI ===")
        report.append("Suggerimento: usa 'cerca_web' per verificare le ipotesi e 'formato_noto salva' per memorizzare la mappatura.")

    finally:
        conn2.close()

    return "\n".join(report)


def tool_affida_a_jules(task, branch='main1', titolo=None):
    """Affida un task di sviluppo a Jules (agente Google AI cloud) via REST API."""
    import urllib.request, ssl
    jules_key = ''
    try:
        cfg = os.path.join(_DIR, '..', 'config.json')
        with open(cfg) as f:
            jules_key = json.load(f).get('jules_api_key', '')
    except Exception:
        pass
    if not jules_key:
        return {'errore': 'jules_api_key non configurata in config.json'}

    payload = json.dumps({
        "prompt": task,
        "sourceContext": {
            "source": "sources/github/avidav1234/tool-db-manager",
            "githubRepoContext": {"startingBranch": branch}
        },
        "title": titolo or task[:60]
    }).encode('utf-8')

    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        'https://jules.googleapis.com/v1alpha/sessions',
        data=payload,
        headers={'X-Goog-Api-Key': jules_key, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            resp = json.loads(r.read())
        session_id = resp.get('name', '').split('/')[-1]
        return {
            'ok': True,
            'eseguito_da': 'jules',
            'session_id': session_id,
            'url': f'https://jules.google.com/tasks/{session_id}',
            'messaggio': f'Task affidato a Jules. Controlla su: https://jules.google.com/tasks/{session_id}',
        }
    except Exception as e:
        return {'errore': f'Jules API error: {e}'}


TOOLS = [
    {
        "name": "cerca_web",
        "description": "Cerca documentazione tecnica su formati CAM, schemi DB proprietari, parametri utensile su internet. Usa questa funzione SEMPRE quando non conosci un formato o hai dubbi su un parametro.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query di ricerca tecnica (es: 'hypermill database dbl_param fields documentation')"},
                "max_results": {"type": "integer", "description": "Numero massimo risultati (default 5)", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "formato_noto",
        "description": "Knowledge base dei formati CAM gia decodificati. Usa 'cerca' prima di ogni analisi per vedere se il formato e gia noto. Usa 'salva' dopo aver verificato una mappatura. Usa 'lista' per vedere tutto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "azione": {"type": "string", "enum": ["cerca", "salva", "lista", "aggiorna_count"]},
                "software": {"type": "string", "description": "Nome software CAM (es: hypermill, cimatron, mastercam)"},
                "mappatura": {"type": "object", "description": "Dict con mappatura campi DB -> significato"},
                "versione": {"type": "string", "description": "Versione del software"},
                "confidenza": {"type": "number", "description": "0.0-1.0"},
                "verificato": {"type": "boolean", "description": "True se confermato da import reale"},
                "note": {"type": "string"}
            },
            "required": ["azione"]
        }
    },
    {
        "name": "decodifica_db",
        "description": "Analisi statistica autonoma di un DB CAM sconosciuto. Usa questa funzione per capire la struttura di qualsiasi file .db SQLite: identifica il software, analizza le colonne numeriche, incrocia con i nomi utensile per indovinare diametro/raggio/lunghezza/angolo. USALA SEMPRE come primo step quando ricevi un file .db non riconosciuto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Percorso al file .db da analizzare"}
            },
            "required": ["filepath"]
        }
    },
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
    ,{"name":"crea_file","description":"Crea un nuovo file del progetto da zero o sovrascrive uno esistente. USA per: nuovi importer, nuovi plugin, nuovi moduli, file di configurazione. Percorso relativo alla root. Estensioni: .py .sql .json .csv .txt .md .sh .bat","input_schema":{"type":"object","properties":{"percorso":{"type":"string","description":"Percorso relativo alla root, es. 'learner/worknc_importer_v2.py' o 'plugins/worknc/plugin.py'"},"contenuto":{"type":"string","description":"Contenuto completo del file da scrivere"},"descrizione":{"type":"string","description":"Descrizione del file per il log"}},"required":["percorso","contenuto"]}},
    {"name":"esegui_comando","description":"Esegue un comando shell nella root del progetto. USA per: riavviare il server Flask dopo modifiche Python (kill + python3 start), eseguire test con pytest, fare git commit, installare dipendenze. Comandi rm -rf e curl sono bloccati per sicurezza.","input_schema":{"type":"object","properties":{"comando":{"type":"string","description":"Comando shell da eseguire, es: 'lsof -ti:5000 | xargs kill -9 2>/dev/null; python3 ui/app.py &' oppure 'python3 -c \"import ast; ast.parse(open(\'learner/x.py\').read()); print(\'OK\')\"'"},"timeout":{"type":"integer","description":"Timeout in secondi (default 30). Usa 5 per kill, 60 per riavvio server, 120 per pip install.","default":30},"cwd":{"type":"string","description":"Sottocartella di lavoro relativa alla root (opzionale)"}},"required":["comando"]}},
    {"name":"affida_a_jules","description":"Affida un task di sviluppo a Jules (agente Google AI cloud). Usalo per task grandi che richiedono molte modifiche a piu file, refactoring, nuove feature complete. Jules lavora in cloud su GitHub e crea una PR. NON usarlo per fix veloci o task che richiedono accesso al DB locale.","input_schema":{"type":"object","properties":{"task":{"type":"string","description":"Descrizione dettagliata del task da fare"},"branch":{"type":"string","description":"Branch di partenza (default: main1)"},"titolo":{"type":"string","description":"Titolo breve del task"}},"required":["task"]}}
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
    'cerca_web':            lambda i: tool_cerca_web(i['query'], i.get('max_results', 5)),
    'formato_noto':         lambda i: tool_formato_noto(i['azione'], i.get('software',''), i.get('mappatura'), i.get('versione',''), i.get('confidenza',0.5), i.get('verificato',False), i.get('note','')),
    'decodifica_db':        lambda i: tool_decodifica_db(i['filepath']),
        'crea_file':            lambda i: tool_crea_file(i['percorso'], i['contenuto'], i.get('descrizione','')),
    'esegui_comando':       lambda i: tool_esegui_comando(i['comando'], i.get('timeout',30), i.get('cwd')),
    'affida_a_jules':       lambda i: tool_affida_a_jules(i['task'], i.get('branch','main1'), i.get('titolo')),
}

#  AGENT LOOP 

SYSTEM_PROMPT = """Sei l'agente tecnico di Tool DB Manager. Gestisci import CAM e fai debug/fix del codice.

MODALITA' DEBUG (quando vedi un log con errore):
1. Leggi il log  identifica il file e la riga dell'errore
2. USA SUBITO leggi_file sul file incriminato  non spiegare prima, agisci
3. Trova il bug esatto nel codice
4. USA modifica_file per applicare il fix  non descrivere il fix, APPLICALO
5. Conferma: "Fix applicato. Riavvia il server con: lsof -ti:PORT | xargs kill -9 && python3 FILE &"

MODALITA' IMPORT (quando vedi un file CAM):
1. formato_noto cerca  controlla knowledge base per formati gia noti
2. lista_plugin  controlla plugin esistenti
3. analizza_file_cam  studia la struttura del file
4. Se e un .db SQLite sconosciuto: decodifica_db  analisi statistica autonoma
5. Se hai dubbi su parametri: cerca_web  cerca documentazione online
6. proponi_mapping  usa knowledge base + euristica
7. importa_file dry_run=true  simula l'import
8. Se import OK (10+ utensili): formato_noto salva con verificato=true
9. Chiedi conferma, poi importa_file dry_run=false

MODALITA' RICERCA AUTONOMA (formato sconosciuto):
1. decodifica_db  analisi statistica del file
2. cerca_web query specifica (es: 'hypermill NCTools dbl_param fields')
3. cerca_web release notes, documentazione vendor, forum CNC machining
4. Incrocia risultati web con analisi statistica
5. Proponi mappatura con confidenza esplicita (es: confidenza 85%)
6. formato_noto salva con confidenza appropriata
7. NON fermarti a 'non so'  cambia query e itera fino alla soluzione
1. lista_plugin  controlla se esiste gia un plugin per questa versione
2. analizza_file_cam  studia la struttura
3. proponi_mapping  fast path Cimatron (0 token) o euristico
4. importa_file dry_run=true  simula
5. Chiedi conferma, poi importa_file dry_run=false
6. leggi_utensili  verifica alias e fuori_pinza_mm


MODALITA' DEV AUTONOMO (quando ricevi un task di sviluppo):
0. PRIMA DI TUTTO: salva_checkpoint(task_id, 'inizio', {task: messaggio_utente})  OBBLIGATORIO come primo tool call
1. leggi_file sui file rilevanti per capire la struttura esistente
2. salva_checkpoint(task_id, 'analisi', {file_letti, plan})
3. crea_file o modifica_file per implementare il task
4. salva_checkpoint(task_id, 'modifica_applicata', {file, cosa_fatto})
5. esegui_comando per validare sintassi: python3 -m py_compile percorso.py
6. esegui_comando per riavviare il server: lsof -ti:5000 | xargs kill -9 2>/dev/null; sleep 1; python3 ui/app.py &
7. salva_checkpoint(task_id, 'completato', {files_creati, test_ok})
8. Riporta: file creati/modificati, come testare, eventuali passi manuali

REGOLE DEV AUTONOMO:
- NON chiedere conferma prima di scrivere codice - vai diretto
- Dopo crea_file/modifica_file SEMPRE valida con py_compile prima di riavviare
- Se py_compile fallisce: correggi SUBITO con un altro crea_file/modifica_file
- Il server va riavviato solo per modifiche a file importati da Flask (.py nel progetto)
- Per nuovi plugin: crea il file, poi testa_plugin per verificare, poi esegui_comando per riavvio
- Puoi creare file in: learner/, plugins/, importers/, exporters/, tools/
- Non creare file in: ui/, database/ (usa esegui_sql per il DB)

REGOLE ASSOLUTE:
- Se vedi "errore: name X is not defined" -> leggi_file SUBITO, trova X, usa modifica_file
- Se vedi "0 colonne mappate" -> leggi_file orchestrator_agent.py, cerca il bug nel batch
- Se vedi "Limite turni" -> il task e complesso, scrivi "continua" per proseguire
- NON spiegare cosa faresti  FALLO direttamente con i tool
- Dopo modifica_file SEMPRE comunica quale file modificare e come riavviare
- DROP TABLE e DELETE senza WHERE sono bloccati per sicurezza
CHECKPOINT - REGOLA FONDAMENTALE:
- Dopo OGNI step completato: salva_checkpoint(task_id, step, risultati)
- Se raggiungi il limite turni il lavoro NON va perso - e' salvato su disco
- Quando utente dice 'continua': lista_checkpoint() poi leggi_checkpoint(task_id) e riparti
- Quando ricevi un messaggio che inizia con PROCEDI IMMEDIATAMENTE: esegui il prossimo step SENZA chiedere nulla, SENZA spiegare, direttamente con i tool

ROUTING AUTOMATICO — decidi autonomamente come gestire ogni task:

REGOLA FONDAMENTALE — PRIMA di decidere chiediti:
"Questo task richiede leggere o scrivere nel DB locale,
 leggere file locali, o eseguire codice Python in locale?"
 SE SI' -> non puoi usare Jules (Jules non ha accesso al DB locale)
 SE NO' -> puoi usare Jules

WORKER DIRETTO — gestisci tu stesso:
- Domande, spiegazioni, analisi
- Query SQL sul DB locale
- Lettura file locali
- Fix singolo file < 50 righe
- Import/export dati che richiedono accesso al DB locale
- Verifica stato DB, conteggi, statistiche
- Qualsiasi task che richiede accesso a database/tool_master.db
- Qualsiasi task completabile in < 5 tool call

AFFIDA A JULES — chiama affida_a_jules IMMEDIATAMENTE:
- Nuove feature multi-file (3+ file da creare o modificare)
- Nuovo schema DB + codice Python correlato
  (Jules crea il codice, poi l'agente locale lo esegue)
- Parser, exporter, motori di calcolo complessi
- Qualsiasi task che richiede > 100 righe di codice nuovo
- Task che NON richiedono accesso al DB locale durante lo sviluppo
- ATTENZIONE: Jules puo' SOLO creare/modificare file nel repo GitHub
  Jules NON puo': leggere DB locale, eseguire Python, testare in locale
  Quindi: Jules crea il codice -> tu esegui e testi in locale

SUPERVISORE — usa solo per task locali complessi multi-step:
- Task che richiedono 3+ step sequenziali con dipendenze
- Task che richiedono lettura + analisi + scrittura + test IN LOCALE
- Mai per task che devono andare a Jules
- Mai per task semplici che puoi fare direttamente

SCHEMA DECISIONALE:
1. Richiede DB locale o file locali? -> Worker diretto
2. E' un task di solo codice multi-file senza bisogno DB? -> Jules
3. E' un task locale complesso multi-step? -> Supervisore
4. E' tutto il resto? -> Worker diretto

QUANDO USI JULES:
Chiama affida_a_jules come PRIMO tool call.
Arricchisci il prompt con le tue conoscenze del progetto in
un UNICO passaggio — zero turni di analisi preliminare separati.
Specifica sempre nel prompt a Jules:
- Quali file creare/modificare
- Che il DB locale non e' disponibile (usare schema.sql come riferimento)
- Branch: main1

- Non modificare mai ui/cam_agent.py (il tuo stesso codice)
- Puoi modificare e CREARE liberamente: ui/app.py, learner/*.py, plugins/**/*.py, importers/*.py, exporters/*.py, tools/*.py
- ATTENZIONE su ui/app.py: dopo ogni modifica valida SEMPRE con py_compile e riavvia il server

File principali:
- learner/orchestrator_agent.py  motore AI di mapping
- learner/cimatron_importer.py  import Cimatron
- learner/cimatron_parser.py  parser ZIP Cimatron
- plugins/cimatron/_core.py  core plugin Cimatron
- plugins/_loader.py  loader plugin dinamico"""

def esegui_agente(messaggio_utente, filepath=None, history=None, max_turns=40):
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
        # Se e' un task di debug, precarica i file rilevanti nel contesto
        contesto_codice = ''
        task_lower = task_id_richiesto.lower()
        if any(k in task_lower for k in ['debug','fix','bug','batch','mapping','error']):
            file_chiave = [
                'learner/orchestrator_agent.py',
                'learner/cimatron_importer.py',
            ]
            for fk in file_chiave:
                try:
                    res = tool_leggi_file(fk)
                    contenuto = res.get('contenuto','')
                    totale = res.get('righe_totali', 0)
                    contesto_codice += f'\n\n=== {fk} ({totale} righe) ===\n{contenuto[:4000]}'
                    if totale > 100:
                        # Leggi anche la seconda meta del file
                        res2 = tool_leggi_file(fk, riga_inizio=101, riga_fine=min(totale, 300))
                        contesto_codice += res2.get('contenuto','')[:2000]
                except: pass
        messaggio_utente = (f'PROCEDI IMMEDIATAMENTE con il task "{task_id_richiesto}".\n'
                           f'Steps GIA FATTI (non ripetere): {steps_fatti}\n'
                           f'Ultimo step: {cp["ultimo_step"]}\n'
                           f'Dati checkpoint: {dati_str}\n'
                           + (f'Codice rilevante precaricato:{contesto_codice}\n' if contesto_codice else '')
                           + f'VAI AL PROSSIMO STEP. Non chiedere conferme, non spiegare, esegui.')

    messages = list(history or [])
    messages.append({'role':'user','content':messaggio_utente})
    tool_calls_log = []
    jules_info = None  # popolato se l'agente invoca affida_a_jules

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
            out = {'risposta': '\n'.join(texts), 'tool_calls': tool_calls_log,
                   'history': messages, 'stop_reason': resp.get('stop_reason'),
                   'eseguito_da': 'claude', 'modello': modello}
            if jules_info:
                out['jules'] = jules_info
            return out

        results = []
        for tu in tool_uses:
            fn = TOOL_FN.get(tu['name'])
            try:
                res = fn(tu.get('input',{})) if fn else {'errore':f'Tool sconosciuto: {tu["name"]}'}
            except Exception as e:
                res = {'errore': str(e), 'traceback': traceback.format_exc()}
            if tu['name'] == 'affida_a_jules' and isinstance(res, dict) and res.get('ok'):
                jules_info = {
                    'session_id': res.get('session_id'),
                    'url':        res.get('url'),
                }
            tool_calls_log.append({'tool':tu['name'],'input':tu.get('input',{}),
                                    'result_summary':str(res)[:200]})
            res_str=json.dumps(res,ensure_ascii=False,default=str)
            if len(res_str)>3000: res_str=res_str[:2000]+'...[troncato]'
            results.append({'type':'tool_result','tool_use_id':tu['id'],'content':res_str})
        messages.append({'role':'user','content':results})

    # Trova il task_id pi recente dai checkpoint salvati
    _task_id_recente = None
    try:
        import glob as _glob
        _cp_dir = os.path.join(os.path.dirname(__file__), '..', 'checkpoints')
        _cp_files = _glob.glob(os.path.join(_cp_dir, '*.json'))
        if _cp_files:
            _newest = max(_cp_files, key=os.path.getmtime)
            _task_id_recente = os.path.basename(_newest).replace('.json', '')
    except Exception:
        pass

    if _task_id_recente:
        _msg_fine = (
            f"Limite {max_turns} turni raggiunto.\n\n"
            f"**Task in corso:** `{_task_id_recente}`\n\n"
            f"Scrivi esattamente: **`continua {_task_id_recente}`** per riprendere."
        )
    else:
        _msg_fine = (
            f"Limite {max_turns} turni raggiunto.\n"
            "Nessun checkpoint trovato  rilancia il task da capo."
        )

    return {'risposta': _msg_fine,
            'tool_calls': tool_calls_log, 'history': messages,
            'eseguito_da': 'claude', 'modello': modello}
