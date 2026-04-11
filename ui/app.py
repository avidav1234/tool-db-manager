"""
app.py - Tool DB Manager - interfaccia web principale
Avvia: python ui/app.py   oppure   bash start.sh
"""

import os, sys, json, zipfile, tempfile, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'learner'))

from flask import (Flask, render_template_string, request,
                   redirect, url_for, send_file)

DB_PATH     = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), '..', 'output', 'manual')

app = Flask(__name__)

# ---------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        schema = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = get_conn()
        with open(schema, encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.commit(); conn.close()
    except Exception as e:
        print(f'[WARN] init_db: {e}')

def carica_config():
    default = {'formati_attivi':['cimatron_v26'],'export_ora':'22:00','output_rete':'','keep_last_n':7}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            for k,v in default.items(): cfg.setdefault(k,v)
            return cfg
    except Exception: pass
    return default

def salva_config(cfg):
    with open(CONFIG_PATH,'w') as f: json.dump(cfg,f,indent=2)

def profili_learner():
    d = os.path.join(os.path.dirname(__file__),'..','learner','profiles')
    out = []
    if not os.path.exists(d): return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'): continue
        try:
            with open(os.path.join(d,fn)) as f: p=json.load(f)
            out.append({'nome':p.get('nome',fn[:-5]),'software':p.get('software','?'),
                        'versione':p.get('versione','?'),'file':fn[:-5]})
        except Exception: pass
    return out

def _conta():
    try:
        conn=get_conn(); n=conn.execute("SELECT COUNT(*) FROM utensile WHERE attivo=1").fetchone()[0]; conn.close(); return n
    except: return 0

def esporta_profilo(nome, session_dir):
    os.makedirs(session_dir, exist_ok=True)
    if nome.startswith('cimatron'):
        from exporters.export_cimatron import export_cutters
        out = os.path.join(session_dir, f'{nome}.csv')
        export_cutters(out); return out
    from universal_converter import master_to_file
    from profile_manager import carica_profilo
    import pandas as pd
    profilo = carica_profilo(nome)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM utensile_completo WHERE attivo=1").fetchall()
    conn.close()
    df = pd.DataFrame([dict(r) for r in rows])
    out = os.path.join(session_dir, f'{nome}.csv')
    master_to_file(df, profilo, out); return out

# ---------------------------------------------------------------
# CSS + BASE
# ---------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;margin:0;background:#f5f5f3;color:#1a1a1a}
.hdr{background:#1a1a1a;color:#fff;padding:.75rem 2rem;display:flex;align-items:center;gap:2rem}
.hdr h1{margin:0;font-size:1rem;font-weight:500}
.hdr a{color:#bbb;text-decoration:none;font-size:.875rem}.hdr a:hover{color:#fff}
.hdr a.active{color:#fff;border-bottom:2px solid #fff;padding-bottom:2px}
.main{max-width:1100px;margin:2rem auto;padding:0 1.5rem}
.card{background:#fff;border:1px solid #e2e2df;border-radius:10px;padding:1.5rem;margin-bottom:1.25rem}
.card h2{margin:0 0 1rem;font-size:.95rem;font-weight:600;color:#222}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border:1px solid #e2e2df;padding:8px 11px;text-align:left;vertical-align:middle}
th{background:#f8f8f6;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#666}
tr:hover td{background:#fafaf8}
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 15px;border-radius:6px;
     border:1px solid #d0d0ce;cursor:pointer;font-size:13px;text-decoration:none;
     background:#fff;color:#333;font-weight:500;white-space:nowrap}
.btn:hover{background:#f5f5f3}
.btn-p{background:#0055cc;color:#fff;border-color:#0055cc}.btn-p:hover{background:#0047ad}
.btn-s{background:#1a6e35;color:#fff;border-color:#1a6e35}.btn-s:hover{background:#155c2c}
.btn-d{background:#b91c1c;color:#fff;border-color:#b91c1c}.btn-d:hover{background:#991515}
.btn-lg{padding:10px 22px;font-size:14px}
.flash{padding:10px 14px;border-radius:6px;margin-bottom:1rem;font-size:13px;
       background:#dcfce7;color:#166534;border:1px solid #bbf7d0}
.flash.err{background:#fee2e2;color:#991b1b;border-color:#fecaca}
.flash.warn{background:#fef9c3;color:#854d0e;border-color:#fef08a}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:500}
.b-ok{background:#dcfce7;color:#166534}
.b-off{background:#f1f0ee;color:#6b7280}
.stat{background:#f8f8f6;border-radius:8px;padding:.75rem 1rem}
.stat-n{font-size:1.4rem;font-weight:600}.stat-l{font-size:11px;color:#888;margin-top:2px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.25rem}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem}
.form-row{display:grid;gap:1rem;margin-bottom:1rem}
.form-row.col2{grid-template-columns:repeat(2,1fr)}
.form-row.col3{grid-template-columns:repeat(3,1fr)}
.form-row.col4{grid-template-columns:repeat(4,1fr)}
.field label{display:block;font-size:12px;font-weight:600;color:#555;margin-bottom:4px}
.field input,.field select,.field textarea{width:100%;padding:7px 10px;border:1px solid #d0d0ce;
  border-radius:5px;font-size:13px;background:#fff}
.field input:focus,.field select:focus{outline:2px solid #0055cc;border-color:transparent}
.field .hint{font-size:11px;color:#aaa;margin-top:3px}
.required::after{content:" *";color:#b91c1c}
.section-title{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;
               color:#888;margin:1.5rem 0 .75rem;padding-bottom:.4rem;border-bottom:1px solid #e2e2df}
code{background:#f4f4f2;padding:2px 6px;border-radius:4px;font-size:12px}
hr{border:none;border-top:1px solid #e2e2df;margin:1.25rem 0}
.tag{display:inline-block;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;
     padding:2px 8px;border-radius:10px;font-size:12px;margin:2px}
.drop-zone{border:2px dashed #ccc;border-radius:8px;padding:2.5rem;text-align:center;
           color:#888;cursor:pointer;transition:all .2s}
.drop-zone:hover,.drop-zone.over{border-color:#0055cc;color:#0055cc;background:#f0f4ff}
"""

BASE = """<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tool DB Manager</title><style>""" + CSS + """</style></head><body>
<div class="hdr">
  <h1>Tool DB Manager</h1>
  <a href="/" class="{{ 'active' if active=='home' }}">Utensili</a>
  <a href="/export" class="{{ 'active' if active=='export' }}">Export</a>
  <a href="/importa" class="{{ 'active' if active=='importa' }}">Importa</a>
  <a href="/impostazioni" class="{{ 'active' if active=='impostazioni' }}">Impostazioni</a>
  <a href="/log" class="{{ 'active' if active=='log' }}">Log</a>
  <span style="margin-left:auto">
    <a href="http://localhost:5001" target="_blank" style="color:#555;font-size:12px">
      Format Learner &#8599;</a>
  </span>
</div>
<div class="main">
{% if msg %}<div class="flash {{ mtype }}">{{ msg }}</div>{% endif %}
{% block content %}{% endblock %}
</div></body></html>"""

# ---------------------------------------------------------------
# HOME
# ---------------------------------------------------------------
HOME_HTML = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem">
  <div>
    <h2 style="margin:0;font-size:1.1rem">Utensili</h2>
    <p style="margin:4px 0 0;color:#888;font-size:13px">{{ n }} utensili nel database master</p>
  </div>
  <div style="display:flex;gap:.5rem">
    <a class="btn" href="/importa">&#8657; Importa</a>
    <a class="btn btn-p" href="/utensile/nuovo">+ Nuovo utensile</a>
    <a class="btn btn-s btn-lg" href="/export">&#8659; Esporta tutti</a>
  </div>
</div>

<div class="grid4" style="margin-bottom:1.25rem">
  <div class="stat"><div class="stat-n">{{ n }}</div><div class="stat-l">Utensili totali</div></div>
  <div class="stat"><div class="stat-n">{{ n_tipi }}</div><div class="stat-l">Tipi diversi</div></div>
  <div class="stat"><div class="stat-n">{{ n_profili }}</div><div class="stat-l">Profili export</div></div>
  <div class="stat"><div class="stat-n">{{ n_attivi }}</div><div class="stat-l">Formati attivi</div></div>
</div>

<div class="card">
{% if utensili %}
<div style="margin-bottom:.75rem;display:flex;gap:.5rem">
  <input type="text" id="search" placeholder="Cerca per codice o descrizione..."
         oninput="filtra(this.value)"
         style="flex:1;padding:7px 10px;border:1px solid #d0d0ce;border-radius:5px;font-size:13px">
</div>
<table id="tbl">
<thead><tr>
  <th>Codice</th><th>Descrizione</th><th>Tipo</th>
  <th>Diam.</th><th>R.punta</th><th>L.tot.</th><th>Tag.</th><th>Mat.</th><th></th>
</tr></thead>
<tbody>
{% for u in utensili %}
<tr data-search="{{ (u.codice_interno ~ ' ' ~ u.descrizione)|lower }}">
  <td><b>{{ u.codice_interno }}</b></td>
  <td style="color:#555;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
      title="{{ u.descrizione }}">{{ u.descrizione }}</td>
  <td><span class="badge b-ok">{{ u.tipo }}</span></td>
  <td>{{ u.diametro_mm }}</td>
  <td>{{ u.raggio_punta_mm }}</td>
  <td>{{ u.lunghezza_totale_mm }}</td>
  <td>{{ u.num_taglienti }}</td>
  <td>{{ u.materiale }}</td>
  <td style="white-space:nowrap">
    <a class="btn" style="padding:4px 9px;font-size:12px"
       href="/utensile/{{ u.id }}/modifica">Modifica</a>
    <a class="btn btn-d" style="padding:4px 9px;font-size:12px"
       href="/utensile/{{ u.id }}/elimina"
       onclick="return confirm('Eliminare {{ u.codice_interno }}?')">X</a>
  </td>
</tr>
{% endfor %}
</tbody></table>
<script>
function filtra(q){
  q=q.toLowerCase();
  document.querySelectorAll('#tbl tbody tr').forEach(r=>{
    r.style.display=(!q||r.dataset.search.includes(q))?'':'none';
  });
}
</script>
{% else %}
<div style="text-align:center;padding:3rem;color:#aaa">
  <div style="font-size:3rem;margin-bottom:.5rem">&#128295;</div>
  <p style="margin-bottom:1rem">Nessun utensile ancora nel database.</p>
  <a class="btn btn-p" href="/utensile/nuovo" style="margin-right:.5rem">+ Inserisci manualmente</a>
  <a class="btn" href="/importa">&#8657; Importa da Excel / CSV</a>
</div>
{% endif %}
</div>
""")

@app.route('/')
def home():
    try:
        conn=get_conn()
        rows=conn.execute("SELECT * FROM utensile_completo WHERE attivo=1 ORDER BY codice_interno").fetchall()
        conn.close()
        utensili=[dict(r) for r in rows]
    except Exception: utensili=[]
    cfg=carica_config(); profili=profili_learner()
    return render_template_string(HOME_HTML,
        utensili=utensili, n=len(utensili),
        n_tipi=len(set(u['tipo'] for u in utensili if u.get('tipo'))),
        n_profili=len(profili), n_attivi=len(cfg.get('formati_attivi',[])),
        active='home', msg=request.args.get('msg',''), mtype=request.args.get('mtype',''))

# ---------------------------------------------------------------
# FORM UTENSILE (nuovo + modifica)
# ---------------------------------------------------------------
FORM_HTML = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;align-items:center;gap:.75rem;margin-bottom:1.5rem">
  <a href="/" class="btn" style="padding:5px 12px;font-size:13px">&#8592; Indietro</a>
  <h2 style="margin:0;font-size:1.1rem">{{ titolo }}</h2>
</div>

<form method="post" action="{{ action }}">
<div class="card">
  <p class="section-title">Identificazione</p>
  <div class="form-row col3">
    <div class="field">
      <label class="required">Codice interno</label>
      <input name="codice_interno" value="{{ u.codice_interno or '' }}"
             placeholder="es. FP-D10-R0-L75" required>
      <p class="hint">ID univoco aziendale — non modificabile dopo la creazione</p>
    </div>
    <div class="field">
      <label>Codice catalogo fornitore</label>
      <input name="codice_catalogo" value="{{ u.codice_catalogo or '' }}"
             placeholder="es. R216.34-10030-AC10G">
    </div>
    <div class="field">
      <label>Descrizione</label>
      <input name="descrizione" value="{{ u.descrizione or '' }}"
             placeholder="es. Fresa piatta D10 Z4 HM">
    </div>
  </div>

  <p class="section-title">Classificazione</p>
  <div class="form-row col3">
    <div class="field">
      <label class="required">Tipo utensile</label>
      <select name="tipo">
        {% for t in tipi %}
        <option value="{{ t.codice }}" {{ 'selected' if u.tipo==t.codice }}>
          {{ t.codice }} — {{ t.descrizione }}
        </option>
        {% endfor %}
      </select>
    </div>
    <div class="field">
      <label class="required">Materiale tagliente</label>
      <select name="materiale">
        {% for m in materiali %}
        <option value="{{ m.codice }}" {{ 'selected' if u.materiale==m.codice }}>
          {{ m.codice }} — {{ m.descrizione }}
        </option>
        {% endfor %}
      </select>
    </div>
    <div class="field">
      <label>Fornitore</label>
      <select name="id_fornitore">
        <option value="">-- nessuno --</option>
        {% for f in fornitori %}
        <option value="{{ f.id }}" {{ 'selected' if u.id_fornitore==f.id }}>{{ f.nome }}</option>
        {% endfor %}
      </select>
    </div>
  </div>

  <p class="section-title">Geometria (mm)</p>
  <div class="form-row col4">
    <div class="field">
      <label class="required">Diametro</label>
      <input type="number" step="0.001" min="0" name="diametro_mm"
             value="{{ u.diametro_mm or '' }}" placeholder="10.0" required>
    </div>
    <div class="field">
      <label>Raggio punta</label>
      <input type="number" step="0.001" min="0" name="raggio_punta_mm"
             value="{{ u.raggio_punta_mm or 0 }}" placeholder="0 = piatta">
      <p class="hint">0 = piatta / sferica se = diam/2</p>
    </div>
    <div class="field">
      <label>Angolo punta (°)</label>
      <input type="number" step="0.1" min="0" max="180" name="angolo_punta_gradi"
             value="{{ u.angolo_punta_gradi or '' }}" placeholder="118">
      <p class="hint">Solo per punte</p>
    </div>
    <div class="field">
      <label>Angolo elica (°)</label>
      <input type="number" step="0.1" min="0" max="90" name="angolo_elica_gradi"
             value="{{ u.angolo_elica_gradi or '' }}" placeholder="30">
    </div>
  </div>
  <div class="form-row col4">
    <div class="field">
      <label class="required">Lunghezza totale</label>
      <input type="number" step="0.01" min="0" name="lunghezza_totale_mm"
             value="{{ u.lunghezza_totale_mm or '' }}" placeholder="75.0" required>
    </div>
    <div class="field">
      <label class="required">Lunghezza tagliente</label>
      <input type="number" step="0.01" min="0" name="lunghezza_tagl_mm"
             value="{{ u.lunghezza_tagl_mm or '' }}" placeholder="22.0" required>
    </div>
    <div class="field">
      <label class="required">Num. taglienti</label>
      <input type="number" step="1" min="1" max="20" name="num_taglienti"
             value="{{ u.num_taglienti or 2 }}" required>
    </div>
    <div class="field">
      <label>Passo filetto (mm)</label>
      <input type="number" step="0.01" min="0" name="passo_mm"
             value="{{ u.passo_mm or '' }}" placeholder="Solo per maschi">
    </div>
  </div>

  <p class="section-title">Note</p>
  <div class="form-row">
    <div class="field">
      <textarea name="note" rows="2" placeholder="Note opzionali..."
                style="resize:vertical">{{ u.note or '' }}</textarea>
    </div>
  </div>
</div>

<div style="display:flex;gap:.75rem;align-items:center">
  <button class="btn btn-p btn-lg" type="submit">
    {{ 'Salva modifiche' if modifica else 'Aggiungi utensile' }}
  </button>
  <a class="btn" href="/">Annulla</a>
  {% if modifica %}
  <a class="btn btn-d" style="margin-left:auto"
     href="/utensile/{{ u.id }}/elimina"
     onclick="return confirm('Eliminare questo utensile?')">Elimina</a>
  {% endif %}
</div>
</form>
""")

def _get_lookup():
    conn = get_conn()
    tipi      = [dict(r) for r in conn.execute("SELECT * FROM tipo_utensile ORDER BY codice").fetchall()]
    materiali = [dict(r) for r in conn.execute("SELECT * FROM materiale_utensile ORDER BY codice").fetchall()]
    fornitori = [dict(r) for r in conn.execute("SELECT * FROM fornitore ORDER BY nome").fetchall()]
    conn.close()
    return tipi, materiali, fornitori

@app.route('/utensile/nuovo', methods=['GET','POST'])
def utensile_nuovo():
    if request.method == 'POST':
        return _salva_utensile(None)
    tipi, materiali, fornitori = _get_lookup()
    return render_template_string(FORM_HTML,
        titolo='Nuovo utensile', action='/utensile/nuovo',
        u={}, tipi=tipi, materiali=materiali, fornitori=fornitori,
        modifica=False, active='home', msg='', mtype='')

@app.route('/utensile/<int:uid>/modifica', methods=['GET','POST'])
def utensile_modifica(uid):
    if request.method == 'POST':
        return _salva_utensile(uid)
    conn = get_conn()
    row = conn.execute("SELECT u.*, t.codice AS tipo, m.codice AS materiale FROM utensile u JOIN tipo_utensile t ON u.id_tipo=t.id JOIN materiale_utensile m ON u.id_materiale=m.id WHERE u.id=?", (uid,)).fetchone()
    conn.close()
    if not row:
        return redirect(url_for('home', msg='Utensile non trovato', mtype='err'))
    tipi, materiali, fornitori = _get_lookup()
    return render_template_string(FORM_HTML,
        titolo=f'Modifica — {row["codice_interno"]}', action=f'/utensile/{uid}/modifica',
        u=dict(row), tipi=tipi, materiali=materiali, fornitori=fornitori,
        modifica=True, active='home', msg='', mtype='')

def _salva_utensile(uid):
    f = request.form
    conn = get_conn()
    try:
        tipo_id = conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (f['tipo'],)).fetchone()['id']
        mat_id  = conn.execute("SELECT id FROM materiale_utensile WHERE codice=?", (f['materiale'],)).fetchone()['id']
        forn_id = f.get('id_fornitore') or None

        def flt(k, default=None):
            v = f.get(k,'').strip()
            try: return float(v) if v else default
            except: return default

        def intt(k, default=2):
            v = f.get(k,'').strip()
            try: return int(v) if v else default
            except: return default

        params = (
            f['codice_catalogo'].strip() or None,
            f['descrizione'].strip() or None,
            tipo_id, mat_id, forn_id,
            flt('diametro_mm', 0),
            flt('raggio_punta_mm', 0),
            flt('angolo_punta_gradi'),
            flt('lunghezza_totale_mm', 0),
            flt('lunghezza_tagl_mm', 0),
            intt('num_taglienti', 2),
            flt('angolo_elica_gradi'),
            flt('passo_mm'),
            f.get('note','').strip() or None,
        )

        if uid:
            conn.execute("""UPDATE utensile SET
                codice_catalogo=?,descrizione=?,id_tipo=?,id_materiale=?,id_fornitore=?,
                diametro_mm=?,raggio_punta_mm=?,angolo_punta_gradi=?,
                lunghezza_totale_mm=?,lunghezza_tagl_mm=?,num_taglienti=?,
                angolo_elica_gradi=?,passo_mm=?,note=?
                WHERE id=?""", (*params, uid))
            msg = f'Utensile aggiornato.'
        else:
            codice = f['codice_interno'].strip()
            if not codice:
                raise ValueError('Codice interno obbligatorio')
            conn.execute("""INSERT INTO utensile
                (codice_interno,codice_catalogo,descrizione,id_tipo,id_materiale,id_fornitore,
                 diametro_mm,raggio_punta_mm,angolo_punta_gradi,lunghezza_totale_mm,
                 lunghezza_tagl_mm,num_taglienti,angolo_elica_gradi,passo_mm,note)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (codice, *params))
            msg = f'Utensile {codice} aggiunto.'
        conn.commit()
        return redirect(url_for('home', msg=msg))
    except Exception as e:
        conn.rollback()
        return redirect(url_for('home', msg=f'Errore: {e}', mtype='err'))
    finally:
        conn.close()

@app.route('/utensile/<int:uid>/elimina')
def utensile_elimina(uid):
    conn = get_conn()
    try:
        row = conn.execute("SELECT codice_interno FROM utensile WHERE id=?", (uid,)).fetchone()
        if row:
            conn.execute("UPDATE utensile SET attivo=0 WHERE id=?", (uid,))
            conn.commit()
            return redirect(url_for('home', msg=f'Utensile {row["codice_interno"]} eliminato.'))
        return redirect(url_for('home', msg='Utensile non trovato', mtype='err'))
    finally:
        conn.close()

# ---------------------------------------------------------------
# IMPORTA — upload Excel/CSV con anteprima
# ---------------------------------------------------------------
IMPORTA_HTML = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem">
  <h2 style="margin:0;font-size:1.1rem">Importa utensili</h2>
  <a href="/" class="btn">&#8592; Indietro</a>
</div>

<div class="grid2">
  <div>
    <div class="card">
      <h2>Carica file Excel o CSV</h2>
      <form method="post" action="/importa" enctype="multipart/form-data">
        <label class="drop-zone" for="file_input" id="dz">
          <div style="font-size:2.5rem;margin-bottom:.5rem">&#128196;</div>
          <div id="dz-label">Trascina qui il file o clicca per sceglierlo</div>
          <div style="font-size:12px;color:#aaa;margin-top:.4rem">.xlsx  .xls  .csv</div>
          <input type="file" id="file_input" name="file"
                 accept=".xlsx,.xls,.csv" style="display:none"
                 onchange="document.getElementById('dz-label').textContent=this.files[0].name">
        </label>
        <div style="margin-top:1rem;display:flex;gap:.75rem;align-items:center">
          <button class="btn btn-p" type="submit">Analizza e importa</button>
          <label style="font-size:13px;display:flex;align-items:center;gap:.4rem;cursor:pointer">
            <input type="checkbox" name="dry_run" value="1"> Simulazione (non scrive nel DB)
          </label>
        </div>
      </form>
    </div>

    <div class="card">
      <h2>Formato atteso</h2>
      <p style="font-size:13px;color:#555;margin-bottom:.75rem">
        Il file deve avere una riga di intestazione. I nomi delle colonne vengono
        riconosciuti automaticamente. Colonne supportate:
      </p>
      <table style="font-size:12px">
      <thead><tr><th>Colonna</th><th>Obbligatoria</th><th>Esempio</th></tr></thead>
      <tbody>
        <tr><td><code>codice_interno</code></td><td>Si</td><td>FP-D10-R0-L75</td></tr>
        <tr><td><code>descrizione</code></td><td>No</td><td>Fresa piatta D10</td></tr>
        <tr><td><code>tipo</code></td><td>Si</td><td>FLAT / BALL / BULL / DRILL / TAP</td></tr>
        <tr><td><code>diametro_mm</code></td><td>Si</td><td>10.0</td></tr>
        <tr><td><code>raggio_punta_mm</code></td><td>No</td><td>0.0</td></tr>
        <tr><td><code>lunghezza_totale_mm</code></td><td>Si</td><td>75.0</td></tr>
        <tr><td><code>lunghezza_tagl_mm</code></td><td>Si</td><td>22.0</td></tr>
        <tr><td><code>num_taglienti</code></td><td>No</td><td>4</td></tr>
        <tr><td><code>materiale</code></td><td>No</td><td>HM / HSS / CBN</td></tr>
        <tr><td><code>codice_catalogo</code></td><td>No</td><td>R216.34-10030</td></tr>
      </tbody>
      </table>
      <div style="margin-top:1rem">
        <a class="btn" href="/importa/template">&#8659; Scarica template Excel</a>
      </div>
    </div>
  </div>

  <div>
    {% if risultato %}
    <div class="card">
      <h2>Risultato import</h2>
      <div class="grid2" style="margin-bottom:1rem">
        <div class="stat"><div class="stat-n" style="color:#166534">{{ risultato.inseriti }}</div>
             <div class="stat-l">Inseriti</div></div>
        <div class="stat"><div class="stat-n" style="color:#854d0e">{{ risultato.aggiornati }}</div>
             <div class="stat-l">Aggiornati</div></div>
      </div>
      {% if risultato.errori %}
      <div class="flash err">
        <b>{{ risultato.errori|length }} errori:</b><br>
        {% for e in risultato.errori %}<div>{{ e }}</div>{% endfor %}
      </div>
      {% endif %}
      {% if risultato.dry_run %}
      <div class="flash warn">
        Simulazione completata — nessun dato scritto nel database.
      </div>
      {% endif %}
    </div>
    {% endif %}

    <div class="card">
      <h2>Oppure usa il Format Learner</h2>
      <p style="font-size:13px;color:#555;margin-bottom:1rem">
        Se il file viene da un CAM (hyperMILL, WorkNC, Mastercam...),
        usa il Format Learner per imparare automaticamente la struttura
        e convertirla nel formato del database master.
      </p>
      <a class="btn btn-p" href="http://localhost:5001" target="_blank">
        Apri Format Learner &#8599;
      </a>
    </div>
  </div>
</div>
""")

UPLOAD_DIR = tempfile.mkdtemp()

@app.route('/importa', methods=['GET','POST'])
def importa():
    risultato = None
    if request.method == 'POST':
        f = request.files.get('file')
        dry_run = bool(request.form.get('dry_run'))
        if f and f.filename:
            import_path = os.path.join(UPLOAD_DIR, f.filename)
            f.save(import_path)
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                from importers.import_from_excel import importa as do_import
                risultato = do_import(import_path, dry_run=dry_run)
                risultato['dry_run'] = dry_run
            except Exception as e:
                risultato = {'inseriti':0,'aggiornati':0,'errori':[str(e)],'dry_run':dry_run}
    return render_template_string(IMPORTA_HTML,
        risultato=risultato, active='importa', msg='', mtype='')

@app.route('/importa/template')
def importa_template():
    try:
        import pandas as pd, io
        cols = ['codice_interno','descrizione','tipo','diametro_mm','raggio_punta_mm',
                'lunghezza_totale_mm','lunghezza_tagl_mm','num_taglienti','materiale',
                'codice_catalogo','angolo_punta_gradi','angolo_elica_gradi','note']
        esempio = [{'codice_interno':'FP-D10-R0-L75','descrizione':'Fresa piatta D10 Z4',
                    'tipo':'FLAT','diametro_mm':10.0,'raggio_punta_mm':0.0,
                    'lunghezza_totale_mm':75.0,'lunghezza_tagl_mm':22.0,
                    'num_taglienti':4,'materiale':'HM','codice_catalogo':'',
                    'angolo_punta_gradi':None,'angolo_elica_gradi':30,'note':''},
                   {'codice_interno':'SB-D10-R5-L75','descrizione':'Fresa sferica D10',
                    'tipo':'BALL','diametro_mm':10.0,'raggio_punta_mm':5.0,
                    'lunghezza_totale_mm':75.0,'lunghezza_tagl_mm':22.0,
                    'num_taglienti':4,'materiale':'HM','codice_catalogo':'',
                    'angolo_punta_gradi':None,'angolo_elica_gradi':30,'note':''}]
        df = pd.DataFrame(esempio, columns=cols)
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name='template_utensili.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return redirect(url_for('importa', msg=f'Errore template: {e}', mtype='err'))

# ---------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------
EXPORT_HTML = BASE.replace('{% block content %}{% endblock %}', """
<h2 style="margin:0 0 1.25rem;font-size:1.1rem">Export CAM</h2>
<div class="grid2">
  <div>
    <div class="card">
      <h2>Esporta tutti i formati attivi</h2>
      <p style="font-size:13px;color:#555;margin:0 0 .75rem">
        Genera uno ZIP con i file per tutti i formati attivi.
      </p>
      {% if formati_attivi %}
      <div style="margin-bottom:.75rem">
        {% for f in formati_attivi %}<span class="tag">{{ f }}</span>{% endfor %}
      </div>
      <form method="post" action="/export/tutti">
        <button class="btn btn-s btn-lg" type="submit">
          &#8659; Esporta tutti ({{ formati_attivi|length }})
        </button>
      </form>
      {% else %}
      <div class="flash warn">
        Nessun formato attivo.
        <a href="/impostazioni">Configura in Impostazioni</a>.
      </div>
      {% endif %}
    </div>
    <div class="card">
      <h2>Esporta singolo formato</h2>
      {% if tutti_profili %}
      <div style="display:flex;flex-direction:column;gap:.5rem">
        {% for p in tutti_profili %}
        <div style="display:flex;align-items:center;justify-content:space-between;
                    padding:.6rem .75rem;border:1px solid #e2e2df;border-radius:6px">
          <div>
            <span style="font-weight:500;font-size:13px">{{ p.nome }}</span>
            <span style="color:#888;font-size:12px;margin-left:.4rem">{{ p.software }} {{ p.versione }}</span>
            <span class="badge {{ 'b-ok' if p.nome in formati_attivi else 'b-off' }}" style="margin-left:.4rem">
              {{ 'attivo' if p.nome in formati_attivi else 'non attivo' }}
            </span>
          </div>
          <form method="post" action="/export/singolo">
            <input type="hidden" name="profilo" value="{{ p.nome }}">
            <button class="btn btn-p" type="submit" style="padding:5px 12px;font-size:12px">Esporta</button>
          </form>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <p style="color:#aaa;font-size:13px">
        Nessun profilo. <a href="http://localhost:5001" target="_blank">Crea con Format Learner</a>.
      </p>
      {% endif %}
    </div>
  </div>
  <div>
    <div class="card">
      <h2>Come aggiungere un formato</h2>
      <ol style="font-size:13px;color:#555;line-height:2;padding-left:1.25rem;margin:0">
        <li>Esporta un file campione dal CAM</li>
        <li>Apri <a href="http://localhost:5001" target="_blank">Format Learner (porta 5001)</a></li>
        <li>Carica il file — mappatura automatica</li>
        <li>Salva il profilo</li>
        <li>Attivalo in <a href="/impostazioni">Impostazioni</a></li>
      </ol>
    </div>
    <div class="card">
      <h2>Ultimi export</h2>
      {% if logs %}
      <table><thead><tr><th>Data</th><th>Formato</th><th>Utensili</th></tr></thead>
      <tbody>{% for l in logs %}
      <tr><td style="font-size:12px;color:#888">{{ l.timestamp[:16] }}</td>
          <td><span class="badge b-ok">{{ l.cam }}</span></td>
          <td>{{ l.num_utensili }}</td></tr>
      {% endfor %}</tbody></table>
      {% else %}
      <p style="color:#aaa;font-size:13px;text-align:center;padding:1rem">Nessun export ancora.</p>
      {% endif %}
    </div>
  </div>
</div>
""")

@app.route('/export')
def export_page():
    cfg=carica_config()
    try:
        conn=get_conn()
        logs=[dict(r) for r in conn.execute("SELECT * FROM log_export ORDER BY timestamp DESC LIMIT 10").fetchall()]
        conn.close()
    except: logs=[]
    return render_template_string(EXPORT_HTML,
        formati_attivi=cfg.get('formati_attivi',[]),
        tutti_profili=profili_learner(), logs=logs,
        active='export', msg=request.args.get('msg',''), mtype=request.args.get('mtype',''))

@app.route('/export/tutti', methods=['POST'])
def export_tutti():
    cfg=carica_config(); formati=cfg.get('formati_attivi',[])
    if not formati:
        return redirect(url_for('export_page',msg='Nessun formato attivo.',mtype='warn'))
    tmp=tempfile.mkdtemp(); session_dir=os.path.join(tmp,'export')
    errori=[]; ok=[]
    for nome in formati:
        try:
            path=esporta_profilo(nome,session_dir); ok.append(path)
            conn=get_conn()
            conn.execute("INSERT INTO log_export (cam,num_utensili,file_output) VALUES (?,?,?)",
                         (nome.upper(),_conta(),path)); conn.commit(); conn.close()
        except Exception as e: errori.append(f'{nome}: {e}')
    if not ok:
        return redirect(url_for('export_page',msg=f'Errori: {"; ".join(errori)}',mtype='err'))
    from datetime import datetime
    ts=datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_path=os.path.join(tmp,f'export_cam_{ts}.zip')
    with zipfile.ZipFile(zip_path,'w') as z:
        for f in ok: z.write(f,os.path.basename(f))
    return send_file(zip_path,as_attachment=True,download_name=f'export_cam_{ts}.zip')

@app.route('/export/singolo', methods=['POST'])
def export_singolo():
    nome=request.form.get('profilo','').strip()
    if not nome:
        return redirect(url_for('export_page',msg='Profilo non specificato',mtype='err'))
    tmp=tempfile.mkdtemp()
    try:
        path=esporta_profilo(nome,tmp)
        conn=get_conn()
        conn.execute("INSERT INTO log_export (cam,num_utensili,file_output) VALUES (?,?,?)",
                     (nome.upper(),_conta(),path)); conn.commit(); conn.close()
        return send_file(path,as_attachment=True,download_name=os.path.basename(path))
    except Exception as e:
        return redirect(url_for('export_page',msg=f'Errore: {e}',mtype='err'))

# ---------------------------------------------------------------
# IMPOSTAZIONI
# ---------------------------------------------------------------
IMPOSTAZIONI_HTML = BASE.replace('{% block content %}{% endblock %}', """
<h2 style="margin:0 0 1.25rem;font-size:1.1rem">Impostazioni</h2>
<div class="grid2">
  <div>
    <div class="card">
      <h2>Formati export attivi</h2>
      <form method="post" action="/impostazioni/formati">
      <div style="display:flex;flex-direction:column;gap:.5rem;margin-bottom:1rem">
        {% for p in tutti_profili %}
        <label style="display:flex;align-items:center;gap:.75rem;padding:.6rem .75rem;
                      border:1px solid #e2e2df;border-radius:6px;cursor:pointer">
          <input type="checkbox" name="formati" value="{{ p.nome }}"
                 {{ 'checked' if p.nome in formati_attivi }} style="width:16px;height:16px">
          <span style="font-weight:500;font-size:13px">{{ p.nome }}</span>
          <span style="color:#888;font-size:12px">{{ p.software }} {{ p.versione }}</span>
        </label>
        {% else %}
        <p style="color:#aaa;font-size:13px">
          Nessun profilo. <a href="http://localhost:5001" target="_blank">Crea con Format Learner</a>.
        </p>
        {% endfor %}
      </div>
      {% if tutti_profili %}<button class="btn btn-p" type="submit">Salva</button>{% endif %}
      </form>
    </div>
  </div>
  <div>
    <div class="card">
      <h2>Scheduler export automatico</h2>
      <form method="post" action="/impostazioni/scheduler">
      <div class="field" style="margin-bottom:1rem">
        <label>Ora export giornaliero</label>
        <input type="time" name="export_ora" value="{{ cfg_ora }}" style="width:auto">
      </div>
      <div class="field" style="margin-bottom:1rem">
        <label>Cartella di rete (opzionale)</label>
        <input type="text" name="output_rete" value="{{ cfg_rete }}"
               placeholder="es. /Volumes/SERVER/CAM_export">
        <p class="hint">Se configurata, i file vengono copiati automaticamente.</p>
      </div>
      <div class="field" style="margin-bottom:1rem">
        <label>Mantieni ultimi N export</label>
        <input type="text" name="keep_last_n" value="{{ cfg_keep }}" style="width:80px">
      </div>
      <button class="btn btn-p" type="submit">Salva</button>
      </form>
    </div>
    <div class="card">
      <h2>Comandi terminale</h2>
      <div style="font-size:12px;color:#555;display:flex;flex-direction:column;gap:.4rem">
        <div style="background:#f4f4f2;border-radius:5px;padding:.5rem .75rem">
          <code>bash start.sh</code> — Avvia tutto</div>
        <div style="background:#f4f4f2;border-radius:5px;padding:.5rem .75rem">
          <code>python scheduler.py --now</code> — Export immediato</div>
        <div style="background:#f4f4f2;border-radius:5px;padding:.5rem .75rem">
          <code>python scheduler.py --watch</code> — Export on-change</div>
        <div style="background:#f4f4f2;border-radius:5px;padding:.5rem .75rem">
          <code>python scheduler.py --daemon</code> — Export notturno</div>
      </div>
    </div>
  </div>
</div>
""")

@app.route('/impostazioni')
def impostazioni():
    cfg=carica_config()
    return render_template_string(IMPOSTAZIONI_HTML,
        tutti_profili=profili_learner(),
        formati_attivi=cfg.get('formati_attivi',[]),
        cfg_ora=cfg.get('export_ora','22:00'),
        cfg_rete=cfg.get('output_rete',''),
        cfg_keep=cfg.get('keep_last_n',7),
        active='impostazioni', msg=request.args.get('msg',''), mtype='')

@app.route('/impostazioni/formati', methods=['POST'])
def salva_formati():
    cfg=carica_config(); cfg['formati_attivi']=request.form.getlist('formati'); salva_config(cfg)
    return redirect(url_for('impostazioni',msg=f'Formati: {", ".join(cfg["formati_attivi"]) or "nessuno"}'))

@app.route('/impostazioni/scheduler', methods=['POST'])
def salva_scheduler():
    cfg=carica_config()
    cfg['export_ora']=request.form.get('export_ora','22:00')
    cfg['output_rete']=request.form.get('output_rete','').strip()
    cfg['keep_last_n']=int(request.form.get('keep_last_n',7) or 7)
    salva_config(cfg)
    return redirect(url_for('impostazioni',msg='Impostazioni salvate'))

# ---------------------------------------------------------------
# LOG
# ---------------------------------------------------------------
LOG_HTML = BASE.replace('{% block content %}{% endblock %}', """
<h2 style="margin:0 0 1.25rem;font-size:1.1rem">Log export</h2>
<div class="card">
<table><thead><tr><th>Data</th><th>Formato</th><th>Utensili</th><th>File</th></tr></thead>
<tbody>
{% for l in logs %}
<tr><td style="font-size:12px;color:#888">{{ l.timestamp }}</td>
    <td><span class="badge b-ok">{{ l.cam }}</span></td>
    <td>{{ l.num_utensili }}</td>
    <td style="font-size:12px;color:#555">{{ l.file_output or '-' }}</td></tr>
{% else %}
<tr><td colspan="4" style="text-align:center;color:#aaa;padding:2rem">Nessun export ancora.</td></tr>
{% endfor %}
</tbody></table>
</div>
""")

@app.route('/log')
def log_page():
    try:
        conn=get_conn()
        logs=[dict(r) for r in conn.execute("SELECT * FROM log_export ORDER BY timestamp DESC LIMIT 100").fetchall()]
        conn.close()
    except: logs=[]
    return render_template_string(LOG_HTML,logs=logs,active='log',msg='',mtype='')

# ---------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__),'..','logs'), exist_ok=True)
    print('')
    print('  Tool DB Manager  ->  http://localhost:5000')
    print('  Format Learner   ->  python learner/app_learner.py  (porta 5001)')
    print('')
    app.run(debug=True, port=5000, use_reloader=False)
