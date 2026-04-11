"""
app_learner.py - Interfaccia web standalone del modulo Format Learner
Porta: 5001  |  Avvia con: python learner/app_learner.py
Apri: http://localhost:5001
"""

import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template_string, request, redirect, url_for, send_file
from format_learner import analizza_file, MASTER_FIELDS
from profile_manager import salva_profilo, carica_profilo, lista_profili, elimina_profilo
from universal_converter import converti

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
UPLOAD_FOLDER = tempfile.mkdtemp()

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
      <input type="file" id="fi" name="file" accept=".csv,.xls,.xlsx,.zip"
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
    I suggerimenti sono evidenziati in blu — verificali e correggi se necessario.
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
      {% for k,v in fields.items() %}<option value="{{ k }}" {% if k==campo %}selected{% endif %}>{{ k }} — {{ v.label }}</option>{% endfor %}
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
      {% for k,v in fields.items() %}<option value="{{ k }}">{{ k }} — {{ v.label }}</option>{% endfor %}
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
         <input type="file" name="file" accept=".csv,.xls,.xlsx,.zip" required></div>
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

@app.route('/analizza', methods=['POST'])
def analizza():
    f = request.files.get('file')
    if not f or f.filename == '':
        return redirect(url_for('home', msg='Nessun file selezionato'))
    fp = os.path.join(UPLOAD_FOLDER, f.filename)
    f.save(fp)
    try:
        # Tenta orchestratore multilivello
        _root = os.path.join(os.path.dirname(__file__), '..')
        if _root not in sys.path: sys.path.insert(0, _root)

        usa_orche = False
        try:
            from orchestrator_agent import disponibile, orchestra_learning
            usa_orche = disponibile()
        except Exception:
            usa_orche = False

        if usa_orche:
            # PERCORSO 1: Orchestratore L1->L4 (autorevole)
            import pandas as pd
            ext = os.path.splitext(fp)[1].lower()
            df_tmp = None
            if ext == '.csv':
                # Rileva separatore
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

            if df_tmp is not None and len(df_tmp) > 0:
                log_ev = []
                res = orchestra_learning(
                    df_tmp, nome_file=f.filename,
                    log_callback=lambda lv, msg: log_ev.append({'livello': lv, 'msg': msg})
                )
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
                        'confidenza':     info.get('confidenza', 'media'),
                        'motivazione':    info.get('motivazione', ''),
                        'trasformazione': info.get('trasformazione', 'nessuna'),
                        'da_agente':      True,
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

if __name__ == '__main__':
    app.jinja_env.filters['basename'] = os.path.basename
    print('Format Learner -> http://localhost:5001')
    app.run(debug=True, port=5001)
