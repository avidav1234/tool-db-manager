"""
scheduler.py
============
Export automatico periodico del DB master verso tutti i formati attivi.

Modalita di esecuzione:
  1. Manuale:   python scheduler.py --now
  2. Daemon:    python scheduler.py --daemon   (gira in background, ogni notte)
  3. On-change: python scheduler.py --watch    (esporta quando il DB cambia)
  4. Windows Task Scheduler: punta a scheduler.py --now

Configurazione in config.json (creato automaticamente al primo avvio).
"""

import os
import sys
import json
import time
import shutil
import hashlib
import argparse
from datetime import datetime

# Percorsi
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, 'database', 'tool_master.db')
LEARNER_DIR   = os.path.join(BASE_DIR, 'learner')
PROFILES_DIR  = os.path.join(LEARNER_DIR, 'profiles')
OUTPUT_DIR    = os.path.join(BASE_DIR, 'output', 'auto')
CONFIG_PATH   = os.path.join(BASE_DIR, 'config.json')
LOG_PATH      = os.path.join(BASE_DIR, 'export.log')

sys.path.insert(0, LEARNER_DIR)
sys.path.insert(0, BASE_DIR)

DEFAULT_CONFIG = {
    "export_ora":        "22:00",
    "output_dir":        OUTPUT_DIR,
    "output_rete":       "",
    "formati_attivi":    ["cimatron_v26"],
    "notify_on_change":  True,
    "keep_last_n":       7
}


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def carica_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        log(f"Config creata: {CONFIG_PATH}")
    with open(CONFIG_PATH, 'r') as f:
        cfg = json.load(f)
    # Merge con default per chiavi mancanti
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def profili_disponibili() -> list:
    if not os.path.exists(PROFILES_DIR):
        return []
    return [f[:-5] for f in os.listdir(PROFILES_DIR) if f.endswith('.json')]


def esporta_tutti(cfg: dict) -> dict:
    """
    Esporta il DB master in tutti i formati attivi.
    Restituisce un dict {profilo: path_file_output | errore}.
    """
    from universal_converter import file_to_master, master_to_file
    from profile_manager import carica_profilo, lista_profili
    from exporters.export_cimatron import export_cutters

    out_dir = cfg.get('output_dir', OUTPUT_DIR)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    session_dir = os.path.join(out_dir, ts)
    os.makedirs(session_dir, exist_ok=True)

    formati = cfg.get('formati_attivi', [])
    risultati = {}

    for profilo_nome in formati:
        try:
            # Caso speciale: Cimatron usa il suo exporter nativo (piu preciso)
            if profilo_nome.startswith('cimatron'):
                out_path = os.path.join(session_dir, f'{profilo_nome}.csv')
                export_cutters(out_path)
                risultati[profilo_nome] = out_path
                log(f"  OK  {profilo_nome} -> {out_path}")

            else:
                # Converter universale via profilo learner
                profilo = carica_profilo(profilo_nome)
                out_ext = '.csv'
                out_path = os.path.join(session_dir, f'{profilo_nome}{out_ext}')

                # Usa il DB master come sorgente tramite una vista CSV temporanea
                import sqlite3
                import pandas as pd
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM utensile_completo WHERE attivo=1").fetchall()
                conn.close()

                df = pd.DataFrame([dict(r) for r in rows])
                master_to_file(df, profilo, out_path)
                risultati[profilo_nome] = out_path
                log(f"  OK  {profilo_nome} -> {out_path}")

        except Exception as e:
            risultati[profilo_nome] = f"ERRORE: {e}"
            log(f"  ERR {profilo_nome}: {e}")

    # Copia su cartella di rete se configurata
    rete = cfg.get('output_rete', '').strip()
    if rete and os.path.exists(rete):
        try:
            net_dir = os.path.join(rete, ts)
            shutil.copytree(session_dir, net_dir)
            log(f"Copiato su rete: {net_dir}")
        except Exception as e:
            log(f"Errore copia rete: {e}")

    # Mantieni solo ultimi N export
    keep = int(cfg.get('keep_last_n', 7))
    dirs = sorted([
        d for d in os.listdir(out_dir)
        if os.path.isdir(os.path.join(out_dir, d))
    ])
    for old in dirs[:-keep]:
        shutil.rmtree(os.path.join(out_dir, old), ignore_errors=True)

    log(f"Export completato: {len([v for v in risultati.values() if not v.startswith('ERRORE')])} OK, "
        f"{len([v for v in risultati.values() if v.startswith('ERRORE')])} errori")
    return risultati


def _db_hash() -> str:
    if not os.path.exists(DB_PATH):
        return ''
    with open(DB_PATH, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def watch_mode(cfg: dict):
    """Modalita watcher: esporta automaticamente quando il DB cambia."""
    log("Modalita watch attiva. Premo Ctrl+C per uscire.")
    last_hash = _db_hash()
    while True:
        time.sleep(10)
        current = _db_hash()
        if current and current != last_hash:
            log("DB modificato — avvio export automatico")
            esporta_tutti(cfg)
            last_hash = current


def daemon_mode(cfg: dict):
    """Modalita daemon: esporta ogni giorno all'ora configurata."""
    try:
        import schedule
    except ImportError:
        log("Installa schedule: pip install schedule")
        sys.exit(1)

    ora = cfg.get('export_ora', '22:00')
    log(f"Daemon attivo. Export programmato ogni giorno alle {ora}. Ctrl+C per uscire.")
    schedule.every().day.at(ora).do(lambda: esporta_tutti(cfg))
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Export automatico DB master')
    parser.add_argument('--now',    action='store_true', help='Esporta subito')
    parser.add_argument('--watch',  action='store_true', help='Esporta quando il DB cambia')
    parser.add_argument('--daemon', action='store_true', help='Esporta ogni notte')
    parser.add_argument('--status', action='store_true', help='Mostra config e profili attivi')
    args = parser.parse_args()

    cfg = carica_config()

    if args.status:
        print(f"\nConfig: {CONFIG_PATH}")
        print(f"Output: {cfg['output_dir']}")
        print(f"Ora export: {cfg['export_ora']}")
        print(f"Cartella rete: {cfg['output_rete'] or 'non configurata'}")
        print(f"Profili attivi: {cfg['formati_attivi']}")
        print(f"Profili disponibili: {profili_disponibili()}")

    elif args.now:
        log("Export manuale avviato")
        risultati = esporta_tutti(cfg)
        for profilo, path in risultati.items():
            print(f"  {profilo:30} {path}")

    elif args.watch:
        watch_mode(cfg)

    elif args.daemon:
        daemon_mode(cfg)

    else:
        parser.print_help()
