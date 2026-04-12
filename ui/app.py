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
def _ensure_db():
    """Crea cartella e DB automaticamente se non esistono."""
    db_dir = os.path.dirname(DB_PATH)
    os.makedirs(db_dir, exist_ok=True)
    if not os.path.exists(DB_PATH):
        schema_path = os.path.join(db_dir, 'schema.sql')
        conn_tmp = sqlite3.connect(DB_PATH)
        if os.path.exists(schema_path):
            with open(schema_path, encoding='utf-8') as f:
                conn_tmp.executescript(f.read())
            conn_tmp.commit()
        conn_tmp.close()

def get_conn():
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
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
  <a href="/cam" class="{{ 'active' if active=='cam' }}">CAM</a>
  <a href="/importa" class="{{ 'active' if active=='importa' }}">Importa</a>
  <a href="/impostazioni" class="{{ 'active' if active=='impostazioni' }}">Impostazioni</a>
  <a href="/test-agente" {% if active=='test' %}class="active"{% endif %}
       style="color:{% if active=='test' %}#fff{% else %}#fbbf24{% endif %}">&#129516; Test AI</a>
    <a href="/verifica" class="{{ 'active' if active=='verifica' }}"
     style="color:{% if active=='verifica' %}#fff{% else %}#4ade80{% endif %}">&#9989; Verifica</a>
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
    <a class="btn btn-p" href="/utensile/nuovo">+ Nuovo</a>
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
<div style="display:flex;gap:.5rem;margin-bottom:.75rem;flex-wrap:wrap;align-items:center">
  <input type="text" id="search"
         placeholder="&#128269;  Cerca codice, descrizione, pinza... (Ctrl+F)"
         oninput="filtra()"
         style="flex:1;min-width:200px;padding:8px 12px;border:2px solid #e2e2df;border-radius:6px;font-size:13px">
  <select id="filtro-tipo" onchange="filtra()"
          style="padding:8px 10px;border:2px solid #e2e2df;border-radius:6px;font-size:13px;background:#fff">
    <option value="">Tutti i tipi</option>
    {% for t in tipi_lista %}<option value="{{ t }}">{{ t }}</option>{% endfor %}
  </select>
  <select id="filtro-pinza" onchange="filtra()"
          style="padding:8px 10px;border:2px solid #e2e2df;border-radius:6px;font-size:13px;background:#fff;max-width:180px">
    <option value="">Tutte le pinze</option>
    {% for p in pinze_lista %}<option value="{{ p }}">{{ p }}</option>{% endfor %}
  </select>
  <span id="count-vis" style="font-size:12px;color:#888;white-space:nowrap">{{ n }} utensili</span>
</div>

<div style="overflow-x:auto">
<table id="tbl">
<thead><tr>
  <th>Codice / Descrizione</th>
  <th>Tipo</th>
  <th style="text-align:right">&#8960; mm</th>
  <th style="text-align:right">R mm</th>
  <th style="text-align:right">L tot</th>
  <th style="background:#f0fdf4;color:#166534;text-align:right">Fuori pinza</th>
  <th>Pinza</th>
  <th style="text-align:center">Z</th>
  <th style="width:90px"></th>
</tr></thead>
<tbody>
{% for u in utensili %}
<tr data-search="{{ (u.codice_interno ~ ' ' ~ (u.descrizione or '') ~ ' ' ~ (u.nome_pinza or ''))|lower }}"
    data-tipo="{{ u.tipo }}"
    data-pinza="{{ u.nome_pinza or '' }}">
  <td>
    {% if u.fuori_pinza_mm and u.nome_pinza and u.num_taglienti %}
      <span title="Dati completi" style="color:#166534;font-size:10px">&#9679;</span>
    {% elif u.fuori_pinza_mm %}
      <span title="Dati parziali" style="color:#854d0e;font-size:10px">&#9679;</span>
    {% else %}
      <span title="Fuori pinza mancante!" style="color:#991b1b;font-size:10px">&#9888;</span>
    {% endif %}
    <a href="/utensile/{{ u.id }}" style="font-weight:600;font-size:13px;color:#1a1a1a;text-decoration:none">
      {{ u.codice_interno }}
    </a>
    {% if u.descrizione %}
    <div style="font-size:11px;color:#888;margin-top:1px">{{ u.descrizione[:45] }}</div>
    {% endif %}
  </td>
  <td><span class="badge b-ok">{{ u.tipo }}</span></td>
  <td style="text-align:right;font-family:monospace;font-size:13px">{{ u.diametro_mm }}</td>
  <td style="text-align:right;font-family:monospace;font-size:13px;color:#888">
    {{ u.raggio_punta_mm if u.raggio_punta_mm else '0' }}
  </td>
  <td style="text-align:right;font-family:monospace;font-size:13px;color:#888">{{ u.lunghezza_totale_mm }}</td>
  <td style="text-align:right;background:#f0fdf4;padding-right:12px">
    {% if u.fuori_pinza_mm %}
    <b style="color:#1a6e35;font-family:monospace">{{ u.fuori_pinza_mm }}</b>
    <span style="font-size:11px;color:#888"> mm</span>
    {% else %}
    <span style="color:#ddd">—</span>
    {% endif %}
  </td>
  <td style="font-size:12px;color:#666;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
      title="{{ u.nome_pinza or '' }}">{{ u.nome_pinza or '—' }}</td>
  <td style="text-align:center;font-size:13px;font-weight:600">{{ u.num_taglienti }}</td>
  <td style="white-space:nowrap;text-align:right">
    <a class="btn" style="padding:3px 8px;font-size:12px" title="Dettaglio"
       href="/utensile/{{ u.id }}">&#8505;</a>
    <a class="btn" style="padding:3px 8px;font-size:12px" title="Modifica"
       href="/utensile/{{ u.id }}/modifica">&#9998;</a>
    <a class="btn btn-d" style="padding:3px 8px;font-size:11px" title="Elimina"
       href="/utensile/{{ u.id }}/elimina"
       onclick="return confirm('Eliminare ' + '{{ u.codice_interno }}' + '?')">&#128465;</a>
  </td>
</tr>
{% endfor %}
</tbody></table>
</div>

<script>
function filtra(){
  var q=document.getElementById('search').value.toLowerCase();
  var tipo=document.getElementById('filtro-tipo').value;
  var pinza=document.getElementById('filtro-pinza').value;
  var n=0;
  document.querySelectorAll('#tbl tbody tr').forEach(function(r){
    var ok=true;
    if(q && !r.dataset.search.includes(q)) ok=false;
    if(tipo && r.dataset.tipo!==tipo) ok=false;
    if(pinza && r.dataset.pinza!==pinza) ok=false;
    r.style.display=ok?'':'none';
    if(ok) n++;
  });
  document.getElementById('count-vis').textContent=n+' utensili';
}
document.addEventListener('keydown',function(e){
  if((e.ctrlKey||e.metaKey)&&e.key==='f'){
    e.preventDefault();
    var s=document.getElementById('search');
    s.focus(); s.select();
  }
});
</script>
{% else %}
<div style="text-align:center;padding:3rem;color:#aaa">
  <div style="font-size:3rem;margin-bottom:.5rem">&#128295;</div>
  <p style="margin-bottom:1rem">Nessun utensile nel database.</p>
  <a class="btn btn-p" href="/utensile/nuovo" style="margin-right:.5rem">+ Inserisci manualmente</a>
  <a class="btn" href="/importa">&#8657; Importa da Cimatron</a>
</div>
{% endif %}
</div>
""")

@app.route('/')
def home():
    def arrotonda(v, dec=3):
        if v is None: return v
        try:
            f = float(v)
            return round(f, 1) if abs(f - round(f)) < 0.0001 else round(f, dec)
        except: return v

    try:
        conn=get_conn()
        rows=conn.execute(
            "SELECT * FROM utensile_completo WHERE attivo=1 ORDER BY tipo, diametro_mm, codice_interno"
        ).fetchall()
        conn.close()
        utensili=[]
        for row in rows:
            u = dict(row)
            for campo in ['diametro_mm','raggio_punta_mm','lunghezza_totale_mm',
                          'lunghezza_tagl_mm','fuori_pinza_mm','lungh_presa_mm']:
                if u.get(campo) is not None:
                    u[campo] = arrotonda(u[campo])
            utensili.append(u)
    except Exception: utensili=[]
    cfg=carica_config(); profili=profili_learner()
    tipi_lista  = sorted(set(u['tipo']       for u in utensili if u.get('tipo')))
    pinze_lista = sorted(set(u['nome_pinza'] for u in utensili if u.get('nome_pinza')))
    return render_template_string(HOME_HTML,
        utensili=utensili, n=len(utensili),
        n_tipi=len(tipi_lista),
        n_profili=len(profili),
        n_attivi=len(cfg.get('formati_attivi',[])),
        tipi_lista=tipi_lista,
        pinze_lista=pinze_lista,
        msg=request.args.get('msg',''),
        mtype=request.args.get('mtype',''))

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

        params = {
            'codice_catalogo':    f.get('codice_catalogo','').strip() or None,
            'descrizione':        f.get('descrizione','').strip() or None,
            'id_tipo':            tipo_id,
            'id_materiale':       mat_id,
            'id_fornitore':       forn_id,
            'diametro_mm':        flt('diametro_mm', 0),
            'raggio_punta_mm':    flt('raggio_punta_mm', 0),
            'angolo_punta_gradi': flt('angolo_punta_gradi'),
            'lunghezza_totale_mm':flt('lunghezza_totale_mm', 0),
            'lunghezza_tagl_mm':  flt('lunghezza_tagl_mm', 0),
            'num_taglienti':      intt('num_taglienti', 2),
            'angolo_elica_gradi': flt('angolo_elica_gradi'),
            'passo_mm':           flt('passo_mm'),
            'note':               f.get('note','').strip() or None,
            # Assemblaggio pinza - DATO FONDAMENTALE
            'nome_pinza':         f.get('nome_pinza','').strip() or None,
            'lungh_presa_mm':     flt('lungh_presa_mm'),
            'fuori_pinza_mm':     flt('fuori_pinza_mm'),
        }

        if uid:
            sets = ', '.join(f"{k}=:{k}" for k in params)
            conn.execute(f"UPDATE utensile SET {sets} WHERE id=:uid",
                         {**params, 'uid': uid})
            msg = 'Utensile aggiornato.'
        else:
            codice = f.get('codice_interno','').strip()
            if not codice: raise ValueError('Codice interno obbligatorio')
            cols = 'codice_interno, ' + ', '.join(params.keys())
            vals = ':codice_interno, ' + ', '.join(f':{k}' for k in params)
            conn.execute(f"INSERT INTO utensile ({cols}) VALUES ({vals})",
                         {'codice_interno': codice, **params})
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
                 accept=".xlsx,.xls,.csv,.zip" style="display:none"
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
      {% if risultato.software %}
      <div class="flash info" style="background:#e0f2fe;border-color:#0284c7;color:#0c4a6e;margin-bottom:.5rem">
        🤖 <b>Formato rilevato:</b> {{ risultato.software }}
        {% if risultato.confidence %} &nbsp;|&nbsp; <b>Confidenza:</b> {{ "%.0f"|format(risultato.confidence*100) }}%{% endif %}
        {% if risultato.ai_usato %} &nbsp;|&nbsp; ✅ AI mapping attivo{% else %} &nbsp;|&nbsp; 🔸 Mapping euristico (nessuna API key){% endif %}
        {% if risultato.righe_totali %} &nbsp;|&nbsp; {{ risultato.righe_totali }} righe analizzate{% endif %}
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

@app.route('/importa_locale', methods=['GET','POST'])
def importa_locale():
    """Importa direttamente da un path file locale - bypassa upload browser."""
    if request.method == 'POST':
        filepath = request.form.get('filepath','').strip()
        dry_run  = bool(request.form.get('dry_run'))
        if not filepath or not os.path.exists(filepath):
            return render_template_string(IMPORTA_LOCALE_HTML,
                msg=f'File non trovato: {filepath}', risultato=None)
        try:
            _root    = os.path.join(os.path.dirname(__file__), '..')
            _learner = os.path.join(_root, 'learner')
            for _p in [_root, _learner]:
                if _p not in sys.path: sys.path.insert(0, _p)
            with open(filepath, 'rb') as f:
                magic = f.read(2)
            if magic in (b'\xff\xfe', b'\xfe\xff'):
                from cimatron_importer import importa_file
                r = importa_file(filepath, dry_run=dry_run)
                risultato = {
                    'inseriti':          r.get('utensili_inseriti', 0),
                    'aggiornati':        r.get('utensili_aggiornati', 0),
                    'errori':            r.get('utensili_errori', []),
                    'dry_run':           dry_run,
                    'versione':          r.get('versione', ''),
                    'taglio_inserite':   r.get('taglio_inserite', 0),
                    'taglio_aggiornate': r.get('taglio_aggiornate', 0),
                }
            else:
                risultato = {'inseriti':0,'aggiornati':0,
                             'errori':[f'Non riconosciuto come Cimatron. Magic: {magic.hex()}'],
                             'dry_run':dry_run}
        except Exception as e:
            risultato = {'inseriti':0,'aggiornati':0,'errori':[str(e)],'dry_run':dry_run}
        return render_template_string(IMPORTA_LOCALE_HTML, msg='', risultato=risultato)
    return render_template_string(IMPORTA_LOCALE_HTML, msg='', risultato=None)

IMPORTA_LOCALE_HTML = BASE.replace('{% block content %}{% endblock %}', """
<h2 style="margin:0 0 1.25rem;font-size:1.1rem">Import diretto da file locale</h2>
<div class="card">
  <p style="font-size:13px;color:#555;margin:0 0 1rem">
    Inserisci il percorso completo del file sul Mac. Utile per file Cimatron CSV/ZIP/XLS.
  </p>
  <form method="post" action="/importa_locale">
    <div class="field" style="margin-bottom:1rem">
      <label style="font-size:12px;font-weight:600">Percorso file</label>
      <input type="text" name="filepath" style="width:100%;font-family:monospace"
             placeholder="/Users/iondodon/Documents/Cimatron_2025.csv">
    </div>
    <div style="display:flex;gap:1rem;align-items:center">
      <button class="btn btn-s" type="submit">Importa</button>
      <label style="font-size:13px;cursor:pointer">
        <input type="checkbox" name="dry_run" value="1"> Simulazione
      </label>
    </div>
  </form>
</div>
{% if risultato %}
<div class="card">
  <div class="grid4">
    <div class="stat"><div class="stat-n" style="color:#1a6e35">{{ risultato.inseriti }}</div><div class="stat-l">Inseriti</div></div>
    <div class="stat"><div class="stat-n" style="color:#854d0e">{{ risultato.aggiornati }}</div><div class="stat-l">Aggiornati</div></div>
    <div class="stat"><div class="stat-n">{{ risultato.get('taglio_inserite',0) }}</div><div class="stat-l">Vc/Fz inserite</div></div>
    <div class="stat"><div class="stat-n">{{ risultato.versione or '-' }}</div><div class="stat-l">Versione</div></div>
  </div>
  {% if risultato.errori %}
  <div class="flash err" style="margin-top:1rem">
    {% for e in risultato.errori[:5] %}<div>{{ e }}</div>{% endfor %}
  </div>
  {% endif %}
  {% if risultato.dry_run %}
  <div class="flash warn" style="margin-top:1rem">Simulazione — nessun dato scritto.</div>
  {% else %}
  <div class="flash" style="margin-top:1rem">Import completato nel database master.</div>
  {% endif %}
</div>
{% endif %}
{% if msg %}<div class="flash err">{{ msg }}</div>{% endif %}
""")


@app.route('/utensile/<int:uid>')
def utensile_dettaglio(uid):
    conn = get_conn()
    try:
        u = conn.execute("SELECT * FROM utensile_completo WHERE id=?", (uid,)).fetchone()
        if not u:
            return redirect(url_for('home', msg='Utensile non trovato', mtype='err'))
        taglio = conn.execute(
            "SELECT * FROM condizioni_taglio WHERE id_utensile=? ORDER BY materiale_pezzo", (uid,)
        ).fetchall()
        # Segmenti portautensile se presente
        holder_segs = []
        if dict(u).get('portautensile'):
            ph = conn.execute("SELECT id FROM portautensile WHERE codice_interno=?",
                              (u['portautensile'],)).fetchone()
            if ph:
                holder_segs = conn.execute(
                    "SELECT * FROM portautensile_segmento WHERE id_portautensile=? AND altezza_totale_mm>0 ORDER BY numero_segmento",
                    (ph['id'],)
                ).fetchall()
    finally:
        conn.close()
    return render_template_string(DETTAGLIO_HTML,
        u=dict(u), taglio=[dict(t) for t in taglio],
        holder_segs=[dict(s) for s in holder_segs],
        active='home', msg='', mtype='')

DETTAGLIO_HTML = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;align-items:center;gap:.75rem;margin-bottom:1.5rem">
  <a href="/" class="btn">&#8592; Lista</a>
  <h2 style="margin:0;font-size:1.1rem">{{ u.codice_interno }}</h2>
  <span class="badge b-ok">{{ u.tipo }}</span>
  {% if u.tecnologia %}<span class="badge b-off">{{ u.tecnologia }}</span>{% endif %}
  <a class="btn" style="margin-left:auto" href="/utensile/{{ u.id }}/modifica">Modifica</a>
</div>

<div class="grid2" style="margin-bottom:1.25rem">

  <!-- COLONNA SINISTRA: geometria + stelo -->
  <div>
    <div class="card">
      <h2>Geometria utensile</h2>
      <table><tbody>
        <tr><td style="color:#888;width:55%">Codice catalogo</td><td>{{ u.codice_catalogo or '-' }}</td></tr>
        <tr><td style="color:#888">Descrizione</td><td>{{ u.descrizione or '-' }}</td></tr>
        <tr><td style="color:#888">Sito web</td><td>{% if u.sito_web %}<a href="{{ u.sito_web }}" target="_blank">{{ u.sito_web }}</a>{% else %}-{% endif %}</td></tr>
        <tr><td style="color:#888">Tipo</td><td><span class="badge b-ok">{{ u.tipo }}</span></td></tr>
        <tr><td style="color:#888">Materiale tagliente</td><td>{{ u.materiale }}</td></tr>
        <tr style="background:#f8f8f6"><td style="color:#555;font-weight:600">Diametro</td><td><b>{{ u.diametro_mm }} mm</b></td></tr>
        <tr><td style="color:#888">Raggio punta</td><td>{{ u.raggio_punta_mm }} mm</td></tr>
        {% if u.angolo_punta_gradi %}<tr><td style="color:#888">Angolo punta</td><td>{{ u.angolo_punta_gradi }}°</td></tr>{% endif %}
        {% if u.angolo_conico_gradi and u.conico %}<tr><td style="color:#888">Angolo conico</td><td>{{ u.angolo_conico_gradi }}°</td></tr>{% endif %}
        <tr style="background:#f8f8f6"><td style="color:#555;font-weight:600">Lunghezza totale</td><td><b>{{ u.lunghezza_totale_mm }} mm</b></td></tr>
        <tr><td style="color:#888">Lunghezza utile</td><td>{{ u.lunghezza_tagl_mm }} mm</td></tr>
        {% if u.lunghezza_tagl2_mm %}<tr><td style="color:#888">Lunghezza tagliente</td><td>{{ u.lunghezza_tagl2_mm }} mm</td></tr>{% endif %}
        <tr><td style="color:#888">Numero taglienti</td><td>{{ u.num_taglienti }}</td></tr>
        {% if u.passo_mm %}<tr><td style="color:#888">Passo filetto</td><td>{{ u.passo_mm }} mm</td></tr>{% endif %}
      </tbody></table>
    </div>

    {% if u.diam_stelo_sup_mm %}
    <div class="card">
      <h2>Stelo</h2>
      <table><tbody>
        <tr><td style="color:#888;width:55%">Diam. superiore stelo</td><td>{{ u.diam_stelo_sup_mm }} mm</td></tr>
        <tr><td style="color:#888">Diam. inferiore stelo</td><td>{{ u.diam_stelo_inf_mm }} mm</td></tr>
        {% if u.lungh_libera_stelo_mm %}<tr><td style="color:#888">Lungh. libera stelo</td><td>{{ u.lungh_libera_stelo_mm }} mm</td></tr>{% endif %}
        {% if u.lungh_cono_stelo_mm %}<tr><td style="color:#888">Lungh. cono stelo</td><td>{{ u.lungh_cono_stelo_mm }} mm</td></tr>{% endif %}
        {% if u.diam_stelo2_sup_mm %}
        <tr><td colspan="2" style="font-size:11px;color:#888;padding-top:.5rem">— Stelo secondario —</td></tr>
        <tr><td style="color:#888">Diam. sup. stelo 2</td><td>{{ u.diam_stelo2_sup_mm }} mm</td></tr>
        <tr><td style="color:#888">Diam. inf. stelo 2</td><td>{{ u.diam_stelo2_inf_mm }} mm</td></tr>
        {% if u.lungh_libera_stelo2_mm %}<tr><td style="color:#888">Lungh. libera stelo 2</td><td>{{ u.lungh_libera_stelo2_mm }} mm</td></tr>{% endif %}
        {% endif %}
      </tbody></table>
    </div>
    {% endif %}
  </div>

  <!-- COLONNA DESTRA: assemblaggio + taglio default -->
  <div>
    <!-- FUORI PINZA - dato critico evidenziato -->
    <div class="card" style="border-left:4px solid #1a6e35">
      <h2>Assemblaggio con pinza</h2>
      {% if u.nome_pinza %}
      <div style="background:#f0fdf4;border-radius:8px;padding:1rem;margin-bottom:1rem">
        <div style="font-size:12px;color:#888;margin-bottom:.25rem">Portautensile / Pinza</div>
        <div style="font-weight:600;font-size:1rem">{{ u.nome_pinza }}</div>
        {% if u.adattatore %}<div style="font-size:12px;color:#666;margin-top:.2rem">{{ u.adattatore }}</div>{% endif %}
      </div>
      <table><tbody>
        <tr><td style="color:#888;width:55%">Lunghezza presa</td><td>{{ u.lungh_presa_mm }} mm <span style="font-size:11px;color:#aaa">(quanto entra nella pinza)</span></td></tr>
        <tr style="background:#f0fdf4">
          <td style="color:#155724;font-weight:700;font-size:14px">FUORI PINZA</td>
          <td>
            <b style="font-size:18px;color:#1a6e35">{{ u.fuori_pinza_mm }} mm</b>
            <span style="font-size:11px;color:#888;display:block">dalla punta all'inizio della pinza</span>
          </td>
        </tr>
        {% if u.lungh_libera_prolunga_mm %}<tr><td style="color:#888">Con prolunga</td><td>{{ u.lungh_libera_prolunga_mm }} mm</td></tr>{% endif %}
      </tbody></table>
      {% else %}
      <p style="color:#aaa;font-size:13px">Nessuna pinza associata.</p>
      {% endif %}

      {% if holder_segs %}
      <p style="font-size:12px;font-weight:600;margin:1rem 0 .5rem;color:#555">Geometria portautensile ({{ holder_segs|length }} segmenti)</p>
      <table style="font-size:12px">
      <thead><tr><th>Seg.</th><th>Ø inf (mm)</th><th>Ø sup (mm)</th><th>H cono (mm)</th><th>H tot (mm)</th></tr></thead>
      <tbody>
      {% for s in holder_segs %}
      <tr>
        <td>{{ s.numero_segmento }}</td>
        <td>{{ '%.3f'|format(s.diametro_inf_mm) if s.diametro_inf_mm else '-' }}</td>
        <td>{{ '%.3f'|format(s.diametro_sup_mm) if s.diametro_sup_mm else '-' }}</td>
        <td>{{ '%.3f'|format(s.altezza_cono_mm) if s.altezza_cono_mm else '-' }}</td>
        <td>{{ '%.3f'|format(s.altezza_totale_mm) if s.altezza_totale_mm else '-' }}</td>
      </tr>
      {% endfor %}
      </tbody></table>
      {% endif %}
    </div>

    <!-- Parametri taglio di default -->
    {% if u.vc_default or u.fz_default %}
    <div class="card">
      <h2>Parametri taglio di default <span style="font-size:11px;color:#888;font-weight:400">(dal profilo utensile)</span></h2>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:.75rem;margin-bottom:.75rem">
        {% if u.vc_default %}<div class="stat"><div class="stat-n">{{ '%.1f'|format(u.vc_default) }}</div><div class="stat-l">Vc (m/min)</div></div>{% endif %}
        {% if u.fz_default %}<div class="stat"><div class="stat-n">{{ '%.4f'|format(u.fz_default) }}</div><div class="stat-l">Fz (mm/z)</div></div>{% endif %}
        {% if u.rotazione_default %}<div class="stat"><div class="stat-n">{{ u.rotazione_default|int }}</div><div class="stat-l">N (rpm)</div></div>{% endif %}
        {% if u.avanzamento_default %}<div class="stat"><div class="stat-n">{{ u.avanzamento_default|int }}</div><div class="stat-l">Vf (mm/min)</div></div>{% endif %}
        {% if u.passo_z_default %}<div class="stat"><div class="stat-n">{{ '%.2f'|format(u.passo_z_default) }}</div><div class="stat-l">ap (mm)</div></div>{% endif %}
        {% if u.passo_lat_default %}<div class="stat"><div class="stat-n">{{ '%.3f'|format(u.passo_lat_default) }}</div><div class="stat-l">ae (mm)</div></div>{% endif %}
      </div>
      <div style="font-size:12px;color:#888">
        {% if u.dir_rotazione %}Dir: {{ u.dir_rotazione }}{% endif %}
        {% if u.refrigerante %} | Refrigerante: {{ u.refrigerante }}{% endif %}
        {% if u.vita_utensile %} | Vita: {{ u.vita_utensile }} min{% endif %}
      </div>
    </div>
    {% endif %}
  </div>
</div>

<!-- CONDIZIONI DI TAGLIO PER MATERIALE -->
<div class="card">
  <h2>Condizioni di taglio per materiale pezzo ({{ taglio|length }} materiali)</h2>
  {% if taglio %}
  <div style="overflow-x:auto">
  <table>
  <thead><tr>
    <th>Materiale pezzo</th>
    <th>Vc (m/min)</th>
    <th>Fz (mm/z)</th>
    <th>N (rpm)</th>
    <th>Vf (mm/min)</th>
    <th>ap (mm)</th>
    <th>ae (mm)</th>
    <th>Refrigerante</th>
  </tr></thead>
  <tbody>
  {% for t in taglio %}
  <tr>
    <td><b>{{ t.materiale_pezzo }}</b></td>
    <td>{{ '%.1f'|format(t.vc_m_min) if t.vc_m_min else '-' }}</td>
    <td>{{ '%.4f'|format(t.fz_mm) if t.fz_mm else '-' }}</td>
    <td>{{ t.n_rpm|int if t.n_rpm else '-' }}</td>
    <td>{{ t.vf_mm_min|int if t.vf_mm_min else '-' }}</td>
    <td>{{ '%.2f'|format(t.ap_mm) if t.ap_mm else '-' }}</td>
    <td>{{ '%.2f'|format(t.ae_mm) if t.ae_mm else '-' }}</td>
    <td style="font-size:12px;color:#888">{{ t.refrigerante or '-' }}</td>
  </tr>
  {% endfor %}
  </tbody></table>
  </div>
  {% else %}
  <p style="color:#aaa;font-size:13px;text-align:center;padding:2rem">
    Nessuna condizione di taglio. Importa il file ZIP per includerle (287 combinazioni disponibili).
  </p>
  {% endif %}
</div>
""")


@app.route('/debug_test_cimatron')
def debug_test_cimatron():
    import glob, tempfile, importlib
    tmp = tempfile.gettempdir()
    files = sorted(glob.glob(f'{tmp}/tmp*/Cimatron_2025.csv'), key=os.path.getmtime)
    if not files:
        return 'nessun file trovato'
    f = files[-1]
    with open(f, 'rb') as fh:
        magic = fh.read(2)
    is_utf16 = magic in (b'\xff\xfe', b'\xfe\xff')
    # Testa _is_cimatron dal modulo ricaricato
    _root = os.path.join(os.path.dirname(__file__), '..')
    _learner = os.path.join(_root, 'learner')
    for _p in [_root, _learner]:
        if _p not in sys.path: sys.path.insert(0, _p)
    import importers.import_from_excel as ief
    importlib.reload(ief)
    result = ief._is_cimatron(f)
    return f"file={os.path.basename(os.path.dirname(f))}/Cimatron_2025.csv<br>magic={magic.hex()}<br>is_utf16={is_utf16}<br>_is_cimatron={result}<br>module_file={ief.__file__}"


@app.route('/importa', methods=['GET','POST'])
def importa():
    risultato = None
    if request.method == 'POST':
        f = request.files.get('file')
        dry_run = bool(request.form.get('dry_run'))
        if f and f.filename:
            # Preserva nome originale con estensione
            safe_name = f.filename.replace(' ', '_')
            import_path = os.path.join(UPLOAD_DIR, safe_name)
            f.save(import_path)
            try:
                # Aggiungi path necessari
                _root = os.path.join(os.path.dirname(__file__), '..')
                _learner = os.path.join(_root, 'learner')
                for _p in [_root, _learner]:
                    if _p not in sys.path:
                        sys.path.insert(0, _p)
                # Rileva Cimatron dai magic bytes PRIMA di qualsiasi import
                with open(import_path, 'rb') as fh:
                    magic = fh.read(2)
                is_cimatron = magic in (b'\xff\xfe', b'\xfe\xff')
                # Controlla anche ZIP
                if not is_cimatron:
                    import zipfile
                    if zipfile.is_zipfile(import_path):
                        with zipfile.ZipFile(import_path) as z:
                            is_cimatron = any('Cutters' in os.path.basename(n) and n.endswith('.csv') for n in z.namelist())
                if is_cimatron:
                    from cimatron_importer import importa_file
                    r = importa_file(import_path, dry_run=dry_run)
                    risultato = {
                        'inseriti':          r.get('utensili_inseriti', 0),
                        'aggiornati':        r.get('utensili_aggiornati', 0),
                        'errori':            r.get('utensili_errori', []),
                        'dry_run':           dry_run,
                        'versione':          r.get('versione', ''),
                        'taglio_inserite':   r.get('taglio_inserite', 0),
                        'taglio_aggiornate': r.get('taglio_aggiornate', 0),
                    }
                else:
                    # Usa universal_parser per CSV/ZIP/altri formati CAM
                    _ext = os.path.splitext(import_path)[1].lower()
                    _is_excel = _ext in ('.xlsx', '.xls')
                    if not _is_excel:
                        try:
                            import importlib as _il
                            if 'universal_parser' in sys.modules:
                                _il.reload(sys.modules['universal_parser'])
                            from universal_parser import parse_any_file
                            _api_key = os.environ.get('ANTHROPIC_API_KEY', '')
                            _up_result = parse_any_file(
                                import_path,
                                api_key=_api_key if _api_key else None,
                            )
                            # Inserisce i record nel DB master
                            _ins = _agg = 0; _errs = _up_result.get('errori', [])
                            _conn = sqlite3.connect(DB_PATH)
                            _conn.row_factory = sqlite3.Row
                            for _rec in _up_result.get('records', []):
                                _cod = _rec.get('codice_interno')
                                if not _cod: continue
                                try:
                                    # Risolve id_tipo
                                    _tipo = _rec.get('tipo','FLAT')
                                    _r = _conn.execute('SELECT id FROM tipo_utensile WHERE codice=?',(_tipo,)).fetchone()
                                    if not _r:
                                        _conn.execute('INSERT OR IGNORE INTO tipo_utensile(codice,descrizione) VALUES(?,?)',(_tipo,_tipo))
                                        _r = _conn.execute('SELECT id FROM tipo_utensile WHERE codice=?',(_tipo,)).fetchone()
                                    _tid = _r['id']
                                    # Risolve id_materiale
                                    _mat = _rec.get('materiale_tagliente','HM')
                                    _rm = _conn.execute('SELECT id FROM materiale_utensile WHERE codice=?',(_mat,)).fetchone()
                                    if not _rm:
                                        _conn.execute('INSERT OR IGNORE INTO materiale_utensile(codice,descrizione) VALUES(?,?)',(_mat,_mat))
                                        _rm = _conn.execute('SELECT id FROM materiale_utensile WHERE codice=?',(_mat,)).fetchone()
                                    _mid = _rm['id']
                                    # Parametri colonna
                                    _p = {k:v for k,v in _rec.items() if k not in ('tipo','materiale_tagliente','codice_interno')}
                                    _esiste = _conn.execute('SELECT id FROM utensile WHERE codice_interno=?',(_cod,)).fetchone()
                                    # Filtra _p alle sole colonne presenti nello schema
                                    _schema_cols = {r[1] for r in _conn.execute("PRAGMA table_info(utensile)").fetchall()}
                                    _p_safe = {k:v for k,v in _p.items() if k in _schema_cols}
                                    if not dry_run:
                                        if _esiste:
                                            if _p_safe:
                                                _sets = ','.join(f'{k}=:{k}' for k in _p_safe)
                                                _conn.execute(f'UPDATE utensile SET {_sets} WHERE codice_interno=:_cod',{**_p_safe,'_cod':_cod})
                                            _agg += 1
                                        else:
                                            _cols = 'codice_interno,id_tipo,id_materiale,' + ','.join(_p_safe)
                                            _vals = ':_cod,:_tid,:_mid,' + ','.join(f':{k}' for k in _p_safe)
                                            _conn.execute(f'INSERT INTO utensile ({_cols}) VALUES ({_vals})',{**_p_safe,'_cod':_cod,'_tid':_tid,'_mid':_mid})
                                            _ins += 1
                                    else:
                                        if _esiste: _agg += 1
                                        else: _ins += 1
                                except Exception as _ex:
                                    _errs.append(f'{_cod}: {_ex}')
                            if not dry_run: _conn.commit()
                            _conn.close()
                            risultato = {
                                'inseriti': _ins, 'aggiornati': _agg, 'errori': _errs,
                                'dry_run': dry_run,
                                'software': _up_result.get('software','unknown'),
                                'confidence': _up_result.get('confidence', 0),
                                'ai_usato': _up_result.get('ai_usato', False),
                                'righe_totali': _up_result.get('righe_totali', 0),
                            }
                        except Exception as _upe:
                            _errs = [f'universal_parser: {_upe}']
                            risultato = {'inseriti':0,'aggiornati':0,'errori':_errs,'dry_run':dry_run}
                    else:
                        import importlib
                        if 'importers.import_from_excel' in sys.modules:
                            importlib.reload(sys.modules['importers.import_from_excel'])
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
# PAGINA CAM — stato decoder/generator per ogni CAM
# ---------------------------------------------------------------
CAM_HTML = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem">
  <div>
    <h2 style="margin:0;font-size:1.1rem">Formati CAM</h2>
    <p style="margin:4px 0 0;color:#888;font-size:13px">
      Stato decoder e generator per ogni sistema CAM configurato
    </p>
  </div>
  <a href="http://localhost:5001" target="_blank" class="btn">
    + Impara nuovo formato &#8599;
  </a>
</div>

<div style="display:flex;flex-direction:column;gap:1rem">
{% for cam in cams %}
<div class="card" style="border-left:4px solid {{ cam.colore }}">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem">
    <div style="display:flex;align-items:center;gap:.75rem">
      <div style="width:10px;height:10px;border-radius:50%;background:{{ cam.colore }}"></div>
      <span style="font-weight:600;font-size:1rem">{{ cam.nome }}</span>
      <span style="font-size:12px;color:#888">{{ cam.versioni }}</span>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">

    <!-- DECODER -->
    <div style="background:#f8f8f6;border-radius:8px;padding:1rem">
      <div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem">
        <span style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:#555">
          Decoder
        </span>
        <span style="background:{{ cam.decoder_bg }};color:{{ cam.decoder_color }};
                     font-size:11px;padding:2px 8px;border-radius:10px;font-weight:500">
          {{ cam.decoder_label }}
        </span>
      </div>
      <p style="font-size:12px;color:#666;margin:0 0 .5rem">{{ cam.decoder_desc }}</p>
      <p style="font-size:11px;color:#aaa;margin:0">Formati: {{ cam.decoder_fmt }}</p>
      {% if cam.decoder_stato in ('in_attesa', 'agente') %}
      <form method="post" action="/cam/{{ cam.key }}/impara" enctype="multipart/form-data"
            style="margin-top:.75rem">
        <div style="display:flex;gap:.5rem;align-items:center">
          <input type="file" name="file" style="font-size:12px;flex:1"
                 accept=".csv,.xls,.xlsx,.zip,.xml">
          <button class="btn btn-p" type="submit"
                  style="padding:5px 10px;font-size:12px;white-space:nowrap">
            Carica campione
          </button>
        </div>
      </form>
      {% endif %}
    </div>

    <!-- GENERATOR -->
    <div style="background:#f8f8f6;border-radius:8px;padding:1rem">
      <div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem">
        <span style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:#555">
          Generator
        </span>
        <span style="background:{{ cam.generator_bg }};color:{{ cam.generator_color }};
                     font-size:11px;padding:2px 8px;border-radius:10px;font-weight:500">
          {{ cam.generator_label }}
        </span>
      </div>
      <p style="font-size:12px;color:#666;margin:0 0 .5rem">{{ cam.generator_desc }}</p>
      <p style="font-size:11px;color:#aaa;margin:0">Formati: {{ cam.generator_fmt }}</p>
      {% if cam.generator_stato == 'completo' %}
      <form method="post" action="/cam/{{ cam.key }}/genera" style="margin-top:.75rem">
        <button class="btn btn-s" type="submit"
                style="padding:5px 10px;font-size:12px">
          Genera file
        </button>
      </form>
      {% endif %}
    </div>

  </div>
</div>
{% endfor %}
</div>

<div class="card" style="margin-top:1rem;background:#f8f8f6">
  <p style="font-size:13px;color:#666;margin:0">
    <b>Come aggiungere un CAM non in lista:</b>
    Esporta un file campione dal software CAM → caricalo nel
    <a href="http://localhost:5001" target="_blank">Format Learner</a> →
    il sistema impara il formato e lo aggiunge automaticamente alla lista.
    Una volta che il decoder e il generator sono attivi, il CAM appare qui completo.
  </p>
</div>
""")


@app.route('/cam')
def cam_page():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    try:
        from cam_registry import stato_sistema
        cams = stato_sistema()
    except Exception as e:
        cams = []
    return render_template_string(CAM_HTML,
        cams=cams, active='cam',
        msg=request.args.get('msg',''), mtype=request.args.get('mtype',''))


@app.route('/cam/<cam_key>/impara', methods=['POST'])
def cam_impara(cam_key):
    f = request.files.get('file')
    if not f or not f.filename:
        return redirect(url_for('cam_page', msg='Nessun file selezionato', mtype='err'))
    # Salva e manda al Format Learner
    import_path = os.path.join(UPLOAD_DIR, f.filename)
    f.save(import_path)
    return redirect(f'http://localhost:5001?file={import_path}',
                    code=302)


@app.route('/cam/<cam_key>/genera', methods=['POST'])
def cam_genera(cam_key):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    try:
        from cam_registry import genera
        import tempfile
        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, f'{cam_key}_export.csv')
        conn = get_conn()
        path = genera(cam_key, out, conn)
        conn.close()
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))
    except NotImplementedError as e:
        return redirect(url_for('cam_page', msg=str(e), mtype='warn'))
    except Exception as e:
        return redirect(url_for('cam_page', msg=f'Errore: {e}', mtype='err'))


@app.route('/verifica')
def verifica():
    """Pagina qualita dati - semaforo per ogni utensile."""
    import sys as _sys
    _root = os.path.join(os.path.dirname(__file__), '..')
    if _root not in _sys.path: _sys.path.insert(0, _root)
    try:
        from verifica_import import genera_report, CAMPI
        conn = get_conn()
        report = genera_report(conn)
        conn.close()
    except Exception as e:
        return render_template_string(BASE.replace(
            '{% block content %}{% endblock %}',
            f'<div class="card"><div class="flash err">Errore: {e}</div></div>'
        ), active='verifica', msg='', mtype='')
    return render_template_string(VERIFICA_HTML,
        report=report, active='verifica', msg='', mtype='')

@app.route('/verifica/report')
def verifica_report_html():
    """Scarica il report HTML completo."""
    import sys as _sys
    _root = os.path.join(os.path.dirname(__file__), '..')
    if _root not in _sys.path: _sys.path.insert(0, _root)
    from verifica_import import genera_html_report
    conn = get_conn()
    html = genera_html_report(conn)
    conn.close()
    from flask import Response
    return Response(html, mimetype='text/html',
        headers={'Content-Disposition': 'attachment; filename=report_qualita_utensili.html'})

VERIFICA_HTML = BASE.replace('{% block content %}{% endblock %}', """
{% set r = report.riepilogo %}
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem">
  <div>
    <h2 style="margin:0;font-size:1.1rem">Verifica qualita dati</h2>
    <p style="margin:4px 0 0;color:#888;font-size:13px">Generato il {{ report.timestamp }}</p>
  </div>
  <a href="/verifica/report" class="btn btn-s">&#8659; Scarica report HTML</a>
</div>

<!-- KPI semaforo globale -->
<div class="grid4" style="margin-bottom:1.25rem">
  <div class="stat" style="border-top:3px solid #166534">
    <div class="stat-n" style="color:#166534">{{ r.verdi }}</div>
    <div class="stat-l">&#9679; Completi (&#8805;90%)</div>
  </div>
  <div class="stat" style="border-top:3px solid #854d0e">
    <div class="stat-n" style="color:#854d0e">{{ r.gialli }}</div>
    <div class="stat-l">&#9679; Incompleti (70-89%)</div>
  </div>
  <div class="stat" style="border-top:3px solid #991b1b">
    <div class="stat-n" style="color:#991b1b">{{ r.rossi }}</div>
    <div class="stat-l">&#9679; Dati mancanti (&lt;70%)</div>
  </div>
  <div class="stat" style="border-top:3px solid #7c3aed">
    <div class="stat-n" style="color:#7c3aed">{{ r.senza_taglio }}</div>
    <div class="stat-l">Senza Vc/Fz per materiale</div>
  </div>
</div>

{% if r.rossi > 0 %}
<div class="flash err" style="margin-bottom:1rem">
  &#9888; <b>{{ r.rossi }} utensili con dati critici mancanti.</b>
  Questi utensili potrebbero causare problemi in lavorazione.
  Verifica le righe evidenziate in rosso.
</div>
{% elif r.gialli > 0 %}
<div class="flash warn" style="margin-bottom:1rem">
  &#9432; <b>{{ r.gialli }} utensili con dati incompleti.</b>
  I dati critici ci sono ma mancano informazioni opzionali utili.
</div>
{% else %}
<div class="flash" style="margin-bottom:1rem">
  &#10003; <b>Tutti i dati sono completi.</b> Database pronto per la lavorazione.
</div>
{% endif %}

<div class="card">
<div style="display:flex;gap:.5rem;margin-bottom:.75rem;align-items:center">
  <input type="text" id="sv-search" placeholder="&#128269; Cerca utensile..."
         oninput="svFiltra()"
         style="flex:1;padding:8px 12px;border:2px solid #e2e2df;border-radius:6px;font-size:13px">
  <select id="sv-filtro" onchange="svFiltra()"
          style="padding:8px;border:2px solid #e2e2df;border-radius:6px;font-size:13px;background:#fff">
    <option value="">Tutti</option>
    <option value="verde">&#9679; Completi</option>
    <option value="giallo">&#9679; Incompleti</option>
    <option value="rosso">&#9679; Mancanti</option>
  </select>
  <span id="sv-count" style="font-size:12px;color:#888;white-space:nowrap">{{ report.utensili|length }} utensili</span>
</div>

<div style="overflow-x:auto">
<table id="sv-tbl">
<thead><tr>
  <th style="width:30px"></th>
  <th>Codice utensile</th>
  <th>Tipo</th>
  <th style="text-align:right">&#8960;</th>
  <th style="text-align:right;background:#f0fdf4;color:#166534">Fuori pinza</th>
  <th style="text-align:center">Vc/Fz</th>
  <th style="text-align:center">Score</th>
  <th>Problemi rilevati</th>
</tr></thead>
<tbody>
{% for item in report.utensili %}
{% set u = item.utensile %}
{% set q = item.qualita %}
<tr data-css="{{ q.css }}"
    data-search="{{ u.codice_interno|lower }} {{ (u.descrizione or '')|lower }}">
  <td style="text-align:center;font-size:16px">
    {% if q.css == 'verde' %}
      <span title="Dati completi" style="color:#166534">&#9679;</span>
    {% elif q.css == 'giallo' %}
      <span title="Dati incompleti" style="color:#854d0e">&#9679;</span>
    {% else %}
      <span title="Dati critici mancanti" style="color:#991b1b">&#9888;</span>
    {% endif %}
  </td>
  <td>
    <a href="/utensile/{{ u.id }}" style="font-weight:600;font-size:13px;color:#1a1a1a;text-decoration:none">
      {{ u.codice_interno }}
    </a>
  </td>
  <td><span class="badge b-ok">{{ u.tipo }}</span></td>
  <td style="text-align:right;font-family:monospace">{{ u.diametro_mm }}</td>
  <td style="text-align:right;background:#f0fdf4;font-family:monospace;font-weight:600;color:#1a6e35">
    {% if u.fuori_pinza_mm %}{{ u.fuori_pinza_mm }} mm{% else %}<span style="color:#991b1b">MANCANTE</span>{% endif %}
  </td>
  <td style="text-align:center">
    {% if q.n_taglio > 0 %}
      <span style="color:#166534;font-weight:600">{{ q.n_taglio }} mat.</span>
    {% else %}
      <span style="color:#aaa;font-size:12px">nessuno</span>
    {% endif %}
  </td>
  <td style="text-align:center">
    <span style="background:{{ q.colore }}22;color:{{ q.colore }};padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600">
      {{ q.score }}%
    </span>
  </td>
  <td style="font-size:12px">
    {% if q.mancanti_critici %}
      <div style="color:#991b1b">&#9888; <b>Critici:</b> {{ q.mancanti_critici|join(', ') }}</div>
    {% endif %}
    {% if q.mancanti_facoltativi %}
      <div style="color:#854d0e">&#9432; {{ q.mancanti_facoltativi|join(', ') }}</div>
    {% endif %}
    {% if q.anomalie %}
      <div style="color:#7c3aed">&#9642; {{ q.anomalie|join(' | ') }}</div>
    {% endif %}
    {% if not q.mancanti_critici and not q.mancanti_facoltativi and not q.anomalie %}
      <span style="color:#166534">&#10003; OK</span>
    {% endif %}
  </td>
</tr>
{% endfor %}
</tbody></table>
</div>

<div style="margin-top:.75rem;font-size:12px;color:#888">
  <b>Leggenda:</b>
  &#9888; = dati critici mancanti (obbligatori per programmare) &nbsp;|&nbsp;
  &#9432; = dati facoltativi mancanti &nbsp;|&nbsp;
  &#9642; = valore fuori range tipico &nbsp;|&nbsp;
  <b>Fuori pinza</b> = distanza dalla punta all'inizio della pinza (critico per evitare collisioni)
</div>
</div>

<script>
function svFiltra(){
  var q=document.getElementById('sv-search').value.toLowerCase();
  var f=document.getElementById('sv-filtro').value;
  var n=0;
  document.querySelectorAll('#sv-tbl tbody tr').forEach(function(r){
    var ok=true;
    if(q && !r.dataset.search.includes(q)) ok=false;
    if(f && r.dataset.css!==f) ok=false;
    r.style.display=ok?'':'none';
    if(ok) n++;
  });
  document.getElementById('sv-count').textContent=n+' utensili';
}
</script>
""")



@app.route('/dev/leggi_file')
def dev_leggi_file():
    p = request.args.get('p','')
    if not p or not os.path.exists(p): return 'NOT FOUND', 404
    with open(p, encoding='utf-8') as f: return f.read(), 200, {'Content-Type':'text/plain'}

@app.route('/test-agente', methods=['GET','POST'])
def test_agente():
    """Pagina di test per l'agente multilivello - verifica ogni livello separatamente."""
    import sys as _sys
    _root = os.path.join(os.path.dirname(__file__), '..')
    if _root not in _sys.path: _sys.path.insert(0, _root)

    risultato = None
    errore = None
    log_html = ''

    if request.method == 'POST':
        azione = request.form.get('azione', '')
        try:
            import pandas as pd

            # Carica il file campione WorkNC per i test
            # Cerca cam_samples nella root del progetto
            sample_path = os.path.join(os.path.dirname(__file__), '..', 'cam_samples', 'worknc_tools_sample.csv')
            sample_path = os.path.abspath(sample_path)
            if not os.path.exists(sample_path):
                raise FileNotFoundError('File campione non trovato: ' + sample_path)
            df = pd.read_csv(sample_path)

            from learner.orchestrator_agent import (
                _get_api_key, _l2a_struttura, _l2b_colonna,
                _l3_mapping, _l4_verifica, orchestra_learning
            )
            key = _get_api_key()
            if not key:
                raise ValueError('API key non configurata')

            log_eventi = []
            def log_cb(livello, msg):
                log_eventi.append({'livello': livello, 'msg': msg})

            if azione == 'test_l2a':
                r = _l2a_struttura(df, key, log_cb)
                risultato = {'livello': 'L2a - Analista Struttura', 'output': r}

            elif azione == 'test_l2b':
                col = request.form.get('colonna', 'Radius')
                contesto = {'software_cam': 'WorkNC'}
                r = _l2b_colonna(col, df[col] if col in df.columns else df.iloc[:,0], contesto, key)
                risultato = {'livello': f'L2b - Analista Valori: colonna "{col}"', 'output': r}

            elif azione == 'test_l3':
                struttura = {'software_cam': 'WorkNC'}
                analisi = {}
                for col in df.columns:
                    analisi[col] = _l2b_colonna(col, df[col], struttura, key)
                r = _l3_mapping(analisi, struttura, key, log_cb)
                risultato = {'livello': 'L3 - Mapper', 'output': r, 'log': log_eventi}

            elif azione == 'test_completo':
                r = orchestra_learning(df, key, 'worknc_tools_sample.csv', log_cb)
                risultato = {
                    'livello': 'Test Completo L1→L4',
                    'verificato': r.get('verificato'),
                    'score': r.get('score'),
                    'n_mappati': len(r.get('profilo', {})),
                    'costo_token': r.get('costo_stimato'),
                    'profilo': r.get('profilo', {}),
                    'campi_mancanti': r.get('campi_mancanti', []),
                    'warning': r.get('warning', []),
                    'log': log_eventi,
                }

        except Exception as e:
            import traceback
            errore = traceback.format_exc()

    # Colonne del file campione per il select
    colonne_sample = []
    try:
        import pandas as pd
        sp = os.path.join(os.path.join(os.path.dirname(__file__), '..'), 'cam_samples', 'worknc_tools_sample.csv')
        if os.path.exists(sp):
            colonne_sample = list(pd.read_csv(sp).columns)
    except: pass

    return render_template_string(TEST_AGENTE_HTML,
        risultato=risultato, errore=errore,
        colonne_sample=colonne_sample,
        active='test', msg='', mtype='')

TEST_AGENTE_HTML = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.5rem">
  <div>
    <h2 style="margin:0;font-size:1.1rem">&#129516; Test Agente Multilivello</h2>
    <p style="margin:4px 0 0;color:#888;font-size:13px">
      Verifica ogni livello dell'orchestratore separatamente o esegui il test completo.
      File usato: <code>cam_samples/worknc_tools_sample.csv</code>
    </p>
  </div>
</div>

<!-- Architettura visiva -->
<div class="card" style="margin-bottom:1.25rem;background:#1a1a1a;color:#fff">
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;font-size:12px;text-align:center">
    <div style="background:#1d4ed8;border-radius:8px;padding:.75rem">
      <div style="font-size:1.5rem">&#127757;</div>
      <div style="font-weight:700;margin:.3rem 0">L1 — Orchestratore</div>
      <div style="color:#93c5fd">Sonnet</div>
      <div style="color:#bfdbfe;margin-top:.3rem">Strategia + verifica finale</div>
    </div>
    <div style="background:#166534;border-radius:8px;padding:.75rem">
      <div style="font-size:1.5rem">&#128300;</div>
      <div style="font-weight:700;margin:.3rem 0">L2a — Struttura</div>
      <div style="color:#86efac">Haiku &#128176;</div>
      <div style="color:#bbf7d0;margin-top:.3rem">Software CAM + gruppi colonne</div>
    </div>
    <div style="background:#166534;border-radius:8px;padding:.75rem">
      <div style="font-size:1.5rem">&#128202;</div>
      <div style="font-weight:700;margin:.3rem 0">L2b — Valori</div>
      <div style="color:#86efac">Haiku &#128176;&#128176;</div>
      <div style="color:#bbf7d0;margin-top:.3rem">Analisi colonna per colonna</div>
    </div>
    <div style="background:#7c3aed;border-radius:8px;padding:.75rem">
      <div style="font-size:1.5rem">&#128270;</div>
      <div style="font-weight:700;margin:.3rem 0">L4 — Verificatore</div>
      <div style="color:#c4b5fd">Sonnet</div>
      <div style="color:#ddd6fe;margin-top:.3rem">Controllo logico + correzioni</div>
    </div>
  </div>
</div>

<!-- Pulsanti test -->
<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:1rem;margin-bottom:1.25rem">

  <form method="post">
    <div class="card" style="height:100%">
      <h3 style="margin:0 0 .5rem;font-size:.95rem">&#9312; Test L2a — Analisi Struttura</h3>
      <p style="font-size:12px;color:#666;margin:0 0 1rem">
        Haiku analizza il file WorkNC e identifica: software CAM, lingua,
        gruppi di colonne (geometria, taglio, assemblaggio).
        <br><b>Costo stimato: ~800 token</b>
      </p>
      <button class="btn btn-p" type="submit" name="azione" value="test_l2a">
        &#9654; Esegui L2a
      </button>
    </div>
  </form>

  <form method="post">
    <div class="card" style="height:100%">
      <h3 style="margin:0 0 .5rem;font-size:.95rem">&#9313; Test L2b — Analisi Colonna</h3>
      <p style="font-size:12px;color:#666;margin:0 0 .75rem">
        Haiku analizza una singola colonna. Scegli una colonna "difficile" come
        <code>Radius</code> o <code>Fz</code> per vedere se capisce il significato.
        <br><b>Costo stimato: ~250 token</b>
      </p>
      <div style="display:flex;gap:.5rem;align-items:center">
        <select name="colonna" style="padding:6px;border:1px solid #ddd;border-radius:5px;font-size:13px;flex:1">
          {% for col in colonne_sample %}
          <option value="{{ col }}" {% if col=='Radius' %}selected{% endif %}>{{ col }}</option>
          {% endfor %}
        </select>
        <button class="btn btn-p" type="submit" name="azione" value="test_l2b">
          &#9654; Esegui L2b
        </button>
      </div>
    </div>
  </form>

  <form method="post">
    <div class="card" style="height:100%">
      <h3 style="margin:0 0 .5rem;font-size:.95rem">&#9314; Test L3 — Mapping</h3>
      <p style="font-size:12px;color:#666;margin:0 0 1rem">
        Haiku produce il mapping completo dopo aver analizzato tutte le colonne.
        Verifica se <code>Radius→diametro_mm</code>, <code>Gauge→fuori_pinza_mm</code>, ecc.
        <br><b>Costo stimato: ~4500 + 1500 token</b>
      </p>
      <button class="btn btn-p" type="submit" name="azione" value="test_l3">
        &#9654; Esegui L3
      </button>
    </div>
  </form>

  <form method="post">
    <div class="card" style="border:2px solid #1d4ed8;height:100%">
      <h3 style="margin:0 0 .5rem;font-size:.95rem;color:#1d4ed8">
        &#9315; Test Completo L1→L4
      </h3>
      <p style="font-size:12px;color:#666;margin:0 0 1rem">
        L'orchestratore esegue tutti i livelli in sequenza e produce il profilo
        validato con score di confidenza. Se L4 rifiuta, L3 corregge e riprova.
        <br><b>Costo stimato: ~$0.003-0.008 USD totali</b>
      </p>
      <button class="btn" style="background:#1d4ed8;color:#fff" type="submit" name="azione" value="test_completo">
        &#9654; Esegui test completo
      </button>
    </div>
  </form>

</div>

<!-- Risultato -->
{% if errore %}
<div class="card" style="border-left:4px solid #991b1b">
  <h3 style="color:#991b1b;margin:0 0 .75rem">&#10060; Errore</h3>
  <pre style="font-size:11px;background:#fef2f2;padding:1rem;border-radius:6px;overflow-x:auto;white-space:pre-wrap">{{ errore }}</pre>
</div>
{% endif %}

{% if risultato %}
<div class="card" style="border-left:4px solid {% if risultato.get('verificato') %}#166534{% else %}#1d4ed8{% endif %}">
  <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1rem">
    <h3 style="margin:0">{{ risultato.livello }}</h3>
    {% if risultato.get('verificato') is not none %}
      {% if risultato.verificato %}
        <span style="background:#dcfce7;color:#166534;padding:3px 10px;border-radius:10px;font-size:12px;font-weight:600">
          &#10003; APPROVATO — Score: {{ risultato.score }}%
        </span>
      {% else %}
        <span style="background:#fee2e2;color:#991b1b;padding:3px 10px;border-radius:10px;font-size:12px;font-weight:600">
          &#10060; NON APPROVATO — Score: {{ risultato.score }}%
        </span>
      {% endif %}
    {% endif %}
    {% if risultato.get('n_mappati') %}
      <span style="background:#dbeafe;color:#1d4ed8;padding:3px 10px;border-radius:10px;font-size:12px">
        {{ risultato.n_mappati }} campi mappati
      </span>
    {% endif %}
    {% if risultato.get('costo_token') %}
      <span style="background:#f0fdf4;color:#166534;padding:3px 10px;border-radius:10px;font-size:12px">
        ~{{ risultato.costo_token }} token
      </span>
    {% endif %}
  </div>

  {% if risultato.get('log') %}
  <details style="margin-bottom:1rem">
    <summary style="cursor:pointer;font-weight:600;font-size:13px;color:#555">
      &#128196; Log esecuzione ({{ risultato.log|length }} eventi)
    </summary>
    <div style="background:#1a1a1a;border-radius:6px;padding:.75rem;margin-top:.5rem;max-height:300px;overflow-y:auto">
      {% for e in risultato.log %}
      <div style="font-family:monospace;font-size:11px;margin:.2rem 0;
           color:{% if e.livello=='L1' %}#60a5fa{% elif e.livello in ('L2a','L2b') %}#4ade80{% elif e.livello=='L3' %}#fbbf24{% else %}#c084fc{% endif %}">
        [{{ e.livello }}] {{ e.msg }}
      </div>
      {% endfor %}
    </div>
  </details>
  {% endif %}

  {% if risultato.get('profilo') %}
  <h4 style="margin:.5rem 0;font-size:.9rem">Mapping prodotto:</h4>
  <table style="font-size:12px;width:100%">
  <thead><tr>
    <th>Colonna file</th><th>Campo master</th>
    <th style="text-align:center">Confidenza</th>
    <th>Trasformazione</th><th>Motivazione</th>
  </tr></thead>
  <tbody>
  {% for col, info in risultato.profilo.items() %}
  <tr>
    <td style="font-family:monospace">{{ col }}</td>
    <td><b>{{ info.campo_master }}</b></td>
    <td style="text-align:center">
      <span style="background:{% if info.confidenza=='alta' %}#dcfce7;color:#166534{% elif info.confidenza=='media' %}#fef9c3;color:#854d0e{% else %}#fee2e2;color:#991b1b{% endif %};padding:1px 8px;border-radius:8px;font-size:11px">
        {{ info.confidenza }}
      </span>
    </td>
    <td style="color:#7c3aed;font-size:11px">{{ info.get('trasformazione','nessuna') }}</td>
    <td style="color:#666;font-size:11px">{{ info.get('motivazione','')[:80] }}</td>
  </tr>
  {% endfor %}
  </tbody></table>
  {% endif %}

  {% if risultato.get('campi_mancanti') %}
  <div style="margin-top:.75rem;background:#fef9c3;border-radius:6px;padding:.75rem">
    <b style="font-size:12px;color:#854d0e">&#9888; Campi critici non coperti:</b>
    <span style="font-size:12px;color:#854d0e"> {{ risultato.campi_mancanti|join(', ') }}</span>
  </div>
  {% endif %}

  {% if risultato.get('output') and not risultato.get('profilo') %}
  <pre style="font-size:11px;background:#f8f8f6;padding:1rem;border-radius:6px;overflow-x:auto;white-space:pre-wrap">{{ risultato.output | tojson(indent=2) }}</pre>
  {% endif %}
</div>
{% endif %}
""")


@app.route('/debug_magic')
def debug_magic():
    import glob, tempfile
    tmp = tempfile.gettempdir()
    files = sorted(glob.glob(f'{tmp}/tmp*/Cimatron_2025.csv'), key=os.path.getmtime)
    results = []
    for f in files[-3:]:
        try:
            with open(f, 'rb') as fh:
                raw = fh.read(20)
            results.append(f"{os.path.basename(os.path.dirname(f))}: {raw.hex()} | size={os.path.getsize(f)}")
        except Exception as e:
            results.append(f"ERR: {e}")
    return '<br>'.join(results) or 'nessun file trovato'


@app.route('/version')
def version():
    import importlib, importers.import_from_excel as ief
    importlib.reload(ief)  # forza reload del modulo
    src = open(ief.__file__).read()
    has_magic = "magic in (b" in src or "b'\\xff\\xfe'" in src or 'xff' in src
    return f"import_from_excel: {'NUOVO (magic bytes)' if has_magic else 'VECCHIO'}<br>path: {ief.__file__}"


# ---------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__),'..','logs'), exist_ok=True)
    print('')
    print('  Tool DB Manager  ->  http://localhost:5000')
    print('  Format Learner   ->  python learner/app_learner.py  (porta 5001)')
    print('')
    app.run(debug=True, port=5000, use_reloader=True)
