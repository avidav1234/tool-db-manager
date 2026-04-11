"""
verifica_import.py
==================
Modulo di verifica qualita dati dopo un import.

Analizza il database master e produce:
  - Score di completezza per ogni utensile (0-100%)
  - Anomalie rilevate (valori fuori range, campi critici mancanti)
  - Report HTML scaricabile
  - Semaforo qualita (verde/giallo/rosso)

Un cammista alle prime armi puo capire immediatamente:
  - Quanti utensili sono stati importati
  - Quali dati mancano e quanto e grave
  - Cosa fare per completare i dati mancanti
"""

import os
import sys
import sqlite3
from datetime import datetime

# verifica_import.py puo essere nella root o in sottocartelle - cerca il DB in modo robusto
def _trova_db():
    """Cerca tool_master.db risalendo l'albero delle directory."""
    start = os.path.dirname(os.path.abspath(__file__))
    for base in [start, os.path.join(start, '..'), os.path.join(start, '..', '..')]:
        candidate = os.path.join(base, 'database', 'tool_master.db')
        if os.path.exists(candidate):
            return candidate
    # Fallback: usa la directory corrente
    return os.path.join(start, 'database', 'tool_master.db')

_BASE   = os.path.dirname(os.path.abspath(__file__))
DB_PATH = _trova_db()

# Definizione campi con peso e criticita
# critico=True -> mancanza = rosso
# critico=False -> mancanza = giallo
CAMPI = {
    'codice_interno':       {'label': 'Codice interno',         'critico': True,  'peso': 15},
    'tipo':                 {'label': 'Tipo utensile',          'critico': True,  'peso': 10},
    'diametro_mm':          {'label': 'Diametro',               'critico': True,  'peso': 10},
    'lunghezza_totale_mm':  {'label': 'Lunghezza totale',       'critico': True,  'peso': 8},
    'lunghezza_tagl_mm':    {'label': 'Lunghezza tagliente',    'critico': True,  'peso': 8},
    'num_taglienti':        {'label': 'N. taglienti',           'critico': True,  'peso': 7},
    'fuori_pinza_mm':       {'label': 'Fuori pinza',            'critico': True,  'peso': 12},
    'nome_pinza':           {'label': 'Nome pinza',             'critico': True,  'peso': 10},
    'raggio_punta_mm':      {'label': 'Raggio punta',          'critico': False, 'peso': 5},
    'descrizione':          {'label': 'Descrizione',            'critico': False, 'peso': 5},
    'codice_catalogo':      {'label': 'Codice catalogo',        'critico': False, 'peso': 5},
    'vc_default':           {'label': 'Vc default',             'critico': False, 'peso': 5},
}

PESO_TOTALE = sum(c['peso'] for c in CAMPI.values())

# Range valori accettabili per rilevare anomalie
RANGE_VALIDI = {
    'diametro_mm':         (0.1,  500.0),
    'raggio_punta_mm':     (0.0,  50.0),
    'lunghezza_totale_mm': (1.0,  600.0),
    'lunghezza_tagl_mm':   (0.5,  400.0),
    'fuori_pinza_mm':      (1.0,  400.0),
    'num_taglienti':       (1,    20),
    'vc_default':          (5.0,  2000.0),
}


def _semaforo(score: float) -> tuple:
    """Ritorna (colore, etichetta, css_class) in base allo score 0-100."""
    if score >= 90:   return ('#166534', 'Completo',    'verde')
    if score >= 70:   return ('#854d0e', 'Incompleto',  'giallo')
    return             ('#991b1b', 'Dati mancanti', 'rosso')


def analizza_utensile(u: dict, taglio: list) -> dict:
    """Analizza un singolo utensile e ritorna il report di qualita."""
    score = 0
    mancanti_critici = []
    mancanti_facoltativi = []
    anomalie = []

    for campo, info in CAMPI.items():
        val = u.get(campo)
        presente = val is not None and str(val).strip() not in ('', 'nan', 'None', '0') or (
            campo in ('raggio_punta_mm',) and val is not None)

        # Caso speciale: raggio 0 e' valido per fresa piatta
        if campo == 'raggio_punta_mm' and val == 0.0:
            presente = True

        if presente:
            score += info['peso']
        else:
            if info['critico']:
                mancanti_critici.append(info['label'])
            else:
                mancanti_facoltativi.append(info['label'])

    # Controlla range valori
    for campo, (vmin, vmax) in RANGE_VALIDI.items():
        val = u.get(campo)
        if val is not None and str(val) not in ('', 'nan', 'None'):
            try:
                v = float(val)
                if v != 0 and (v < vmin or v > vmax):
                    anomalie.append(f"{campo}: {v} (atteso {vmin}-{vmax})")
            except (ValueError, TypeError):
                pass

    # Controlla condizioni di taglio
    n_taglio = len(taglio)
    if n_taglio == 0 and u.get('tipo') in ('FLAT', 'BALL', 'BULL', 'DRILL'):
        mancanti_facoltativi.append('Condizioni di taglio (Vc/Fz per materiale)')

    score_pct = round(score / PESO_TOTALE * 100)
    colore, etichetta, css = _semaforo(score_pct)

    return {
        'score':                score_pct,
        'colore':               colore,
        'etichetta':            etichetta,
        'css':                  css,
        'mancanti_critici':     mancanti_critici,
        'mancanti_facoltativi': mancanti_facoltativi,
        'anomalie':             anomalie,
        'n_taglio':             n_taglio,
    }


def genera_report(conn=None) -> dict:
    """
    Genera il report completo di qualita per tutti gli utensili nel DB.
    
    Returns:
        dict con:
          - utensili: lista di { utensile, qualita }
          - riepilogo: statistiche globali
          - timestamp: datetime generazione
    """
    chiudi = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        chiudi = True

    try:
        utensili_db = conn.execute(
            "SELECT * FROM utensile_completo WHERE attivo=1 ORDER BY tipo, diametro_mm, codice_interno"
        ).fetchall()
    finally:
        if chiudi:
            conn.close()

    conn2 = sqlite3.connect(DB_PATH)
    conn2.row_factory = sqlite3.Row

    risultati = []
    n_verde = n_giallo = n_rosso = 0
    n_senza_taglio = 0

    for row in utensili_db:
        u = dict(row)
        taglio = conn2.execute(
            "SELECT * FROM condizioni_taglio WHERE id_utensile=?", (u['id'],)
        ).fetchall()

        qualita = analizza_utensile(u, taglio)
        risultati.append({'utensile': u, 'qualita': qualita})

        if qualita['css'] == 'verde':   n_verde += 1
        elif qualita['css'] == 'giallo': n_giallo += 1
        else:                            n_rosso += 1
        if qualita['n_taglio'] == 0:     n_senza_taglio += 1

    conn2.close()

    score_medio = round(sum(r['qualita']['score'] for r in risultati) / max(len(risultati), 1))

    return {
        'utensili':    risultati,
        'timestamp':   datetime.now().strftime('%d/%m/%Y %H:%M'),
        'riepilogo': {
            'totale':        len(risultati),
            'verdi':         n_verde,
            'gialli':        n_giallo,
            'rossi':         n_rosso,
            'senza_taglio':  n_senza_taglio,
            'score_medio':   score_medio,
            'colore_globale':_semaforo(score_medio)[0],
            'etichetta':     _semaforo(score_medio)[1],
        }
    }


def genera_html_report(conn=None) -> str:
    """Genera un report HTML completo e leggibile, scaricabile come file."""
    report = genera_report(conn)
    r = report['riepilogo']

    def badge(css, label):
        colors = {
            'verde':  ('#dcfce7','#166534'),
            'giallo': ('#fef9c3','#854d0e'),
            'rosso':  ('#fee2e2','#991b1b'),
        }
        bg, fg = colors.get(css, ('#f1f0ee','#6b7280'))
        return f'<span style="background:{bg};color:{fg};padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600">{label}</span>'

    righe = []
    for item in report['utensili']:
        u = item['utensile']
        q = item['qualita']
        problemi = ''
        if q['mancanti_critici']:
            problemi += f'<div style="color:#991b1b;font-size:12px">&#9888; Mancanti critici: {", ".join(q["mancanti_critici"])}</div>'
        if q['mancanti_facoltativi']:
            problemi += f'<div style="color:#854d0e;font-size:12px">&#9432; Mancanti: {", ".join(q["mancanti_facoltativi"])}</div>'
        if q['anomalie']:
            problemi += f'<div style="color:#7c3aed;font-size:12px">&#9642; Anomalie: {"; ".join(q["anomalie"])}</div>'
        if not problemi:
            problemi = '<div style="color:#166534;font-size:12px">&#10003; Dati completi</div>'

        taglio_cell = f'<span style="color:#166534;font-weight:600">{q["n_taglio"]}</span>' if q['n_taglio'] > 0 else '<span style="color:#aaa">—</span>'

        righe.append(f"""
        <tr>
          <td style="font-weight:600">{u.get('codice_interno','?')}</td>
          <td>{u.get('tipo','?')}</td>
          <td style="text-align:right">{u.get('diametro_mm','?')}</td>
          <td style="text-align:right;background:#f0fdf4;font-weight:600;color:#1a6e35">{u.get('fuori_pinza_mm','—')}</td>
          <td>{u.get('nome_pinza','—')}</td>
          <td style="text-align:center">{taglio_cell}</td>
          <td style="text-align:center">{badge(q["css"], f'{q["score"]}%')}</td>
          <td>{problemi}</td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>Report Qualita Utensili - {report['timestamp']}</title>
<style>
  body {{ font-family:system-ui,sans-serif; margin:2rem; background:#f5f5f3; color:#1a1a1a }}
  .header {{ background:#1a1a1a; color:#fff; padding:1.5rem 2rem; border-radius:10px; margin-bottom:1.5rem }}
  .header h1 {{ margin:0; font-size:1.3rem }}
  .header p  {{ margin:.3rem 0 0; color:#aaa; font-size:.9rem }}
  .kpi {{ display:grid; grid-template-columns:repeat(5,1fr); gap:1rem; margin-bottom:1.5rem }}
  .kpi-box {{ background:#fff; border:1px solid #e2e2df; border-radius:8px; padding:1rem; text-align:center }}
  .kpi-n {{ font-size:2rem; font-weight:700 }}
  .kpi-l {{ font-size:11px; color:#888; margin-top:.2rem }}
  .card {{ background:#fff; border:1px solid #e2e2df; border-radius:10px; padding:1.5rem; margin-bottom:1rem }}
  table {{ width:100%; border-collapse:collapse; font-size:13px }}
  th,td {{ border:1px solid #e2e2df; padding:8px 10px; text-align:left; vertical-align:top }}
  th {{ background:#f8f8f6; font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.04em }}
  tr:hover td {{ background:#fafaf8 }}
  .legenda {{ display:flex; gap:1rem; font-size:12px; margin-bottom:1rem; flex-wrap:wrap }}
</style>
</head>
<body>
<div class="header">
  <h1>&#128295; Report Qualita Utensili</h1>
  <p>Generato il {report['timestamp']} &nbsp;|&nbsp; {r['totale']} utensili nel database master</p>
</div>

<div class="kpi">
  <div class="kpi-box" style="border-top:3px solid #166534">
    <div class="kpi-n" style="color:#166534">{r['verdi']}</div>
    <div class="kpi-l">&#9679; Dati completi (&#8805;90%)</div>
  </div>
  <div class="kpi-box" style="border-top:3px solid #854d0e">
    <div class="kpi-n" style="color:#854d0e">{r['gialli']}</div>
    <div class="kpi-l">&#9679; Dati incompleti (70-89%)</div>
  </div>
  <div class="kpi-box" style="border-top:3px solid #991b1b">
    <div class="kpi-n" style="color:#991b1b">{r['rossi']}</div>
    <div class="kpi-l">&#9679; Dati mancanti (&lt;70%)</div>
  </div>
  <div class="kpi-box" style="border-top:3px solid #7c3aed">
    <div class="kpi-n" style="color:#7c3aed">{r['senza_taglio']}</div>
    <div class="kpi-l">Senza dati Vc/Fz</div>
  </div>
  <div class="kpi-box" style="border-top:3px solid #1d4ed8">
    <div class="kpi-n" style="color:#1d4ed8">{r['score_medio']}%</div>
    <div class="kpi-l">Score medio qualita</div>
  </div>
</div>

<div class="card">
  <div class="legenda">
    <span><b>Leggenda:</b></span>
    <span style="color:#991b1b">&#9888; Critici = dati obbligatori per la lavorazione (tipo, diametro, fuori pinza)</span>
    <span style="color:#854d0e">&#9432; Facoltativi = utili ma non bloccanti</span>
    <span style="color:#7c3aed">&#9642; Anomalie = valori fuori range tipico</span>
  </div>
  <table>
  <thead><tr>
    <th>Codice utensile</th>
    <th>Tipo</th>
    <th style="text-align:right">&#8960; (mm)</th>
    <th style="text-align:right;background:#f0fdf4;color:#166534">Fuori pinza</th>
    <th>Pinza</th>
    <th style="text-align:center">Vc/Fz</th>
    <th style="text-align:center">Qualita</th>
    <th>Note</th>
  </tr></thead>
  <tbody>
  {"".join(righe)}
  </tbody>
  </table>
</div>

<div style="text-align:center;color:#aaa;font-size:12px;margin-top:1rem">
  Tool DB Manager &nbsp;|&nbsp; Report generato automaticamente
</div>
</body>
</html>"""
    return html
