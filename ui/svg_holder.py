"""
svg_holder.py — Renderer SVG per profilo fresa e holder.
Punta IN BASSO (z=0), gambo/prolunga IN ALTO (z=FP).
"""
import math

def _ar(cx, cy, px, py):
    return math.sqrt((cx - px)**2 + (cy - py)**2)

def render_fresa_svg(
    diametro_mm=10, lunghezza_totale_mm=60,
    lunghezza_tagl_mm=None, raggio_punta_mm=0,
    angolo_punta_gradi=None, tipo='BULL',
    fuori_pinza_mm=None, reach_tool_mm=None,
    reach_extension_mm=None, extension_name=None,
    diam_stelo_mm=None, tip_diameter_mm=None,
    shaft_chamfer_pos_mm=None, chamfer_angle_gradi=None,
    elementi_taglio=None, elementi_gambo=None,
    width=220, height=400, **kwargs
):
    # --- 1. Parametrizzazione ---
    D = float(diametro_mm or 10)
    R = float(raggio_punta_mm or 0)
    L_tagl = float(lunghezza_tagl_mm or (D * 0.3))
    FP = float(fuori_pinza_mm or lunghezza_totale_mm or 60)
    r_tool = float(reach_tool_mm or FP)
    if r_tool <= 0: r_tool = FP

    t = (tipo or '').upper()
    if 'BALL' in t or (R >= D/2 - 0.05 and D > 0):
        tipo_r = 'BALL'; R = D/2
    elif 'BULL' in t or R > 0:
        tipo_r = 'BULL'
    elif 'DRILL' in t or (angolo_punta_gradi and angolo_punta_gradi > 0):
        tipo_r = 'DRILL'
    elif 'CHAMFER' in t or (tip_diameter_mm and tip_diameter_mm > 0):
        tipo_r = 'CHAMFER'
    else:
        tipo_r = 'FLAT'

    # --- 2. Costruzione Profilo Destro ---
    profilo = []

    # A. Punta
    usa_tip = (elementi_taglio and tipo_r not in ('BULL', 'BALL', 'FLAT', 'DRILL', 'REAM', 'TAP', 'THREAD'))
    if usa_tip:
        for e in elementi_taglio:
            profilo.append({
                'type': e.get('type', 'line'),
                'sx': abs(float(e.get('sx', 0))), 'sy': float(e.get('sy', 0)),
                'ex': abs(float(e.get('ex', 0))), 'ey': float(e.get('ey', 0)),
                'cx': abs(float(e.get('cx', 0))), 'cy': float(e.get('cy', 0))
            })
    else:
        if tipo_r == 'BALL':
            profilo.append({'type': 'ccwarc', 'sx': 0, 'sy': 0, 'ex': D/2, 'ey': D/2, 'cx': 0, 'cy': D/2})
            if L_tagl > D/2: profilo.append({'type': 'line', 'sx': D/2, 'sy': D/2, 'ex': D/2, 'ey': L_tagl})
        elif tipo_r == 'BULL':
            hf = max(0, D/2 - R)
            if hf > 0: profilo.append({'type': 'line', 'sx': 0, 'sy': 0, 'ex': hf, 'ey': 0})
            profilo.append({'type': 'ccwarc', 'sx': hf, 'sy': 0, 'ex': D/2, 'ey': R, 'cx': hf, 'cy': R})
            if L_tagl > R: profilo.append({'type': 'line', 'sx': D/2, 'sy': R, 'ex': D/2, 'ey': L_tagl})
        elif tipo_r == 'DRILL':
            ang = angolo_punta_gradi or 118
            hp = (D/2) / math.tan(math.radians(ang/2)) if 0 < ang < 180 else D*0.3
            profilo.append({'type': 'line', 'sx': 0, 'sy': 0, 'ex': D/2, 'ey': hp})
            if L_tagl > hp: profilo.append({'type': 'line', 'sx': D/2, 'sy': hp, 'ex': D/2, 'ey': L_tagl})
        elif tipo_r == 'CHAMFER':
            rtip = (tip_diameter_mm or 0) / 2.0
            profilo.append({'type': 'line', 'sx': rtip, 'sy': 0, 'ex': D/2, 'ey': L_tagl})
        else:
            profilo.append({'type': 'line', 'sx': 0, 'sy': 0, 'ex': D/2, 'ey': 0})
            profilo.append({'type': 'line', 'sx': D/2, 'sy': 0, 'ex': D/2, 'ey': L_tagl})

    # B. Gambo
    curr_z = profilo[-1]['ey'] if profilo else 0
    curr_r = profilo[-1]['ex'] if profilo else 0

    if elementi_gambo:
        gambo_to_add = []
        for e in elementi_gambo:
            sz, ez = float(e.get('sy', 0)), float(e.get('ey', 0))
            if ez <= curr_z: continue
            if sz >= r_tool: continue
            ne = {'type': e.get('type', 'line'), 'sx': abs(float(e.get('sx', 0))), 'sy': sz, 'ex': abs(float(e.get('ex', 0))), 'ey': ez, 'cx': abs(float(e.get('cx', 0))), 'cy': float(e.get('cy', 0))}
            if sz < curr_z:
                if ne['type'] == 'line':
                    frac = (curr_z - sz) / (ez - sz) if ez != sz else 0
                    ne['sx'] = ne['sx'] + frac * (ne['ex'] - ne['sx'])
                ne['sy'] = curr_z
            if ez > r_tool:
                if ne['type'] == 'line':
                    frac = (r_tool - ne['sy']) / (ez - ne['sy']) if ez != ne['sy'] else 0
                    ne['ex'] = ne['sx'] + frac * (ne['ex'] - ne['sx'])
                ne['ey'] = r_tool
                gambo_to_add.append(ne); break
            gambo_to_add.append(ne)

        if gambo_to_add:
            if abs(curr_r - gambo_to_add[0]['sx']) > 0.01:
                profilo.append({'type': 'line', 'sx': curr_r, 'sy': curr_z, 'ex': gambo_to_add[0]['sx'], 'ey': curr_z})
            profilo.extend(gambo_to_add)
    else:
        Dst = float(diam_stelo_mm or D)
        if r_tool > curr_z:
            if shaft_chamfer_pos_mm and curr_z < shaft_chamfer_pos_mm < r_tool:
                profilo.append({'type': 'line', 'sx': curr_r, 'sy': curr_z, 'ex': D/2, 'ey': shaft_chamfer_pos_mm})
                profilo.append({'type': 'line', 'sx': D/2, 'sy': shaft_chamfer_pos_mm, 'ex': Dst/2, 'ey': r_tool})
            else:
                profilo.append({'type': 'line', 'sx': curr_r, 'sy': curr_z, 'ex': Dst/2, 'ey': r_tool})

    # --- 3. Scaling ---
    all_rs = [D/2]
    for e in profilo:
        all_rs.extend([e['sx'], e['ex']])
        if e['type'] != 'line':
            rad = _ar(e['cx'], e['cy'], e['sx'], e['sy'])
            all_rs.append(e['cx'] + rad)
    max_r = max(all_rs) if all_rs else 1.0
    margin = 24; label_w = 50; cx_svg = (width - label_w) / 2.0
    scala = min((cx_svg - margin) / max_r, (height - 2*margin) / FP)
    def tx(r): return cx_svg + r * scala
    def ty(z): return (height - margin) - z * scala

    # --- 4. Path Generation ---
    d_parts = []
    if profilo:
        d_parts.append(f"M {tx(profilo[0]['sx']):.2f},{ty(profilo[0]['sy']):.2f}")
        for e in profilo:
            if e['type'] == 'line': d_parts.append(f"L {tx(e['ex']):.2f},{ty(e['ey']):.2f}")
            else:
                r_svg = _ar(e['cx'], e['cy'], e['sx'], e['sy']) * scala
                sweep = 0 if e['type'] == 'ccwarc' else 1
                d_parts.append(f"A {r_svg:.2f},{r_svg:.2f} 0 0 {sweep} {tx(e['ex']):.2f},{ty(e['ey']):.2f}")
        last_ex, last_ey = profilo[-1]['ex'], profilo[-1]['ey']
        d_parts.append(f"L {tx(-last_ex):.2f},{ty(last_ey):.2f}")
        for i in range(len(profilo)-1, -1, -1):
            e = profilo[i]
            if e['type'] == 'line': d_parts.append(f"L {tx(-e['sx']):.2f},{ty(e['sy']):.2f}")
            else:
                r_svg = _ar(e['cx'], e['cy'], e['sx'], e['sy']) * scala
                sweep = 1 if e['type'] == 'ccwarc' else 0
                d_parts.append(f"A {r_svg:.2f},{r_svg:.2f} 0 0 {sweep} {tx(-e['sx']):.2f},{ty(e['sy']):.2f}")
        d_parts.append("Z")

    # --- 5. Render SVG ---
    parts = []
    parts.append(f'<path d="{" ".join(d_parts)}" fill="#1e3a8a" fill-opacity="0.8" stroke="#1e40af" stroke-width="1"/>')
    if reach_extension_mm and reach_extension_mm > 0:
        z_ext_top = min(FP, r_tool + reach_extension_mm)
        rext = max_r * 1.05
        ext_d = f"M {tx(-rext):.2f},{ty(r_tool):.2f} L {tx(rext):.2f},{ty(r_tool):.2f} L {tx(rext):.2f},{ty(z_ext_top):.2f} L {tx(-rext):.2f},{ty(z_ext_top):.2f} Z"
        parts.append(f'<path d="{ext_d}" fill="#c4b5fd" fill-opacity="0.4" stroke="#8b5cf6" stroke-width="1"/>')
        if extension_name: parts.append(f'<text x="{tx(rext)+4:.0f}" y="{ty(r_tool + (z_ext_top-r_tool)/2)+3:.1f}" font-size="9" fill="#6d28d9" font-family="sans-serif">{extension_name}</text>')
    parts.append(f'<line x1="{cx_svg}" y1="{ty(0)+5}" x2="{cx_svg}" y2="{ty(FP)-5}" stroke="#ccc" stroke-width="0.5" stroke-dasharray="4,2"/>')
    parts.append(f'<line x1="{margin}" y1="{ty(FP)}" x2="{tx(max_r)+10}" y2="{ty(FP)}" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="5,3"/>')
    parts.append(f'<text x="{tx(max_r)+12}" y="{ty(FP)+4}" font-size="11" fill="#f59e0b" font-weight="bold" font-family="monospace">{FP:.1f}</text>')
    label = f"D{D:.1f}" + (f" R{R:.1f}" if R > 0 else "")
    parts.append(f'<text x="{cx_svg}" y="{height-5}" text-anchor="middle" font-size="10" fill="#444" font-family="sans-serif">{label}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="background:transparent">'
            f'{"".join(parts)}</svg>')

def render_holder_svg(elementi, width=300, height=400, colore='#6366f1', margin=15):
    if not elementi: return '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><text x="10" y="25" font-size="12" fill="#aaa">nessuna geometria</text></svg>'
    all_r = [0.0]; all_z = [0.0]
    for e in elementi:
        for k in ('sx', 'ex'):
            if e.get(k) is not None: all_r.append(abs(float(e[k])))
        for k in ('sy', 'ey'):
            if e.get(k) is not None: all_z.append(abs(float(e[k])))
    max_r = max(all_r) or 1.0; max_z = max(all_z) or 1.0
    scale = min(((width/2)-margin)/max_r, (height-2*margin)/max_z); svg_cx = width/2
    def tx(r): return svg_cx + r * scale
    def ty(z): return (height - margin) - z * scale
    path = []
    for i, e in enumerate(elementi):
        sr, sz, er, ez = float(e.get('sx',0)), float(e.get('sy',0)), float(e.get('ex',0)), float(e.get('ey',0))
        if i == 0: path.append(f'M {tx(sr):.2f},{ty(sz):.2f}')
        if e['type'] == 'line': path.append(f'L {tx(er):.2f},{ty(ez):.2f}')
        else:
            r = math.sqrt((float(e.get('cx',0))-sr)**2 + (float(e.get('cy',0))-sz)**2) * scale
            path.append(f'A {r:.2f},{r:.2f} 0 0 {0 if e["type"]=="cwarc" else 1} {tx(er):.2f},{ty(ez):.2f}')
    for i in range(len(elementi)-1, -1, -1):
        e = elementi[i]; sr, sz, er, ez = float(e.get('sx',0)), float(e.get('sy',0)), float(e.get('ex',0)), float(e.get('ey',0))
        if i == len(elementi)-1: path.append(f'L {tx(-er):.2f},{ty(ez):.2f}')
        if e['type'] == 'line': path.append(f'L {tx(-sr):.2f},{ty(sz):.2f}')
        else:
            r = math.sqrt((float(e.get('cx',0))-sr)**2 + (float(e.get('cy',0))-sz)**2) * scale
            path.append(f'A {r:.2f},{r:.2f} 0 0 {1 if e["type"]=="cwarc" else 0} {tx(-sr):.2f},{ty(sz):.2f}')
    path.append('Z')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="background:transparent">'
            f'<path d="{" ".join(path)}" fill="{colore}" fill-opacity="0.2" stroke="#4f46e5" stroke-width="1.5"/></svg>')
