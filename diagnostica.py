"""
diagnostica.py
==============
Modulo di diagnostica standalone.
Controlla lo stato di tutti i componenti del sistema:
  - Python e dipendenze
  - Database master
  - Agente AI (API key + connessione reale)
  - Parser Cimatron
  - Profili learner
  - Scheduler

Uso:
    python diagnostica.py            # output testo nel terminale
    python diagnostica.py --json     # output JSON (per l'app web)
"""

import os
import sys
import json
import sqlite3
import importlib
import urllib.request
import urllib.error

BASE = os.path.join(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(BASE, 'learner'))
sys.path.insert(0, BASE)

CONFIG_PATH = os.path.join(BASE, 'config.json')
DB_PATH     = os.path.join(BASE, 'database', 'tool_master.db')


def _ok(msg):    return {'stato': 'ok',      'msg': msg, 'icona': 'OK'}
def _warn(msg):  return {'stato': 'warn',    'msg': msg, 'icona': 'ATTENZIONE'}
def _errore(msg):return {'stato': 'errore',  'msg': msg, 'icona': 'ERRORE'}


# ---------------------------------------------------------------
def check_python():
    v = sys.version_info
    if v.major == 3 and 10 <= v.minor <= 13:
        return _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    elif v.major == 3 and v.minor >= 14:
        return _warn(f"Python {v.major}.{v.minor} (versione alpha - alcune librerie potrebbero non funzionare)")
    return _errore(f"Python {v.major}.{v.minor} non supportato (richiesto 3.10-3.13)")


def check_dipendenze():
    richieste = ['flask', 'pandas', 'openpyxl', 'xlrd', 'schedule']
    mancanti  = []
    versioni  = {}
    for pkg in richieste:
        try:
            mod = importlib.import_module(pkg)
            versioni[pkg] = getattr(mod, '__version__', 'ok')
        except ImportError:
            mancanti.append(pkg)
    if mancanti:
        return _errore(f"Mancanti: {', '.join(mancanti)} — esegui: pip install {' '.join(mancanti)}")
    return _ok(', '.join(f"{k} {v}" for k,v in versioni.items()))


def check_database():
    if not os.path.exists(DB_PATH):
        return _warn("Database non ancora creato — verrà creato al primo avvio")
    try:
        conn = sqlite3.connect(DB_PATH)
        n_utensili = conn.execute("SELECT COUNT(*) FROM utensile WHERE attivo=1").fetchone()[0]
        n_taglio   = conn.execute("SELECT COUNT(*) FROM condizioni_taglio").fetchone()[0]
        n_profili  = conn.execute("SELECT COUNT(*) FROM tipo_utensile").fetchone()[0]
        conn.close()
        return _ok(f"{n_utensili} utensili | {n_taglio} condizioni taglio | {n_profili} tipi configurati")
    except Exception as e:
        return _errore(f"Errore lettura DB: {e}")


def check_api_key():
    """Verifica presenza e validità della API key Anthropic."""
    # 1. Variabile d'ambiente
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    sorgente = 'variabile ambiente'

    # 2. config.json
    if not key:
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH) as f:
                    cfg = json.load(f)
                key = cfg.get('anthropic_api_key', '').strip()
                sorgente = 'config.json'
        except Exception:
            pass

    # 3. .env
    if not key:
        env_path = os.path.join(BASE, '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('ANTHROPIC_API_KEY='):
                            key = line.split('=', 1)[1].strip().strip('"').strip("'")
                            sorgente = '.env'
                            break
            except Exception:
                pass

    if not key:
        return _errore(
            "API key non trovata.\n"
            "Soluzioni:\n"
            "  1. export ANTHROPIC_API_KEY=sk-ant-...  (nel terminale prima di start.sh)\n"
            "  2. echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env  (nella cartella progetto)\n"
            "  3. Aggiungi in config.json: { \"anthropic_api_key\": \"sk-ant-...\" }"
        )

    # Verifica formato
    if not key.startswith('sk-ant-'):
        return _warn(f"API key trovata in {sorgente} ma formato insolito (non inizia con sk-ant-)")

    return _ok(f"Trovata in: {sorgente} | Inizio: {key[:16]}...")


def check_agente_connessione():
    """Testa la connessione reale all'API Anthropic con una chiamata minimale."""
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not key:
        try:
            env_path = os.path.join(BASE, '.env')
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith('ANTHROPIC_API_KEY='):
                            key = line.split('=',1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    if not key:
        try:
            with open(CONFIG_PATH) as f:
                key = json.load(f).get('anthropic_api_key','').strip()
        except Exception:
            pass

    if not key:
        return _warn("Test saltato — API key non configurata")

    try:
        import ssl
        # Fix SSL certificati Mac
        def _ssl_ctx():
            try:
                import certifi
                return ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                pass
            try:
                ctx = ssl.create_default_context()
                ctx.load_verify_locations('/etc/ssl/cert.pem')
                return ctx
            except Exception:
                pass
            return ssl.create_default_context()

        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "rispondi solo: ok"}]
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'Content-Type':      'application/json',
                'x-api-key':         key,
                'anthropic-version': '2023-06-01',
            },
            method='POST'
        )
        with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=8) as resp:
            data = json.loads(resp.read())
            risposta = data['content'][0]['text'].strip()
            return _ok(f"Connessione OK — risposta test: '{risposta}'")

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try:
            err = json.loads(body).get('error', {}).get('message', body[:80])
        except Exception:
            err = body[:80]
        if e.code == 401:
            return _errore(f"API key non valida o scaduta (401): {err}")
        elif e.code == 429:
            return _warn(f"Rate limit o credito esaurito (429): {err}")
        return _errore(f"Errore HTTP {e.code}: {err}")
    except Exception as e:
        return _errore(f"Connessione fallita: {e}")


def check_parser_cimatron():
    try:
        from cimatron_parser import is_cimatron_file, leggi_cimatron_csv, leggi_cimatron_zip
        return _ok("Parser Cimatron caricato (CSV UTF-16, XLS nativo, ZIP)")
    except ImportError as e:
        return _errore(f"cimatron_parser.py non trovato: {e}")
    except Exception as e:
        return _errore(f"Errore parser: {e}")


def check_profili():
    profiles_dir = os.path.join(BASE, 'learner', 'profiles')
    if not os.path.exists(profiles_dir):
        return _warn("Cartella profili non trovata")
    profili = [f[:-5] for f in os.listdir(profiles_dir) if f.endswith('.json')]
    if not profili:
        return _warn("Nessun profilo salvato — carica un file nel Format Learner per crearne uno")
    return _ok(f"{len(profili)} profili: {', '.join(profili)}")


def check_config():
    if not os.path.exists(CONFIG_PATH):
        return _warn("config.json non trovato — verrà creato al primo avvio")
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        formati = cfg.get('formati_attivi', [])
        ora     = cfg.get('export_ora', '22:00')
        rete    = cfg.get('output_rete', '') or 'non configurata'
        return _ok(f"Formati attivi: {formati or 'nessuno'} | Export ore: {ora} | Rete: {rete}")
    except Exception as e:
        return _errore(f"config.json non valido: {e}")


def check_mapping_agent():
    try:
        from mapping_agent import agente_disponibile, _get_api_key
        key = _get_api_key()
        if key:
            return _ok(f"Modulo caricato | Key: {key[:16]}... | Pronto")
        return _warn("Modulo caricato ma API key non configurata — mapping AI disabilitato")
    except ImportError:
        return _errore("mapping_agent.py non trovato")
    except Exception as e:
        return _errore(f"Errore: {e}")


# ---------------------------------------------------------------
def esegui_tutti() -> dict:
    """Esegue tutti i check e ritorna il report completo."""
    checks = {
        'python':              ('Python',                  check_python),
        'dipendenze':          ('Dipendenze',              check_dipendenze),
        'database':            ('Database master',         check_database),
        'config':              ('Configurazione',          check_config),
        'profili':             ('Profili formato',         check_profili),
        'parser_cimatron':     ('Parser Cimatron',         check_parser_cimatron),
        'api_key':             ('API key Anthropic',       check_api_key),
        'mapping_agent':       ('Modulo mapping agent',    check_mapping_agent),
        'agente_connessione':  ('Connessione API (test)',  check_agente_connessione),
    }

    risultati = {}
    for key, (nome, fn) in checks.items():
        try:
            risultati[key] = {'nome': nome, **fn()}
        except Exception as e:
            risultati[key] = {'nome': nome, **_errore(f"Eccezione: {e}")}

    # Riepilogo
    ok    = sum(1 for r in risultati.values() if r['stato'] == 'ok')
    warn  = sum(1 for r in risultati.values() if r['stato'] == 'warn')
    erri  = sum(1 for r in risultati.values() if r['stato'] == 'errore')
    risultati['_riepilogo'] = {'ok': ok, 'warn': warn, 'errori': erri, 'totale': len(checks)}

    return risultati


# ---------------------------------------------------------------
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()

    risultati = esegui_tutti()

    if args.json:
        print(json.dumps(risultati, indent=2, ensure_ascii=False))
    else:
        print()
        print('=' * 60)
        print('  DIAGNOSTICA TOOL DB MANAGER')
        print('=' * 60)
        ICONE = {'ok': '[OK]     ', 'warn': '[ATTENZIONE] ', 'errore': '[ERRORE]  '}
        for key, r in risultati.items():
            if key == '_riepilogo':
                continue
            icona = ICONE.get(r['stato'], '  ')
            print(f"\n{icona} {r['nome']}")
            for riga in r['msg'].split('\n'):
                print(f"           {riga}")
        print()
        print('=' * 60)
        rie = risultati['_riepilogo']
        print(f"  Risultato: {rie['ok']} OK  |  {rie['warn']} avvisi  |  {rie['errori']} errori")
        print('=' * 60)
        print()
