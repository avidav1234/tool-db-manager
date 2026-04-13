"""
app_learner.py - Interfaccia web standalone del modulo Format Learner
Porta: 5001  |  Avvia con: python learner/app_learner.py
Apri: http://localhost:5001
"""

import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template_string, request, redirect, url_for, send_file, session
from format_learner import analizza_file, MASTER_FIELDS
from profile_manager import salva_profilo, carica_profilo, lista_profili, elimina_profilo
from universal_converter import converti

app = Flask(__name__)
app.secret_key = 'tooldb-learner-2025'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# Preload moduli al boot per abilitare hot-reload
def _preload_moduli():
    import sys, os
    _ld = os.path.dirname(os.path.abspath(__file__))
    if _ld not in sys.path: sys.path.insert(0, _ld)
    for _m in ['cimatron_parser', 'orchestrator_agent', 'mapping_agent']:
        try:
            if _m not in sys.modules:
                __import__(_m)
        except Exception:
            pass

_preload_moduli()
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads_learner')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

BASE = """<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Format Learner</title>
<style>
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;margin:0;background:#f8f8f6;color:#1a1a1a}
.hdr{background:#1a1a1a;color:#fff;padding:.8rem 2rem;display:flex;align-items:center;gap:2rem}
.hdr h1{margin:0;font-size:1rem;font-weight:500}
.hdr a{color:#bbb;text-decoration:none;font-size:.9rem}.hdr a:hover{color:#fff}
.main{max-width:1100px;margin:2rem auto;padding:0 1rem}
.card{background:#fff;border:1px solid #e0e0de;border-radius:8px;padding:1.5rem;margin-bottom:1.5rem}
.card h2{margin:0 0 1rem;font-size:1rem;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border:1px solid #e0e0de;padding:7px 10px;text-align:left}
th{background:#f4f4f2;font-weight:600}
.btn{display:inline-block;padding:7px 16px;border-radius:5px;border:1px solid #ccc;
     cursor:pointer;font-size:13px;text-decoration:none;background:#fff;color:#333}
.btn-p{background:#0055cc;color:#fff;border-color:#0055cc}
.btn-s{background:#1a7a3c;color:#fff;border-color:#1a7a3c}
.btn-d{background:#c0392b;color:#fff;border-color:#c0392b}
.flash{padding:10px;border-radius:5px;margin-bottom:1rem;background:#d4edda;color:#155724}
.flash.err{background:#f8d7da;color:#721c24}
.badge{display:inline-block;font-size:11px;padding:2px 7px;border-radius:10px;font-weight:500}
.b-a{background:#d4edda;color:#155724}.b-m{background:#fff3cd;color:#856404}
.b-b{background:#f8d7da;color:#721c24}.b-n{background:#e9ecef;color:#6c757d}
select,input[type=text],input[type=file]{padding:6px 10px;border:1px solid #ccc;
  border-radius:4px;font-size:13px;width:100%}
.up{border:2px dashed #ccc;border-radius:8px;padding:2rem;text-align:center;
    color:#888;cursor:pointer}.up:hover{border-color:#0055cc;color:#0055cc}
.steps{display:flex;gap:0;margin-bottom:1.5rem}
.step{flex:1;padding:8px;text-align:center;font-size:12px;background:#e9ecef;color:#666}
.step.on{background:#0055cc;color:#fff;font-weight:600}
.step.ok{background:#1a7a3c;color:#fff}
</style></head><body>
<div class="hdr"><h1>Format Learner</h1>
<a href="/">Impara</a><a href="/profili">Profili</a><a href="/converti">Converti</a></div>
<div class="main">
{% if msg %}<div class="flash {{ mtype }}">{{ msg }}</div>{% endif %}
{% block content %}{% endblock %}
</div></body></html>"""

HOME = BASE.replace('{% block content %}{% endblock %}', """
<div class="steps">
  <div class="step on">1. Carica file</div>
  <div class="step">2. Verifica mappatura</div>
  <div class="step">3. Salva profilo</div>
</div>
<div class="card">
  <h2>Carica un file esportato da qualsiasi CAM</h2>
  <p style="color:#666;font-size:13px;margin-bottom:1rem">
    Formati: <b>CSV</b>, <b>XLS/XLSX</b>, <b>ZIP</b> (es. Cimatron)<br>
    Il sistema analizza la struttura e propone la mappatura automaticamente.
  </p>
  <form method="post" action="/analizza" enctype="multipart/form-data">
    <label class="up" for="fi">
      <div style="font-size:2rem">&#8679;</div>
      <div>Trascina qui il file o clicca per sceglierlo</div>
      <input type="file" id="fi" name="file" accept=".csv,.xls,.xlsx,.zip,.db,.tooldb,.tools,.json,.wkz,.js,.hlx,.hld,.tsv,.txt"
             style="display:none" onchange="document.querySelector('.up div+div').textContent=this.files[0].name">
    </label>
    <div style="margin-top:1rem">
      <button class="btn btn-p" type="submit">Analizza file</button>
    </div>
  </form>
</div>
{% if profili %}
<div class="card">
  <h2>Profili disponibili ({{ profili|length }})</h2>
  <table><thead><tr><th>Nome</th><th>Software</th><th>Versione</th><th>Colonne</th></tr></thead>
  <tbody>{% for p in profili %}
  <tr><td><b>{{ p.nome }}</b></td><td>{{ p.software }}</td>
      <td>{{ p.versione }}</td><td>{{ p.num_colonne }}</td></tr>
  {% endfor %}</tbody></table>
</div>{% endif %}
""")

ANALISI = BASE.replace('{% block content %}{% endblock %}', """
<div class="steps">
  <div class="step ok">1. Carica file</div>
  <div class="step on">2. Verifica mappatura</div>
  <div class="step">3. Salva profilo</div>
</div>
<div class="card">
  <h2>{{ r.num_righe }} utensili | {{ r.num_colonne }} colonne</h2>
  <form method="post" action="/salva_profilo">
  <input type="hidden" name="filepath" value="{{ r.filepath }}">
  {% if r.agente_usato %}
  <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:.6rem 1rem;margin-bottom:1rem;font-size:13px;color:#1d4ed8">
    L'agente AI ha suggerito mapping per le colonne non identificate automaticamente.
    I suggerimenti sono evidenziati in blu Ã¢ÂÂ verificali e correggi se necessario.
  </div>
  {% endif %}
  {% if r.agente_errore %}
  <div style="background:#fef9c3;border-radius:6px;padding:.6rem 1rem;margin-bottom:1rem;font-size:12px;color:#854d0e">
    Agente non disponibile ({{ r.agente_errore }}). Mappa manualmente le colonne rimanenti.
  </div>
  {% endif %}
  {% if r.orchestratore %}
  <div style="background:{% if r.orchestratore.verificato %}#f0fdf4{% else %}#fefce8{% endif %};border:1px solid {% if r.orchestratore.verificato %}#86efac{% else %}#fde047{% endif %};border-radius:8px;padding:.75rem;margin-bottom:1rem;display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
    <span style="font-weight:600;font-size:13px">&#129516; Agente Multilivello:</span>
    {% if r.orchestratore.verificato %}
    <span style="background:#dcfce7;color:#166534;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600">&#10003; APPROVATO {{r.orchestratore.score}}%</span>
    {% else %}
    <span style="background:#fef9c3;color:#854d0e;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600">&#9888; PARZIALE {{r.orchestratore.score}}%</span>
    {% endif %}
    <span style="font-size:12px;color:#888">~{{r.orchestratore.costo}} token | {{r.orchestratore.struttura.get('software_cam','?')}}</span>
    {% if r.orchestratore.campi_mancanti %}
    <span style="font-size:12px;color:#854d0e">&#9888; Mancanti: {{r.orchestratore.campi_mancanti|join(', ')}}</span>
    {% endif %}
    <details style="width:100%">
      <summary style="cursor:pointer;font-size:11px;color:#888">Log</summary>
      <div style="background:#1a1a1a;border-radius:4px;padding:.4rem;margin-top:.3rem;max-height:150px;overflow-y:auto">
      {% for e in r.orchestratore.log %}
      <div style="font-family:monospace;font-size:10px;color:{% if e.livello=='L1' %}#60a5fa{% elif 'L2' in e.livello %}#4ade80{% elif e.livello=='L3' %}#fbbf24{% else %}#c084fc{% endif %}">[{{e.livello}}] {{e.msg}}</div>
      {% endfor %}
      </div>
    </details>
  </div>
  {% endif %}

  <table style="margin-bottom:1rem">
  <thead><tr><th>Colonna file</th><th>Campo master</th><th>Confidenza</th><th>Note</th></tr></thead>
  <tbody>
  {% for campo, info in r.mapping.items() %}
  <tr {% if info.get('da_agente') %}style="background:#eff6ff"{% endif %}>
    <td>
      <code>{{ info.colonna_file }}</code>
      {% if info.get('da_agente') %}
      <span style="background:#1d4ed8;color:#fff;font-size:10px;padding:1px 5px;border-radius:8px;margin-left:4px">AI</span>
      {% endif %}
    </td>
    <td><select name="map_{{ info.colonna_file }}">
      <option value="">-- ignora --</option>
      {% for k,v in fields.items() %}<option value="{{ k }}" {% if k==campo %}selected{% endif %}>{{ k }} Ã¢ÂÂ {{ v.label }}</option>{% endfor %}
    </select></td>
    <td><span class="badge b-{{ info.confidenza[0] }}">{{ info.confidenza }}</span></td>
    <td style="font-size:11px;color:#888">{{ info.get('motivazione','') }}</td>
  </tr>
  {% endfor %}
  {% for col in r.colonne_non_mappate %}
  <tr style="background:#fafaf0">
    <td><code>{{ col }}</code></td>
    <td><select name="map_{{ col }}">
      <option value="">-- ignora --</option>
      {% for k,v in fields.items() %}<option value="{{ k }}">{{ k }} Ã¢ÂÂ {{ v.label }}</option>{% endfor %}
    </select></td>
    <td><span class="badge b-n">non rilevata</span></td>
    <td></td>
  </tr>
  {% endfor %}
  </tbody></table>
  {% if r.valori_categoria %}
  <h3 style="font-size:.9rem;margin-top:1.5rem">Valori categorici</h3>
  {% for campo, valori in r.valori_categoria.items() %}
  <p style="font-size:13px;font-weight:600">{{ campo }}</p>
  <table style="width:auto;margin-bottom:1rem">
  <thead><tr><th>Nel file</th><th>Nel master</th></tr></thead>
  <tbody>{% for vf, vm in valori.items() %}
  <tr><td><code>{{ vf }}</code></td>
      <td><input type="text" name="cat_{{ campo }}_{{ vf }}" value="{{ vm }}" style="width:120px"></td></tr>
  {% endfor %}</tbody></table>
  {% endfor %}{% endif %}
  <hr style="margin:1.5rem 0">
  <h3 style="font-size:.9rem">Salva come profilo</h3>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;margin-bottom:1rem">
    <div><label style="font-size:12px">Nome *</label>
         <input type="text" name="nome" placeholder="es. hypermill_2024" required></div>
    <div><label style="font-size:12px">Software</label>
         <input type="text" name="software" placeholder="es. hypermill"></div>
    <div><label style="font-size:12px">Versione</label>
         <input type="text" name="versione" placeholder="es. 2024.1"></div>
  </div>
  <div style="margin-bottom:1rem"><label style="font-size:12px">Note</label>
    <input type="text" name="note" placeholder="opzionale"></div>
  <div style="display:flex;gap:1rem">
    <button class="btn btn-s" type="submit">Salva profilo</button>
    <a class="btn" href="/">Annulla</a>
  </div>
  </form>
</div>

<div class="card" style="border-color:#86efac;background:#f0fdf4">
  <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
    <div>
      <h2 style="margin:0;color:#166534">&#8679; Importa nel DB master</h2>
      <p style="margin:.25rem 0 0;font-size:.8rem;color:#555">
        Inserisce gli utensili direttamente in Tool DB Manager
        &mdash; usa il parser deterministico Cimatron (35 campi, 0 token AI)
      </p>
    </div>
    <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap">
      <label style="font-size:.8rem;color:#555;display:flex;align-items:center;gap:.3rem">
        <input type="checkbox" id="lrn_dry_run"> Simulazione
      </label>
      <button onclick="lrnImportaDB()"
              style="padding:.5rem 1.25rem;background:#166534;color:#fff;border:none;
                     border-radius:6px;cursor:pointer;font-size:.875rem;font-weight:500">
        &#8679; Importa nel DB master
      </button>
    </div>
  </div>
  <div id="lrn_status" style="margin-top:.75rem;font-size:.85rem;display:none;
       padding:.5rem .75rem;border-radius:6px"></div>
</div>

<script>
function lrnImportaDB() {
  const fp  = {{ r.filepath | tojson }};
  const dry = document.getElementById('lrn_dry_run').checked;
  const box = document.getElementById('lrn_status');
  box.style.display = 'block';
  box.style.background = '#fef9c3';
  box.style.color = '#713f12';
  box.textContent = 'Importazione in corso...';
  fetch('http://localhost:5000/api/importa-db', {
    method : 'POST',
    headers: {'Content-Type':'application/json'},
    body   : JSON.stringify({filepath: fp, dry_run: dry})
  })
  .then(r => r.json())
  .then(d => {
    if (d.errore) {
      box.style.background = '#fee2e2';
      box.style.color = '#991b1b';
      box.textContent = 'Errore: ' + d.errore;
    } else {
      box.style.background = dry ? '#fef9c3' : '#dcfce7';
      box.style.color = dry ? '#713f12' : '#166534';
      let msg = (dry ? 'SIMULAZIONE Ã¢ÂÂ ' : '') +
        d.inseriti + ' inseriti, ' +
        d.aggiornati + ' aggiornati';
      if (d.taglio_inserite) msg += ', ' + d.taglio_inserite + ' condizioni taglio';
      if (d.versione) msg += ' (v' + d.versione + ')';
      if (d.errori && d.errori.length) msg += ' Ã¢ÂÂ ' + d.errori.length + ' errori';
      if (!dry) msg += ' Ã¢ÂÂ <a href="http://localhost:5000" target="_blank" style="color:#166534">Apri DB master Ã¢ÂÂ</a>';
      box.innerHTML = msg;
    }
  })
  .catch(e => {
    box.style.background = '#fee2e2';
    box.style.color = '#991b1b';
    box.textContent = 'Connessione fallita: ' + e.message + ' (app.py in esecuzione su porta 5000?)';
  });
}
</script>

<div class="card"><h2>Anteprima</h2>
<div style="overflow-x:auto"><table>
<thead><tr>{% for c in r.colonne_originali %}<th>{{ c }}</th>{% endfor %}</tr></thead>
<tbody>{% for row in r.anteprima %}
<tr>{% for c in r.colonne_originali %}<td>{{ row.get(c,'') }}</td>{% endfor %}</tr>
{% endfor %}</tbody></table></div></div>
""")

PROFILI_P = BASE.replace('{% block content %}{% endblock %}', """
<div style="display:flex;justify-content:space-between;margin-bottom:1rem">
  <h2 style="margin:0">Profili salvati</h2>
  <a class="btn btn-p" href="/">+ Nuovo</a>
</div>
<div class="card">
{% if profili %}
<table><thead><tr><th>Nome</th><th>Software</th><th>Versione</th><th>Colonne</th><th>Data</th><th></th></tr></thead>
<tbody>{% for p in profili %}
<tr><td><b>{{ p.nome }}</b></td><td>{{ p.software }}</td><td>{{ p.versione }}</td>
    <td>{{ p.num_colonne }}</td><td style="color:#999;font-size:12px">{{ p.creato_il[:10] }}</td>
    <td>
      <a class="btn" href="/profilo/{{ p.file[:-5] }}/scarica">Scarica</a>
      <a class="btn btn-d" href="/profilo/{{ p.file[:-5] }}/elimina"
         onclick="return confirm('Eliminare?')">X</a>
    </td></tr>
{% endfor %}</tbody></table>
{% else %}<p style="color:#999;text-align:center;padding:2rem">
  Nessun profilo. <a href="/">Carica un file per iniziare.</a></p>{% endif %}
</div>
""")

CONVERTI_P = BASE.replace('{% block content %}{% endblock %}', """
<div class="card">
  <h2>Converti file tra formati CAM</h2>
  <form method="post" action="/converti" enctype="multipart/form-data">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:1.5rem">
    <div><label style="font-size:12px;font-weight:600">File sorgente</label>
         <input type="file" name="file" accept=".csv,.xls,.xlsx,.zip,.db,.tooldb,.tools,.json,.wkz,.js,.hlx,.hld,.tsv,.txt" required></div>
    <div></div>
    <div><label style="font-size:12px;font-weight:600">Profilo DA (sorgente)</label>
         <select name="profilo_input" required>
           <option value="">-- seleziona --</option>
           {% for p in profili %}<option value="{{ p.file[:-5] }}">{{ p.nome }} ({{ p.software }} {{ p.versione }})</option>{% endfor %}
         </select></div>
    <div><label style="font-size:12px;font-weight:600">Profilo A (destinazione)</label>
         <select name="profilo_output" required>
           <option value="">-- seleziona --</option>
           {% for p in profili %}<option value="{{ p.file[:-5] }}">{{ p.nome }} ({{ p.software }} {{ p.versione }})</option>{% endfor %}
         </select></div>
  </div>
  {% if profili|length < 2 %}
  <div class="flash err">Servono almeno 2 profili. <a href="/">Aggiungi profili</a>.</div>
  {% endif %}
  <button class="btn btn-p" type="submit" {% if profili|length < 2 %}disabled{% endif %}>
    Converti e scarica</button>
  </form>
</div>
""")


@app.route('/')
def home():
    app.jinja_env.filters['basename'] = os.path.basename
    return render_template_string(HOME, profili=lista_profili(),
                                  msg=request.args.get('msg',''), mtype='')

HYPERMILL_PREVIEW = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>Anteprima Import Hypermill</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px}
h1{color:#6366f1;margin-bottom:4px}
.sub{color:#64748b;margin-bottom:24px}
.card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;margin-bottom:20px}
h2{color:#94a3b8;font-size:.95rem;text-transform:uppercase;letter-spacing:.05em;margin:0 0 16px}
table{width:100%;border-collapse:collapse;font-size:.875rem}
th{background:#0f172a;color:#64748b;padding:8px 12px;text-align:left;font-weight:600}
td{padding:8px 12px;border-bottom:1px solid #334155}
tr:hover td{background:#263344}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600}
.tag-ok{background:#0d2d1a;color:#86efac}
.tag-warn{background:#2d1a0d;color:#fb923c}
.btn{display:inline-block;padding:12px 28px;border-radius:8px;font-weight:600;cursor:pointer;border:none;font-size:1rem;text-decoration:none}
.btn-ok{background:#6366f1;color:#fff;margin-right:12px}
.btn-cancel{background:#334155;color:#94a3b8}
.stat{font-size:2.5rem;font-weight:700;color:#6366f1}
</style>
</head>
<body>
<h1>Anteprima Import Hypermill</h1>
<p class="sub">Verifica il mapping prima di importare nel DB master</p>

<div class="card">
<h2>Riepilogo</h2>
<p><span class="stat">{{ totale }}</span> utensili trovati nel database Hypermill</p>
</div>

<div class="card">
<h2>Mapping Hypermill &rarr; DB Master</h2>
<table>
<thead><tr><th>Sorgente Hypermill</th><th>Campo DB Master</th><th>Esempio</th><th>Stato</th></tr></thead>
<tbody>
{% set rows = [
  ('nc_number_str','codice_interno','Nome officina (codice)'),
  ('nc_name','alias','Codice NC macchina'),
  ('holder_name','nome_pinza','Nome portautensile'),
  ('polyline','lungh_presa_mm','Lunghezza corpo holder mm'),
  ('tool_length+reach','fuori_pinza_mm','Fuori pinza mm'),
  ('ext_reach','lungh_libera_prolunga_mm','Reach prolunga mm'),
  ('tipo_attacco','tipo_attacco','Tipo attacco HSK/ISO'),
  ('tech.p2','fz_default','Fz mm/dente'),
  ('tech.p5','passo_lat_default','Ae mm'),
  ('tech.p6','passo_z_default','Ap mm'),
  ('tech.p10','vc_default','Vc m/min'),
  ('tool_name','descrizione','Nome utensile completo'),
  ('ordering_code','codice_catalogo','Codice catalogo'),
  ('tool_type_id','tipo','BALL/BULL/FLAT/DRILL'),
  ('dbl_param4','diametro_mm','Diametro mm'),
  ('dbl_param10','raggio_punta_mm','Raggio angolo mm'),
  ('total_length','lunghezza_totale_mm','Lunghezza totale mm'),
  ('int_param1','num_taglienti','Numero denti'),
  ('holder_name','nome_pinza','Nome portautensile'),
  ('gage_length','fuori_pinza_mm','Fuori pinza mm'),
  ('feedrate','avanzamento_default','Feed Vf mm/min'),
  ('fz','fz_default','Fz mm/dente'),
  ('rpm','rotazione_default','RPM mandrino'),
  ('vc','vc_default','Vc m/min'),
] %}
{% for src,dst,desc in rows %}
{% set val = campione.get(dst,'') %}
<tr>
<td style="color:#94a3b8;font-family:monospace">{{ src }}</td>
<td style="color:#818cf8;font-weight:600">{{ dst }}</td>
<td style="color:#64748b">{{ val if val else desc }}</td>
<td><span class="tag {{ 'tag-ok' if val else 'tag-warn' }}">{{ 'OK' if val else 'vuoto' }}</span></td>
</tr>
{% endfor %}
</tbody>
</table>
</div>

<div class="card">
<h2>Anteprima primi utensili</h2>
<table>
<thead><tr><th>#</th><th>Codice</th><th>Alias NC</th><th>Tipo</th><th>D mm</th><th>CR</th><th>Fuori pinza</th><th>Holder</th><th>L holder</th><th>Feed</th><th>Fz</th><th>Vc</th></tr></thead>
<tbody>
{% for u in utensili %}
<tr>
<td style="color:#475569">{{ loop.index }}</td>
<td>{{ u.get('codice_interno','') }}</td>
<td style="color:#94a3b8">{{ u.get('alias','') }}</td>
<td><span class="tag tag-ok">{{ u.get('tipo','?') }}</span></td>
<td>{{ u.get('diametro_mm','') }}</td>
<td>{{ u.get('raggio_punta_mm','') }}</td>
<td>{{ u.get('fuori_pinza_mm','') }}</td>
<td style="color:#94a3b8;font-size:.8rem">{{ u.get('nome_pinza','')[:20] }}</td>
<td>{{ u.get('lungh_presa_mm','') }}</td>
<td>{{ u.get('avanzamento_default','') }}</td>
<td>{{ u.get('fz_default','') }}</td>
<td>{{ u.get('vc_default','') }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>

<form method="POST" action="/conferma_import_hypermill">
<input type="hidden" name="filepath" value="{{ filepath }}">
<button type="submit" class="btn btn-ok">&#10003; Importa {{ totale }} utensili nel DB Master</button>
<a href="/" class="btn btn-cancel">Annulla</a>
</form>
</body></html>
"""


@app.route('/analizza', methods=['POST'])

def analizza():
    f = request.files.get('file')
    if not f or f.filename == '':
        return redirect(url_for('home', msg='Nessun file selezionato'))
    fp = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(fp)

    # Gestione speciale: database Hypermill (.db) - import diretto nel DB master
    if f.filename.lower().endswith('.db'):
        try:
            import sys as _sys, os as _os
            _ld = _os.path.dirname(_os.path.abspath(__file__))
            if _ld not in _sys.path: _sys.path.insert(0, _ld)
            from hypermill_db_importer import importa_hypermill_db, _is_hypermill_db
            if not _is_hypermill_db(fp):
                return redirect(url_for('home', msg='File .db non riconosciuto come database Hypermill'))
            # Dry run: mostra anteprima mapping con dati reali
            result = importa_hypermill_db(fp, None, dry_run=True)
            n_utensili = result.get('utensili', 0)
            if isinstance(n_utensili, list):
                n_utensili = len(n_utensili)

            # Costruisci campione reale leggendo direttamente dal DB
            campione = {}
            utensili_preview = []
            try:
                import sqlite3 as _sq
                _hm = _sq.connect(fp)
                _hm.row_factory = _sq.Row
                # Campione per il mapping (primo utensile con dati)
                _row = _hm.execute("""
                    SELECT n.nc_name, n.nc_number_str, n.tool_length, n.gage_length,
                           t.tool_type_id, t.name as tool_name, t.total_length,
                           t.dbl_param4, t.dbl_param10, t.int_param1, t.ordering_code,
                           h.name as holder_name,
                           cp.feedrate, cp.fz, cp.rpm, cp.vc
                    FROM NCTools n
                    JOIN Tools t ON n.tool_id=t.id
                    LEFT JOIN Holders h ON n.holder_id=h.id
                    LEFT JOIN CuttingProfiles cp ON cp.nc_tool_id=n.id
                    WHERE t.dbl_param4 > 0 LIMIT 1
                """).fetchone()
                if _row:
                    _tipo_map = {1:'BALL',2:'FLAT',3:'BULL',4:'DRILL',5:'BALL',6:'FORM',9:'FORM',15:'THREAD',16:'REAM'}
                    campione = {
                        'codice_interno': _row['nc_number_str'] or _row['nc_name'] or '',
                        'alias': _row['nc_name'] or '',
                        'nome_pinza': _row['holder_name'] or '',
                        'descrizione': _row['tool_name'] or '',
                        'codice_catalogo': _row['ordering_code'] or '',
                        'tipo': _tipo_map.get(_row['tool_type_id'], '?'),
                        'diametro_mm': round(float(_row['dbl_param4']),3) if _row['dbl_param4'] else '',
                        'raggio_punta_mm': round(float(_row['dbl_param10']),3) if _row['dbl_param10'] else '',
                        'lunghezza_totale_mm': round(float(_row['total_length']),1) if _row['total_length'] else '',
                        'num_taglienti': _row['int_param1'] or '',
                        'fuori_pinza_mm': round(float(_row['tool_length']),1) if _row['tool_length'] else '',
                        'avanzamento_default': round(float(_row['feedrate']),1) if _row['feedrate'] else '',
                        'fz_default': round(float(_row['fz']),4) if _row['fz'] else '',
                        'vc_default': round(float(_row['vc']),1) if _row['vc'] else '',
                    }
                # Anteprima primi 8 utensili
                _rows = _hm.execute("""
                    SELECT n.nc_name, n.nc_number_str, n.tool_length, n.gage_length,
                           t.tool_type_id, t.dbl_param4, t.dbl_param10,
                           h.name as holder_name,
                           cp.feedrate, cp.fz, cp.vc
                    FROM NCTools n
                    JOIN Tools t ON n.tool_id=t.id
                    LEFT JOIN Holders h ON n.holder_id=h.id
                    LEFT JOIN CuttingProfiles cp ON cp.nc_tool_id=n.id
                    WHERE t.dbl_param4 > 0
                    ORDER BY t.tool_type_id, t.dbl_param4 LIMIT 8
                """).fetchall()
                for _r in _rows:
                    utensili_preview.append({
                        'codice_interno': _r['nc_number_str'] or _r['nc_name'] or '',
                        'alias': _r['nc_name'] or '',
                        'tipo': _tipo_map.get(_r['tool_type_id'], '?'),
                        'diametro_mm': round(float(_r['dbl_param4']),3) if _r['dbl_param4'] else '',
                        'raggio_punta_mm': round(float(_r['dbl_param10']),3) if _r['dbl_param10'] else '',
                        'fuori_pinza_mm': round(float(_r['tool_length']),1) if _r['tool_length'] else '',
                        'nome_pinza': _r['holder_name'] or '',
                        'avanzamento_default': round(float(_r['feedrate']),1) if _r['feedrate'] else '',
                        'fz_default': round(float(_r['fz']),4) if _r['fz'] else '',
                        'vc_default': round(float(_r['vc']),1) if _r['vc'] else '',
                        'lungh_presa_mm': round(float(_r['gage_length']),1) if _r['gage_length'] else '',
                    })
                _hm.close()
            except Exception:
                pass  # campione vuoto se errore â non blocca il flusso

            # Salva path in sessione per conferma successiva
            import json as _json
            session['hm_filepath'] = fp
            session['hm_count'] = n_utensili
            return render_template_string(HYPERMILL_PREVIEW,
                filepath=fp, utensili=utensili_preview,
                totale=n_utensili, campione=campione)
        except Exception as e:
            import traceback as _tb
            return redirect(url_for('home', msg=f'Errore DB Hypermill: {str(e)[:100]}'))

    try:
        # Tenta orchestratore multilivello
        _root = os.path.join(os.path.dirname(__file__), '..')
        if _root not in sys.path: sys.path.insert(0, _root)

        usa_orche = False
        _oa_module = None
        try:
            import sys as _sys, os as _os
            for _k in list(_sys.modules.keys()):
                if 'orchestrator' in _k:
                    del _sys.modules[_k]
            _ld = _os.path.dirname(_os.path.abspath(__file__))
            if _ld not in _sys.path: _sys.path.insert(0, _ld)
            import orchestrator_agent as _oa_module
            usa_orche = _oa_module.disponibile()
        except Exception:
            usa_orche = False

        log_ev = []  # inizializzato qui per essere disponibile in tutto il blocco
        if usa_orche:
            # PERCORSO 1: Orchestratore L1->L4 (autorevole)
            # SKIP per Cimatron: ha parser nativo dedicato, l'orchestratore spreca token
            is_cimatron = False
            try:
                with open(fp, 'rb') as fh:
                    magic = fh.read(2)
                if magic in (b'\xff\xfe', b'\xfe\xff'):
                    is_cimatron = True
                elif fp.lower().endswith('.zip'):
                    import zipfile as _zf
                    with _zf.ZipFile(fp) as z:
                        is_cimatron = any('Cutters' in n for n in z.namelist())
            except Exception:
                pass
            if is_cimatron:
                usa_orche = False  # Usa euristica nativa Cimatron

            import pandas as pd
            ext = os.path.splitext(fp)[1].lower()
            df_tmp = None
            if ext == '.csv':
                for sep in [',', ';', '\t', '|']:
                    try:
                        test = pd.read_csv(fp, sep=sep, nrows=3)
                        if len(test.columns) > 2:
                            df_tmp = pd.read_csv(fp, sep=sep)
                            break
                    except Exception:
                        pass
            elif ext in ('.xlsx', '.xls'):
                df_tmp = pd.read_excel(fp)
            elif ext == '.zip':
                # ZIP Cimatron: usa parser ufficiale cimatron_parser
                try:
                    import cimatron_parser as _cp_mod
                    _result = _cp_mod.leggi_cimatron_zip(fp)
                    df_tmp = _result.get('df')
                    # Logga i nomi colonne per debug
                    if df_tmp is not None:
                        print('[DBG] col_names[:10]=' + str(list(df_tmp.columns)[:10]), flush=True)
                except Exception as _ez:
                    print('[ERR] leggi_cimatron_zip: ' + str(_ez), flush=True)
                    # Fallback: parser manuale
                    import zipfile, io
                    try:
                        with zipfile.ZipFile(fp) as z:
                            cutters = next((n for n in z.namelist() if 'Cutters' in n and n.endswith('.csv')), None)
                            if cutters:
                                with z.open(cutters) as zf:
                                    content = zf.read().decode('utf-16')
                                lines = content.splitlines()
                                nome_riga = id_riga = -1
                                for i, line in enumerate(lines):
                                    s = line.strip().lstrip('"')
                                    if s.startswith('//') or s == '' or s.startswith('Cimatron'): continue
                                    if nome_riga == -1: nome_riga = i; continue
                                    if id_riga == -1: id_riga = i; break
                                if nome_riga >= 0 and id_riga >= 0:
                                    col_names = [c.strip() for c in lines[nome_riga].split('|')]
                                    dati = [l for l in lines[id_riga+1:] if l.strip() and not l.strip().startswith('//')]
                                    rows = []
                                    for line in dati:
                                        parts = line.split('|')
                                        rows.append({col_names[j]: parts[j].strip() if j < len(parts) else '' for j in range(len(col_names))})
                                    df_tmp = pd.DataFrame(rows)
                    except Exception:
                        pass
                except Exception:
                    pass

            if df_tmp is not None and len(df_tmp) > 0:
                log_ev = []  # reset per questa analisi
                res = _oa_module.orchestra_learning(
                    df_tmp, nome_file=f.filename,
                    log_callback=lambda lv, msg: log_ev.append({'livello': lv, 'msg': msg})
                )
                # Leggi il mapping dal formato dell'orchestrator v2
                # Struttura: res['mapping']['mapping'] = {col: {campo_master, confidenza}}
                _raw_map = res.get('mapping', {})
                if isinstance(_raw_map, dict):
                    profilo = _raw_map.get('mapping', _raw_map)
                else:
                    profilo = res.get('profilo', {})

                # Costruisce r nel formato che la template si aspetta
                mapping = {}
                for col_file, info in profilo.items():
                    campo = info.get('campo_master', 'ignora')
                    if campo == 'ignora':
                        continue
                    mapping[campo] = {
                        'colonna_file':   col_file,
                        'score':          9.0 if info.get('confidenza') == 'alta' else 6.0,
                        'tipo':           'string',
                        'label':          col_file,
                        'confidenza':     info.get('confidenza', 'alta'),
                        'motivazione':    info.get('motivazione', 'Cimatron deterministico'),
                        'trasformazione': info.get('trasformazione', 'nessuna'),
                        'da_agente':      False,
                    }

                # Colonne non mappate = quelle nel file che non hanno un campo master
                colonne_mappate = set(v['colonna_file'] for v in mapping.values())
                r = {
                    'filepath':            fp,
                    'num_righe':           len(df_tmp),
                    'num_colonne':         len(df_tmp.columns),
                    'colonne_originali':   list(df_tmp.columns),
                    'mapping':             mapping,
                    'valori_categoria':    {},
                    'colonne_non_mappate': [c for c in df_tmp.columns if c not in colonne_mappate],
                    'anteprima':           df_tmp.head(5).to_dict(orient='records'),
                    'software_rilevato':   res.get('struttura', {}).get('software_cam', 'sconosciuto'),
                    'versione_rilevata':   res.get('struttura', {}).get('versione', ''),
                    'parser_usato':        'orchestratore_ai',
                    'orchestratore': {
                        'verificato':      res.get('verificato', False),
                        'score':           res.get('score', 0),
                        'costo':           res.get('costo_stimato', 0),
                        'struttura':       res.get('struttura', {}),
                        'campi_mancanti':  res.get('campi_mancanti', []),
                        'warning':         res.get('warning', []),
                        'log':             log_ev,
                    },
                }
                app.jinja_env.filters['basename'] = os.path.basename
                return render_template_string(ANALISI, r=r, fields=MASTER_FIELDS, msg='', mtype='')

        # PERCORSO 2: Euristica (fallback se orchestratore non disponibile o file non leggibile)
        r = analizza_file(fp)
        r.pop('df', None)
        r['orchestratore'] = None

    except Exception as e:
        return redirect(url_for('home', msg=f'Errore: {e}'))
    app.jinja_env.filters['basename'] = os.path.basename
    return render_template_string(ANALISI, r=r, fields=MASTER_FIELDS, msg='', mtype='')
@app.route('/salva_profilo', methods=['POST'])
def salva_profilo_route():
    form = request.form
    fp   = form.get('filepath', '')
    nome = form.get('nome', '').strip()
    if not nome:
        return redirect(url_for('home', msg='Nome obbligatorio'))
    try:
        r = analizza_file(fp)
    except Exception as e:
        return redirect(url_for('home', msg=f'Errore rianalisi: {e}'))
    tutte = r['colonne_originali']
    mapping, valori_cat = {}, {}
    for col in tutte:
        campo = form.get(f'map_{col}', '').strip()
        if not campo:
            continue
        from format_learner import MASTER_FIELDS as MF
        tipo = MF.get(campo, {}).get('tipo', 'string')
        mapping[campo] = {'colonna_file': col, 'tipo': tipo, 'label': MF.get(campo, {}).get('label', campo)}
    for campo in ['tipo', 'materiale']:
        if campo in mapping:
            col = mapping[campo]['colonna_file']
            _df_raw = r.get('df'); df = _df_raw if _df_raw is not None else __import__('pandas').DataFrame()
            try:
                uniq = df[col].dropna().unique() if col in df.columns else []
            except Exception:
                uniq = []
            vals = {}
            for v in uniq:
                key = f'cat_{campo}_{v}'
                vals[str(v)] = form.get(key, str(v)).strip()
            if vals:
                valori_cat[campo] = vals
    sep = '|' if fp.endswith('.zip') else ','
    try:
        with open(fp, 'r', encoding='utf-8', errors='replace') as fh:
            raw = fh.read(2000)
        sep = '|' if raw.count('|') > raw.count(',') else ','
    except Exception:
        pass
    try:
        salva_profilo(nome, form.get('software',''), form.get('versione',''),
                      mapping, valori_cat, separatore=sep, note=form.get('note',''))
        return redirect(url_for('profili_page', msg=f'Profilo "{nome}" salvato'))
    except Exception as e:
        return redirect(url_for('home', msg=f'Errore salvataggio: {e}'))

@app.route('/profili')
def profili_page():
    return render_template_string(PROFILI_P, profili=lista_profili(),
                                  msg=request.args.get('msg',''), mtype='')

@app.route('/profilo/<nome>/scarica')
def scarica(nome):
    from profile_manager import _profile_path
    path = _profile_path(nome)
    return send_file(path, as_attachment=True) if os.path.exists(path) else redirect(url_for('profili_page'))

@app.route('/profilo/<nome>/elimina')
def elimina(nome):
    elimina_profilo(nome)
    return redirect(url_for('profili_page', msg=f'"{nome}" eliminato'))

@app.route('/api/version')
def api_version():
    """Mostra la versione dei moduli caricati (per debug)."""
    import importlib, sys
    info = {}
    for mod in ['orchestrator_agent','format_learner','cimatron_parser']:
        m = sys.modules.get(mod)
        info[mod] = 'loaded' if m else 'not loaded'
    return json.dumps({'status': 'ok', 'modules': info,
                       'python': sys.version.split()[0]}, ensure_ascii=False)

@app.route('/api/debug-import')
def api_debug_import():
    """Debug: elenca file in UPLOAD_FOLDER e mostra percorso."""
    import glob, os
    files = glob.glob(os.path.join(UPLOAD_FOLDER, '*'))
    return json.dumps({'upload_folder': UPLOAD_FOLDER, 'files': files})

@app.route('/api/reload', methods=['POST'])
def api_reload():
    """Ricarica i moduli principali senza riavviare il server."""
    import importlib, sys
    reloaded = []
    _preload_moduli()  # assicura che tutti i moduli siano caricati
    for mod in ['orchestrator_agent','format_learner','cimatron_parser',
                'mapping_agent','profile_manager']:
        if mod in sys.modules:
            try:
                importlib.reload(sys.modules[mod])
                reloaded.append(mod)
            except Exception as e:
                pass
    return json.dumps({'reloaded': reloaded}, ensure_ascii=False)

@app.route('/converti', methods=['GET','POST'])
def converti_page():
    profili = lista_profili()
    if request.method == 'POST':
        f    = request.files.get('file')
        p_in = request.form.get('profilo_input','')
        p_out= request.form.get('profilo_output','')
        if not f or not p_in or not p_out:
            return render_template_string(CONVERTI_P, profili=profili,
                                          msg='Tutti i campi obbligatori', mtype='err')
        in_p  = os.path.join(UPLOAD_FOLDER, f.filename)
        out_p = os.path.join(UPLOAD_FOLDER, f'converted_{p_out}.csv')
        f.save(in_p)
        try:
            converti(in_p, p_in, p_out, out_p)
            return send_file(out_p, as_attachment=True, download_name=f'converted_{p_out}.csv')
        except Exception as e:
            return render_template_string(CONVERTI_P, profili=profili,
                                          msg=f'Errore: {e}', mtype='err')
    return render_template_string(CONVERTI_P, profili=profili,
                                  msg=request.args.get('msg',''), mtype='')



# Ã¢ÂÂÃ¢ÂÂ Widget agente CAM (pannello flottante) Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

_WIDGET_MARKUP_L = (
    '<div id="ai-fab" onclick="aiT()" title="Agente CAM" '
    'style="position:fixed;bottom:24px;right:24px;width:52px;height:52px;'
    'background:#6366f1;color:#fff;border:none;border-radius:50%;cursor:pointer;'
    'font-size:1rem;font-weight:700;box-shadow:0 4px 20px rgba(99,102,241,.5);z-index:9998;'
    'display:flex;align-items:center;justify-content:center">AI</div>'
    '<div id="ai-panel" style="position:fixed;bottom:88px;right:24px;width:420px;height:560px;'
    'background:#1e293b;border:1px solid #334155;border-radius:16px;'
    'box-shadow:0 20px 60px rgba(0,0,0,.5);z-index:9999;display:none;flex-direction:column;overflow:hidden">'
    '<div style="background:#0f172a;padding:.75rem 1rem;display:flex;align-items:center;gap:.5rem;border-bottom:1px solid #334155">'
    '<span style="color:#fff;font-weight:600;font-size:.875rem;flex:1">Agente CAM</span>'
    '<small id="ai-pg" style="color:#475569;font-size:.7rem">Learner</small>'
    '<span onclick="aiT()" style="color:#64748b;cursor:pointer;font-size:1rem;padding:.2rem">X</span>'
    '</div>'
    '<div id="ai-ms" style="flex:1;overflow-y:auto;padding:.75rem;display:flex;flex-direction:column;gap:.5rem">'
    '<div style="background:#0d2d1a;color:#86efac;align-self:center;font-size:.7rem;padding:.2rem .6rem;border-radius:12px">'
    'Sono qui - scrivi o incolla un log.</div>'
    '</div>'
    '<div style="padding:.6rem;border-top:1px solid #334155;display:flex;flex-direction:column;gap:.4rem">'
    '<div style="display:flex;align-items:center;gap:.4rem">'
    '<label for="ai-fi" style="background:#0f172a;border:1px dashed #334155;border-radius:5px;'
    'padding:.3rem .6rem;cursor:pointer;font-size:.72rem;color:#64748b;white-space:nowrap">'
    'File CAM</label>'
    '<input type="file" id="ai-fi" style="display:none" accept=".zip,.csv,.xml,.tdm,.tdb,.db,.tooldb,.tools,.json,.wkz,.js,.hlx,.hld,.tsv,.txt,.xls,.xlsx">'
    '<span id="ai-fn" style="font-size:.7rem;color:#475569;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">nessun file</span>'
    '</div>'
    '<div style="display:flex;gap:.4rem">'
    '<textarea id="ai-in" rows="1" placeholder="Scrivi o incolla un log..." '
    'style="flex:1;background:#0f172a;border:1px solid #334155;border-radius:8px;'
    'padding:.5rem .7rem;color:#e2e8f0;font-size:.8rem;resize:none;min-height:34px;max-height:80px"></textarea>'
    '<button id="ai-sb" onclick="aiS()" '
    'style="background:#6366f1;color:#fff;border:none;border-radius:8px;'
    'padding:.5rem .9rem;cursor:pointer;font-size:.9rem;font-weight:600">></button>'
    '</div></div></div>'
    '<script src="http://localhost:5000/static/widget.js"><' '/script>'
)


@app.route('/static/widget.js')
def learner_widget_js():
    import os as _os
    from flask import redirect
    return redirect('http://localhost:5000/static/widget.js')


@app.after_request
def _inject_widget_learner(resp):
    if resp.content_type and 'text/html' in resp.content_type:
        html = resp.get_data(as_text=True)
        if '</body>' in html and 'ai-fab' not in html:
            resp.set_data(html.replace('</body>', _WIDGET_MARKUP_L + '</body>'))
    return resp




@app.route('/importa_db', methods=['POST'])
def importa_db():
    """Import diretto da DB Hypermill nel DB master."""
    import json as _json, sys as _sys, os as _os
    _ld = _os.path.dirname(_os.path.abspath(__file__))
    if _ld not in _sys.path: _sys.path.insert(0, _ld)

    filepath = request.form.get('filepath') or request.json.get('filepath','') if request.is_json else ''
    if not filepath:
        # Leggi da sessione
        try:
            analisi = _json.loads(session.get('analisi','{}'))
            filepath = analisi.get('filepath','')
        except Exception:
            filepath = ''

    if not filepath or not _os.path.exists(filepath):
        return _json.dumps({'errore': 'File non trovato'}), 400, {'Content-Type':'application/json'}

    try:
        from hypermill_db_importer import importa_hypermill_db
        # Trova il DB master
        _root = _os.path.join(_ld, '..')
        master_db = _os.path.join(_root, 'database', 'tool_master.db')
        result = importa_hypermill_db(filepath, master_db, dry_run=False)
        return _json.dumps({
            'ok': True,
            'importati': result.get('importati', 0),
            'errori': result.get('errori', 0),
            'totale': result.get('totale', 0),
        }, ensure_ascii=False), 200, {'Content-Type':'application/json'}
    except Exception as e:
        import traceback
        return _json.dumps({'errore': str(e), 'traceback': traceback.format_exc()[-300:]}), 500, {'Content-Type':'application/json'}


@app.route('/conferma_import_hypermill', methods=['POST'])
def conferma_import_hypermill():
    import os as _os, sys as _sys
    _ld = _os.path.dirname(_os.path.abspath(__file__))
    if _ld not in _sys.path: _sys.path.insert(0, _ld)
    filepath = request.form.get('filepath', '')
    if not filepath or not _os.path.exists(filepath):
        return redirect(url_for('home', msg='File non trovato'))
    try:
        from hypermill_db_importer import importa_hypermill_db
        _root = _os.path.join(_ld, '..')
        master_db = _os.path.join(_root, 'database', 'tool_master.db')
        result = importa_hypermill_db(filepath, master_db, dry_run=False)
        importati = result.get('utensili', result.get('importati', 0))
        errori = result.get('errori', 0)
        msg = f'Hypermill: {importati} utensili importati nel DB master'
        if errori: msg += f' ({errori} non importati)'
        return redirect(url_for('home', msg=msg))
    except Exception as e:
        return redirect(url_for('home', msg=f'Errore: {str(e)[:100]}'))

if __name__ == '__main__':
    app.jinja_env.filters['basename'] = os.path.basename
    print('Format Learner -> http://localhost:5001')
    app.run(debug=True, port=5001)
