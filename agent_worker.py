#!/usr/bin/env python3
"""
Agent Worker — processo dedicato per eseguire i job del CAM Agent.
Gira separatamente da Flask/Gunicorn.
Legge i job dalla tabella agent_jobs nel DB SQLite.
"""
import sqlite3, time, json, os, sys, traceback
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'database', 'tool_master.db')
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'ui'))


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] WORKER: {msg}", flush=True)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_table():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS agent_jobs (
        job_id      TEXT PRIMARY KEY,
        status      TEXT DEFAULT 'pending',
        messaggio   TEXT,
        filepath    TEXT,
        history_json TEXT,
        result_json TEXT,
        created_at  REAL,
        updated_at  REAL,
        error_msg   TEXT
    )''')
    # Segna come 'lost' i job che erano running prima del riavvio
    conn.execute("""UPDATE agent_jobs SET status='lost',
        error_msg='Worker riavviato durante esecuzione'
        WHERE status IN ('running','pending') AND created_at < ?""",
        (time.time() - 30,))
    conn.commit()
    conn.close()
    log("Tabella agent_jobs inizializzata")


def run_job(job):
    job_id = job['job_id']
    messaggio = job['messaggio']
    filepath = job['filepath']
    history = json.loads(job['history_json'] or '[]')

    log(f"Eseguo job {job_id}: {messaggio[:60]}...")

    # Marca come running
    conn = get_db()
    conn.execute("UPDATE agent_jobs SET status='running', updated_at=? WHERE job_id=?",
                 (time.time(), job_id))
    conn.commit()
    conn.close()

    try:
        import importlib
        if 'cam_agent' in sys.modules:
            try:
                importlib.reload(sys.modules['cam_agent'])
            except Exception:
                pass
        import cam_agent as _ca

        result = _ca.esegui_agente(messaggio, filepath=filepath, history=history)
        status = 'done'
        error_msg = None
    except Exception as e:
        result = {'errore': f'{e}', 'traceback': traceback.format_exc()[-500:]}
        status = 'error'
        error_msg = str(e)
        log(f"ERRORE job {job_id}: {e}")

    conn = get_db()
    conn.execute("""UPDATE agent_jobs
        SET status=?, result_json=?, error_msg=?, updated_at=?
        WHERE job_id=?""",
        (status, json.dumps(result, ensure_ascii=False, default=str),
         error_msg, time.time(), job_id))
    conn.commit()
    conn.close()
    log(f"Job {job_id} completato: {status}")


def main():
    init_table()
    log("Worker avviato — in ascolto per job...")

    while True:
        try:
            conn = get_db()
            job = conn.execute(
                "SELECT * FROM agent_jobs WHERE status='pending' ORDER BY created_at LIMIT 1"
            ).fetchone()
            conn.close()

            if job:
                run_job(dict(job))
            else:
                time.sleep(1)

            # Pulizia job vecchi > 2 ore
            conn = get_db()
            conn.execute("DELETE FROM agent_jobs WHERE created_at < ?",
                         (time.time() - 7200,))
            conn.commit()
            conn.close()

        except KeyboardInterrupt:
            log("Worker fermato (Ctrl+C)")
            break
        except Exception as e:
            log(f"ERRORE nel loop principale: {e}")
            time.sleep(2)


if __name__ == '__main__':
    main()
