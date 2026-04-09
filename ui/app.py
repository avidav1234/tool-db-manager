"""
app.py - Interfaccia web locale (Flask)
Avvia con: python ui/app.py
Apri nel browser: http://localhost:5000
"""

import sqlite3
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file
from exporters.export_cimatron import export_cutters as export_cimatron

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')

app = Flask(__name__)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')
    conn = get_conn()
    with open(schema_path, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


HTML_BASE = """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tool DB Manager</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 1rem; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
  th { background: #f4f4f4; font-weight: 600; }
  tr:hover { background: #fafafa; }
  .btn { padding: 6px 14px; border-radius: 4px; border: 1px solid #ccc;
         cursor: pointer; text-decoration: none; display: inline-block; }
  .btn-primary { background: #0066cc; color: white; border-color: #0066cc; }
  .btn-success { background: #28a745; color: white; border-color: #28a745; }
  .btn-danger  { background: #dc3545; color: white; border-color: #dc3545; }
  .flash { padding: 10px; margin: 10px 0; border-radius: 4px; background: #d4edda; color: #155724; }
  nav a { margin-right: 1rem; font-weight: 500; }
  h1 { margin-bottom: 0.3rem; }
  .subtitle { color: #666; margin-bottom: 1.5rem; }
</style>
</head>
<body>
<nav>
  <a href="/">Utensili</a>
  <a href="/export">Export CAM</a>
  <a href="/log">Log</a>
</nav>
<hr>
{% block content %}{% endblock %}
</body>
</html>
"""

HOME_HTML = HTML_BASE.replace('{% block content %}{% endblock %}', """
<h1>Tool DB Manager</h1>
<p class="subtitle">Database utensili centralizzato | Cimatron · hyperMILL · WorkNC</p>

{% if msg %}<div class="flash">{{ msg }}</div>{% endif %}

<div style="margin-bottom:1rem">
  <a class="btn btn-primary" href="/utensile/nuovo">+ Nuovo utensile</a>
</div>

<table>
<thead><tr>
  <th>Codice</th><th>Descrizione</th><th>Tipo</th>
  <th>Diam. (mm)</th><th>R. punta</th><th>L. tot.</th>
  <th>Taglienti</th><th>Materiale</th><th>Azioni</th>
</tr></thead>
<tbody>
{% for u in utensili %}
<tr>
  <td><b>{{ u.codice_interno }}</b></td>
  <td>{{ u.descrizione }}</td>
  <td>{{ u.tipo }}</td>
  <td>{{ u.diametro_mm }}</td>
  <td>{{ u.raggio_punta_mm }}</td>
  <td>{{ u.lunghezza_totale_mm }}</td>
  <td>{{ u.num_taglienti }}</td>
  <td>{{ u.materiale }}</td>
  <td>
    <a class="btn" href="/utensile/{{ u.id }}/modifica">Modifica</a>
    <a class="btn btn-danger" href="/utensile/{{ u.id }}/elimina"
       onclick="return confirm('Eliminare?')">X</a>
  </td>
</tr>
{% else %}
<tr><td colspan="9" style="text-align:center;color:#999">
  Nessun utensile. <a href="/utensile/nuovo">Aggiungi il primo.</a>
</td></tr>
{% endfor %}
</tbody>
</table>
""")

EXPORT_HTML = HTML_BASE.replace('{% block content %}{% endblock %}', """
<h1>Export CAM</h1>
<p class="subtitle">Genera i file di import per i tre sistemi CAM</p>

{% if msg %}<div class="flash">{{ msg }}</div>{% endif %}

<table>
<thead><tr><th>Sistema CAM</th><th>Stato</th><th>Azione</th></tr></thead>
<tbody>
<tr>
  <td><b>Cimatron</b></td>
  <td>Pronto</td>
  <td><form method="post" action="/export/cimatron" style="display:inline">
    <button class="btn btn-success" type="submit">Genera CSV Cimatron</button>
  </form></td>
</tr>
<tr>
  <td><b>hyperMILL</b></td>
  <td style="color:#999">In attesa info versione</td>
  <td><button class="btn" disabled>Non disponibile</button></td>
</tr>
<tr>
  <td><b>WorkNC</b></td>
  <td style="color:#999">In attesa info versione</td>
  <td><button class="btn" disabled>Non disponibile</button></td>
</tr>
</tbody>
</table>
""")


@app.route('/')
def home():
    conn = get_conn()
    utensili = conn.execute("SELECT * FROM utensile_completo WHERE attivo=1 ORDER BY codice_interno").fetchall()
    conn.close()
    msg = request.args.get('msg', '')
    return render_template_string(HOME_HTML, utensili=utensili, msg=msg)


@app.route('/export', methods=['GET'])
def export_page():
    msg = request.args.get('msg', '')
    return render_template_string(EXPORT_HTML, msg=msg)


@app.route('/export/cimatron', methods=['POST'])
def do_export_cimatron():
    try:
        path = export_cimatron()
        return send_file(path, as_attachment=True)
    except Exception as e:
        return redirect(url_for('export_page', msg=f'Errore: {e}'))


@app.route('/log')
def log_page():
    conn = get_conn()
    logs = conn.execute("SELECT * FROM log_export ORDER BY timestamp DESC LIMIT 50").fetchall()
    conn.close()
    log_html = HTML_BASE.replace('{% block content %}{% endblock %}', """
<h1>Log export</h1>
<table>
<thead><tr><th>Data</th><th>CAM</th><th>Utensili</th><th>File</th></tr></thead>
<tbody>
{% for l in logs %}
<tr><td>{{ l.timestamp }}</td><td>{{ l.cam }}</td>
    <td>{{ l.num_utensili }}</td><td>{{ l.file_output }}</td></tr>
{% else %}
<tr><td colspan="4" style="text-align:center;color:#999">Nessun export ancora effettuato.</td></tr>
{% endfor %}
</tbody>
</table>
""")
    return render_template_string(log_html, logs=logs)


if __name__ == '__main__':
    init_db()
    print('Tool DB Manager avviato su http://localhost:5000')
    app.run(debug=True, port=5000)
