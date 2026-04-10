"""
app.py - Interfaccia web principale Tool DB Manager
Avvia con: python ui/app.py
Apri: http://localhost:5000
"""

import os, sys, json, zipfile, tempfile, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'learner'))

from flask import (Flask, render_template_string, request,
                   redirect, url_for, send_file, jsonify)
from exporters.export_cimatron import export_cutters as export_cimatron

DB_PATH     = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), '..', 'output', 'manual')

app = Flask(__name__)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    schema = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')
    conn = get_conn()
    with open(schema, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit(); conn.close()


def carica_config() -> dict:
    default = {"formati_attivi": ["cimatron_v26"], "export_ora": "22:00",
               "output_rete": "", "keep_last_n": 7}
    if not os.path.exists(CONFIG_PATH):
        return default
    try:
        with open(CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
        for k, v in default.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return default


def salva_config(cfg: dict):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)


def profili_learner() -> list:
    profiles_dir = os.path.join(os.path.dirname(__file__), '..', 'learner', 'profiles')
    if not os.path.exists(profiles_dir):
        return []
    profili = []
    for fname in sorted(os.listdir(profiles_dir)):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(profiles_dir, fname), 'r') as f:
                p = json.load(f)
            profili.append({'nome': p.get('nome', fname[:-5]),
                            'software': p.get('software', '?'),
                            'versione': p.get('versione', '?'),
                            'file': fname[:-5]})
        except Exception:
            pass
    return profili


def esporta_profilo(nome: str, session_dir: str) -> str:
    """Esporta il DB master nel formato del profilo dato. Restituisce path output."""
    os.makedirs(session_dir, exist_ok=True)
    if nome.startswith('cimatron'):
        out = os.path.join(session_dir, f'{nome}.csv')
        export_cimatron(out)
        return out
    # Converter universale per tutti gli altri profili
    from universal_converter import master_to_file
    from profile_manager import carica_profilo
    profilo = carica_profilo(nome)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM utensile_completo WHERE attivo=1").fetchall()
    conn.close()
    import pandas as pd
    df = pd.DataFrame([dict(r) for r in rows])
    ext = '.xlsx' if profilo.get('separatore', ',') not in ('|', ',') else '.csv'
    out = os.path.join(session_dir, f'{nome}{ext}')
    master_to_file(df, profilo, out)
    return out


# ---------------------------------------------------------------
# CSS / HTML base
# ---------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;margin:0;background:#f5f5f3;color:#1a1a1a}
.hdr{background:#1a1a1a;color:#fff;padding:.75rem 2rem;display:flex;align-items:center;gap:2rem}
.hdr h1{margin:0;font-size:1rem;font-weight:500;letter-spacing:.02em}
.hdr a{color:#bbb;text-decoration:none;font-size:.875rem}
.hdr a:hover{color:#fff}
.hdr .sep{color:#444}
.main{max-width:1200px;margin:2rem auto;padding:0 1.5rem}
.card{background:#fff;border:1px solid #e2e2df;border-radius:10px;padding:1.5rem;margin-bottom:1.25rem}
.card-title{font-size:.95rem;font-weight:600;margin:0 0 1rem;color:#222}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border:1px solid #e2e2df;padding:8px 11px;text-align:left;vertical-align:middle}
th{background:#f8f8f6;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#555}
tr:hover td{background:#fafaf8}
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border-radius:6px;
     border:1px solid #d0d0ce;cursor:pointer;font-size:13px;text-decoration:none;
     background:#fff;color:#333;white-space:nowrap;font-weight:500}
.btn:hover{background:#f5f5f3;border-color:#bbb}
.btn-p{background:#0055cc;color:#fff;border-color:#0055cc}
.btn-p:hover{background:#004ab0}
.btn-s{background:#1a6e35;color:#fff;border-color:#1a6e35}
.btn-s:hover{background:#155c2c}
.btn-d{background:#b91c1c;color:#fff;border-color:#b91c1c}
.btn-d:hover{background:#991515}
.btn-lg{padding:10px 22px;font-size:14px;border-radius:7px}
.flash{padding:10px 14px;border-radius:6px;margin-bottom:1rem;font-size:13px;
       background:#dcfce7;color:#166534;border:1px solid #bbf7d0}
.flash.err{background:#fee2e2;color:#991b1b;border-color:#fecaca}
.flash.warn{background:#fef9c3;color:#854d0e;border-color:#fef08a}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:500}
.b-ok{background:#dcfce7;color:#166534}
.b-warn{background:#fef9c3;color:#854d0e}
.b-off{background:#f1f0ee;color:#6b7280}
.stat{background:#f8f8f6;border-radius:8px;padding:.75rem 1rem}
.stat-n{font-size:1.5rem;font-weight:600;color:#1a1a1a}
.stat-l{font-size:11px;color:#888;margin-top:2px}
select,input[type=text],input[type=file],input[type=time]{padding:6px 10px;
  border:1px solid #d0d0ce;border-radius:5px;font-size:13px}
select:focus,input:focus{outline:2px solid #0055cc;border-color:transparent}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.25rem}
.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1.25rem}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem}
.tag{display:inline-block;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;
     padding:2px 8px;border-radius:10px;font-size:12px;margin:2px}
.tag-del{cursor:pointer;margin-left:3px;color:#6b7280}
.tag-del:hover{color:#b91c1c}
hr{border:none;border-top:1px solid #e2e2df;margin:1.25rem 0}
"""

BASE = """<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tool DB Manager</title>
<style>""" + CSS + """</style></head><body>
<div class="hdr">
  <h1>Tool DB Manager</h1>
  <span class="sep">|</span>
  <a href="/">Utensili</a>
  <a href="/export">Export CAM</a>
  <a href="/impostazioni">Impostazioni</a>
  <a href="/log">Log</a>
  <span style="margin-left:auto;font-size:12px;color:#666">
    <a href="http://localhost:5001" target="_blank" style="color:#888">
      Format Learner &#8599;</a>
  </span>
</div>
<div class="main">
{% if msg %}<div class="flash {{ mtype }}">{{ msg }}</div>{% endif %}
{% block content %}{% endblock %}
</div></body></html>"""


# ---------------------------------------------------------------
# HOME — Lista utensili
# ---------------------------------------------------------------
HOME_HTML = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem">
  <div>
    <h2 style="margin:0;font-size:1.1rem">Utensili</h2>
    <p style="margin:4px 0 0;color:#888;font-size:13px">{{ utensili|length }} utensili attivi nel database master</p>
  </div>
  <div style="display:flex;gap:.5rem">
    <a class="btn btn-p" href="/utensile/nuovo">+ Nuovo utensile</a>
    <a class="btn btn-s btn-lg" href="/export">&#8659; Esporta tutti</a>
  </div>
</div>

<div class="grid4" style="margin-bottom:1.25rem">
  <div class="stat"><div class="stat-n">{{ utensili|length }}</div><div class="stat-l">Utensili totali</div></div>
  <div class="stat"><div class="stat-n">{{ tipi }}</div><div class="stat-l">Tipi diversi</div></div>
  <div class="stat"><div class="stat-n">{{ profili_n }}</div><div class="stat-l">Formati export</div></div>
  <div class="stat"><div class="stat-n">{{ formati_attivi_n }}</div><div class="stat-l">Formati attivi</div></div>
</div>

<div class="card">
<table>
<thead><tr>
  <th>Codice</th><th>Descrizione</th><th>Tipo</th>
  <th>Diam.</th><th>R. punta</th><th>L. tot.</th>
  <th>Tag.</th><th>Materiale</th><th></th>
</tr></thead>
<tbody>
{% for u in utensili %}
<tr>
  <td><b>{{ u.codice_interno }}</b></td>
  <td style="color:#555">{{ u.descrizione }}</td>
  <td><span class="badge b-ok">{{ u.tipo }}</span></td>
  <td>{{ u.diametro_mm }}</td>
  <td>{{ u.raggio_punta_mm }}</td>
  <td>{{ u.lunghezza_totale_mm }}</td>
  <td>{{ u.num_taglienti }}</td>
  <td>{{ u.materiale }}</td>
  <td style="white-space:nowrap">
    <a class="btn" href="/utensile/{{ u.id }}/modifica" style="padding:4px 10px;font-size:12px">Modifica</a>
    <a class="btn btn-d" href="/utensile/{{ u.id }}/elimina"
       onclick="return confirm('Eliminare questo utensile?')"
       style="padding:4px 10px;font-size:12px">X</a>
  </td>
</tr>
{% else %}
<tr><td colspan="9" style="text-align:center;color:#aaa;padding:2rem">
  Nessun utensile. <a href="/utensile/nuovo">Aggiungi il primo</a>
  oppure <a href="/importa">importa da Excel</a>.
</td></tr>
{% endfor %}
</tbody>
</table>
</div>
""")


@app.route('/')
def home():
    conn = get_conn()
    utensili = conn.execute(
        "SELECT * FROM utensile_completo WHERE attivo=1 ORDER BY codice_interno"
    ).fetchall()
    conn.close()
    cfg = carica_config()
    profili = profili_learner()
    tipi = len(set(u['tipo'] for u in utensili)) if utensili else 0
    return render_template_string(HOME_HTML,
        utensili=utensili, tipi=tipi,
        profili_n=len(profili),
        formati_attivi_n=len(cfg.get('formati_attivi', [])),
        msg=request.args.get('msg', ''), mtype='')


# ---------------------------------------------------------------
# EXPORT — Esporta tutti i formati
# ---------------------------------------------------------------
EXPORT_HTML = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem">
  <div>
    <h2 style="margin:0;font-size:1.1rem">Export CAM</h2>
    <p style="margin:4px 0 0;color:#888;font-size:13px">
      Genera i file di import per i sistemi CAM configurati
    </p>
  </div>
</div>

<div class="grid2">

  <!-- Colonna sinistra: Export manuale -->
  <div>
    <div class="card">
      <p class="card-title">Export manuale</p>

      <!-- Esporta tutti -->
      <form method="post" action="/export/tutti" style="margin-bottom:1.25rem">
        <p style="font-size:13px;color:#555;margin:0 0 .75rem">
          Genera in un colpo solo i file per tutti i formati attivi e scarica uno ZIP.
        </p>
        {% if formati_attivi %}
        <div style="margin-bottom:.75rem">
          {% for f in formati_attivi %}
          <span class="tag">{{ f }}</span>
          {% endfor %}
        </div>
        <button class="btn btn-s btn-lg" type="submit">
          &#8659; Esporta tutti ({{ formati_attivi|length }} formati)
        </button>
        {% else %}
        <div class="flash warn">
          Nessun formato attivo. Aggiungine uno nelle
          <a href="/impostazioni">Impostazioni</a>
          o impara un nuovo formato con il
          <a href="http://localhost:5001" target="_blank">Format Learner</a>.
        </div>
        {% endif %}
      </form>

      <hr>

      <!-- Esporta singolo formato -->
      <p style="font-size:13px;font-weight:600;margin-bottom:.75rem">Esporta un singolo formato</p>
      {% if tutti_profili %}
      <div style="display:flex;flex-direction:column;gap:.5rem">
        {% for p in tutti_profili %}
        <div style="display:flex;align-items:center;justify-content:space-between;
                    padding:.6rem .75rem;border:1px solid #e2e2df;border-radius:6px">
          <div>
            <span style="font-weight:500;font-size:13px">{{ p.nome }}</span>
            <span style="color:#888;font-size:12px;margin-left:.5rem">
              {{ p.software }} {{ p.versione }}
            </span>
            {% if p.nome in formati_attivi %}
            <span class="badge b-ok" style="margin-left:.5rem">attivo</span>
            {% else %}
            <span class="badge b-off" style="margin-left:.5rem">non attivo</span>
            {% endif %}
          </div>
          <form method="post" action="/export/singolo">
            <input type="hidden" name="profilo" value="{{ p.nome }}">
            <button class="btn btn-p" type="submit" style="padding:5px 12px;font-size:12px">
              Esporta
            </button>
          </form>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <p style="color:#aaa;font-size:13px">
        Nessun profilo disponibile.
        <a href="http://localhost:5001" target="_blank">Crea il primo con Format Learner</a>.
      </p>
      {% endif %}
    </div>
  </div>

  <!-- Colonna destra: info + ultimo export -->
  <div>
    <div class="card">
      <p class="card-title">Come funziona</p>
      <ol style="font-size:13px;color:#555;line-height:1.8;padding-left:1.25rem;margin:0">
        <li>Esporta un file campione dal tuo CAM (CSV, XLS, ZIP)</li>
        <li>Caricalo nel <a href="http://localhost:5001" target="_blank">Format Learner</a> su porta 5001</li>
        <li>Il sistema impara la struttura automaticamente</li>
        <li>Salva il profilo con nome e versione software</li>
        <li>Attivalo qui nelle <a href="/impostazioni">Impostazioni</a></li>
        <li>Da ora il formato appare in questa pagina</li>
      </ol>
    </div>

    <div class="card">
      <p class="card-title">Ultimi export</p>
      {% if logs %}
      <table>
      <thead><tr><th>Data</th><th>Formato</th><th>Utensili</th></tr></thead>
      <tbody>
      {% for l in logs %}
      <tr>
        <td style="font-size:12px;color:#888">{{ l.timestamp[:16] }}</td>
        <td><span class="badge b-ok">{{ l.cam }}</span></td>
        <td>{{ l.num_utensili }}</td>
      </tr>
      {% endfor %}
      </tbody>
      </table>
      {% else %}
      <p style="color:#aaa;font-size:13px;text-align:center;padding:1rem">
        Nessun export ancora effettuato.
      </p>
      {% endif %}
    </div>
  </div>
</div>
""")


@app.route('/export', methods=['GET'])
def export_page():
    cfg = carica_config()
    conn = get_conn()
    logs = conn.execute(
        "SELECT * FROM log_export ORDER BY timestamp DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return render_template_string(EXPORT_HTML,
        formati_attivi=cfg.get('formati_attivi', []),
        tutti_profili=profili_learner(),
        logs=logs,
        msg=request.args.get('msg', ''), mtype=request.args.get('mtype', ''))


@app.route('/export/tutti', methods=['POST'])
def export_tutti():
    cfg = carica_config()
    formati = cfg.get('formati_attivi', [])
    if not formati:
        return redirect(url_for('export_page',
                                msg='Nessun formato attivo configurato.', mtype='warn'))
    tmp = tempfile.mkdtemp()
    session_dir = os.path.join(tmp, 'export')
    errori = []
    ok = []

    for nome in formati:
        try:
            path = esporta_profilo(nome, session_dir)
            ok.append(path)
            conn = get_conn()
            conn.execute(
                "INSERT INTO log_export (cam, num_utensili, file_output) VALUES (?,?,?)",
                (nome.upper(), _conta_utensili(), path))
            conn.commit(); conn.close()
        except Exception as e:
            errori.append(f'{nome}: {e}')

    if not ok:
        return redirect(url_for('export_page',
                                msg=f'Errori: {"; ".join(errori)}', mtype='err'))

    # Crea ZIP con tutti i file
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_path = os.path.join(tmp, f'export_cam_{ts}.zip')
    with zipfile.ZipFile(zip_path, 'w') as z:
        for f in ok:
            z.write(f, os.path.basename(f))

    return send_file(zip_path, as_attachment=True,
                     download_name=f'export_cam_{ts}.zip')


@app.route('/export/singolo', methods=['POST'])
def export_singolo():
    nome = request.form.get('profilo', '').strip()
    if not nome:
        return redirect(url_for('export_page', msg='Profilo non specificato', mtype='err'))
    tmp = tempfile.mkdtemp()
    try:
        path = esporta_profilo(nome, tmp)
        conn = get_conn()
        conn.execute(
            "INSERT INTO log_export (cam, num_utensili, file_output) VALUES (?,?,?)",
            (nome.upper(), _conta_utensili(), path))
        conn.commit(); conn.close()
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))
    except Exception as e:
        return redirect(url_for('export_page', msg=f'Errore: {e}', mtype='err'))


def _conta_utensili() -> int:
    try:
        conn = get_conn()
        n = conn.execute("SELECT COUNT(*) FROM utensile WHERE attivo=1").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


# ---------------------------------------------------------------
# IMPOSTAZIONI
# ---------------------------------------------------------------
IMPOSTAZIONI_HTML = BASE.replace('{% block content %}{% endblock %}', """
<h2 style="margin:0 0 1.25rem;font-size:1.1rem">Impostazioni</h2>

<div class="grid2">
  <div>
    <div class="card">
      <p class="card-title">Formati export attivi</p>
      <p style="font-size:13px;color:#555;margin-bottom:1rem">
        Seleziona i formati da includere nell'export automatico e nel pulsante "Esporta tutti".
      </p>

      <form method="post" action="/impostazioni/formati">
      <div style="display:flex;flex-direction:column;gap:.5rem;margin-bottom:1rem">
        {% for p in tutti_profili %}
        <label style="display:flex;align-items:center;gap:.75rem;padding:.6rem .75rem;
                      border:1px solid #e2e2df;border-radius:6px;cursor:pointer">
          <input type="checkbox" name="formati" value="{{ p.nome }}"
                 {% if p.nome in formati_attivi %}checked{% endif %}
                 style="width:16px;height:16px">
          <div>
            <span style="font-weight:500;font-size:13px">{{ p.nome }}</span>
            <span style="color:#888;font-size:12px;margin-left:.4rem">
              {{ p.software }} {{ p.versione }}
            </span>
          </div>
        </label>
        {% else %}
        <p style="color:#aaa;font-size:13px">
          Nessun profilo disponibile.
          <a href="http://localhost:5001" target="_blank">Crea profili con Format Learner</a>.
        </p>
        {% endfor %}
      </div>
      {% if tutti_profili %}
      <button class="btn btn-p" type="submit">Salva formati attivi</button>
      {% endif %}
      </form>
    </div>
  </div>

  <div>
    <div class="card">
      <p class="card-title">Export automatico</p>
      <form method="post" action="/impostazioni/scheduler">
      <div style="margin-bottom:1rem">
        <label style="font-size:12px;display:block;margin-bottom:4px;font-weight:600">
          Ora export giornaliero
        </label>
        <input type="time" name="export_ora" value="{{ cfg.export_ora }}"
               style="width:auto">
        <p style="font-size:12px;color:#888;margin:4px 0 0">
          Usato da: <code>python scheduler.py --daemon</code>
        </p>
      </div>
      <div style="margin-bottom:1rem">
        <label style="font-size:12px;display:block;margin-bottom:4px;font-weight:600">
          Cartella di rete (opzionale)
        </label>
        <input type="text" name="output_rete" value="{{ cfg.output_rete }}"
               placeholder="es. \\\\SERVER\\CAM_export" style="width:100%">
        <p style="font-size:12px;color:#888;margin:4px 0 0">
          Se configurata, i file vengono copiati automaticamente dopo ogni export.
        </p>
      </div>
      <div style="margin-bottom:1rem">
        <label style="font-size:12px;display:block;margin-bottom:4px;font-weight:600">
          Mantieni ultimi N export
        </label>
        <input type="text" name="keep_last_n" value="{{ cfg.keep_last_n }}"
               style="width:80px">
      </div>
      <button class="btn btn-p" type="submit">Salva impostazioni scheduler</button>
      </form>
    </div>

    <div class="card">
      <p class="card-title">Comandi utili</p>
      <div style="font-size:12px;color:#555;display:flex;flex-direction:column;gap:.5rem">
        <div style="background:#f8f8f6;border-radius:5px;padding:.5rem .75rem">
          <code>python scheduler.py --now</code><br>
          <span style="color:#888">Esporta subito tutti i formati attivi</span>
        </div>
        <div style="background:#f8f8f6;border-radius:5px;padding:.5rem .75rem">
          <code>python scheduler.py --watch</code><br>
          <span style="color:#888">Esporta automaticamente quando il DB cambia</span>
        </div>
        <div style="background:#f8f8f6;border-radius:5px;padding:.5rem .75rem">
          <code>python scheduler.py --daemon</code><br>
          <span style="color:#888">Esporta ogni notte all'ora configurata</span>
        </div>
        <div style="background:#f8f8f6;border-radius:5px;padding:.5rem .75rem">
          <a href="http://localhost:5001" target="_blank">
            Format Learner → http://localhost:5001
          </a><br>
          <span style="color:#888">Impara nuovi formati CAM da file campione</span>
        </div>
      </div>
    </div>
  </div>
</div>
""")


@app.route('/impostazioni')
def impostazioni():
    cfg = carica_config()
    return render_template_string(IMPOSTAZIONI_HTML,
        cfg=type('C', (), cfg)(),
        tutti_profili=profili_learner(),
        formati_attivi=cfg.get('formati_attivi', []),
        msg=request.args.get('msg', ''), mtype='')


@app.route('/impostazioni/formati', methods=['POST'])
def salva_formati():
    cfg = carica_config()
    cfg['formati_attivi'] = request.form.getlist('formati')
    salva_config(cfg)
    return redirect(url_for('impostazioni',
                            msg=f'Formati attivi salvati: {", ".join(cfg["formati_attivi"]) or "nessuno"}'))


@app.route('/impostazioni/scheduler', methods=['POST'])
def salva_scheduler():
    cfg = carica_config()
    cfg['export_ora']   = request.form.get('export_ora', '22:00')
    cfg['output_rete']  = request.form.get('output_rete', '').strip()
    cfg['keep_last_n']  = int(request.form.get('keep_last_n', 7) or 7)
    salva_config(cfg)
    return redirect(url_for('impostazioni', msg='Impostazioni scheduler salvate'))


# ---------------------------------------------------------------
# LOG
# ---------------------------------------------------------------
LOG_HTML = BASE.replace('{% block content %}{% endblock %}', """
<h2 style="margin:0 0 1.25rem;font-size:1.1rem">Log export</h2>
<div class="card">
<table>
<thead><tr><th>Data</th><th>Formato</th><th>Utensili</th><th>File output</th></tr></thead>
<tbody>
{% for l in logs %}
<tr>
  <td style="font-size:12px;color:#888">{{ l.timestamp }}</td>
  <td><span class="badge b-ok">{{ l.cam }}</span></td>
  <td>{{ l.num_utensili }}</td>
  <td style="font-size:12px;color:#555">{{ l.file_output or '-' }}</td>
</tr>
{% else %}
<tr><td colspan="4" style="text-align:center;color:#aaa;padding:2rem">
  Nessun export ancora effettuato.
</td></tr>
{% endfor %}
</tbody>
</table>
</div>
""")


@app.route('/log')
def log_page():
    conn = get_conn()
    logs = conn.execute(
        "SELECT * FROM log_export ORDER BY timestamp DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return render_template_string(LOG_HTML, logs=logs, msg='', mtype='')


# ---------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print('Tool DB Manager -> http://localhost:5000')
    print('Format Learner  -> http://localhost:5001  (avvia separatamente)')
    app.run(debug=True, port=5000)
