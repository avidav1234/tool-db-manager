"""
svg_holder.py — Renderer SVG per profilo holder e fresa da geometria cont2D.

Input: lista di elem2D dict {type, sx, sy, ex, ey, cx, cy, cuttingArea}
Output: stringa SVG con profilo 2D simmetrico (lato destro rispecchiato a sinistra)
"""
import math


def _arc_radius(cx, cy, px, py):
    """Calcola raggio dall'arco centro-punto."""
    return math.sqrt((cx - px) ** 2 + (cy - py) ** 2)


def _arc_large_flag(sx, sy, ex, ey, cx, cy, clockwise):
    """Determina large-arc-flag per SVG path A."""
    # Angoli dal centro
    a_start = math.atan2(sy - cy, sx - cx)
    a_end = math.atan2(ey - cy, ex - cx)
    delta = (a_end - a_start) % (2 * math.pi)
    if clockwise:
        return 1 if delta > math.pi else 0
    else:
        return 1 if (2 * math.pi - delta) > math.pi else 0


def render_holder_svg(elementi, width=300, height=400, colore='#4a90d9', margin=15):
    """Genera SVG del profilo holder da elementi cont2D.

    Coordinate: r (raggio, asse X) e z (lunghezza, asse Y).
    Il profilo viene rispecchiato sull'asse Z per simmetria.
    """
    if not elementi:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><text x="10" y="25" font-size="12" fill="#aaa">nessuna geometria</text></svg>'

    # Bounding box
    all_r = [0.0]
    all_z = [0.0]
    for e in elementi:
        for k in ('sx', 'ex'):
            if e.get(k) is not None:
                all_r.append(abs(e[k]))
        for k in ('sy', 'ey'):
            if e.get(k) is not None:
                all_z.append(abs(e[k]))
        if e.get('cx') is not None:
            r = _arc_radius(e['cx'], e['cy'], e.get('ex', 0), e.get('ey', 0))
            all_r.append(abs(e['cx']) + r)

    max_r = max(all_r) or 1.0
    max_z = max(all_z) or 1.0

    # Scale
    usable_w = (width / 2) - margin
    usable_h = height - 2 * margin
    scale_r = usable_w / max_r
    scale_z = usable_h / max_z
    scale = min(scale_r, scale_z)
    cx_svg = width / 2

    def to_svg(r, z):
        return cx_svg + r * scale, margin + z * scale

    def to_svg_mirror(r, z):
        return cx_svg - r * scale, margin + z * scale

    # Build right-side path
    path_right = []
    path_left = []

    for i, e in enumerate(elementi):
        sr = e.get('sx', 0)
        sz = e.get('sy', 0)
        er = e.get('ex', 0)
        ez = e.get('ey', 0)

        sx_svg, sy_svg = to_svg(sr, sz)
        ex_svg, ey_svg = to_svg(er, ez)
        sx_m, sy_m = to_svg_mirror(sr, sz)
        ex_m, ey_m = to_svg_mirror(er, ez)

        if i == 0:
            path_right.append(f'M {sx_svg:.2f},{sy_svg:.2f}')
            path_left.append(f'M {sx_m:.2f},{sy_m:.2f}')

        if e['type'] == 'line':
            path_right.append(f'L {ex_svg:.2f},{ey_svg:.2f}')
            path_left.append(f'L {ex_m:.2f},{ey_m:.2f}')
        elif e['type'] in ('cwarc', 'ccwarc'):
            acx = e.get('cx', 0)
            acy = e.get('cy', 0)
            radius = _arc_radius(acx, acy, sr, sz) * scale
            if radius < 0.1:
                radius = _arc_radius(acx, acy, er, ez) * scale
            sweep = 1 if e['type'] == 'cwarc' else 0
            large = _arc_large_flag(sr, sz, er, ez, acx, acy, e['type'] == 'cwarc')
            path_right.append(f'A {radius:.2f},{radius:.2f} 0 {large} {sweep} {ex_svg:.2f},{ey_svg:.2f}')
            # Mirror: swap sweep direction
            sweep_m = 0 if sweep == 1 else 1
            path_left.append(f'A {radius:.2f},{radius:.2f} 0 {large} {sweep_m} {ex_m:.2f},{ey_m:.2f}')

    # Reverse left path for closed shape
    d_right = ' '.join(path_right)
    # Close bottom: connect right end to left end, then trace left back up
    last_r = elementi[-1].get('ex', 0)
    last_z = elementi[-1].get('ey', 0)
    lx_r, ly_r = to_svg(last_r, last_z)
    lx_m, ly_m = to_svg_mirror(last_r, last_z)

    # Build full closed path: right side down, bottom line, left side up
    # Left side reversed
    path_left_rev = []
    for i in range(len(elementi) - 1, -1, -1):
        e = elementi[i]
        sr = e.get('sx', 0)
        sz = e.get('sy', 0)
        sx_m, sy_m = to_svg_mirror(sr, sz)
        er = e.get('ex', 0)
        ez = e.get('ey', 0)
        ex_m, ey_m = to_svg_mirror(er, ez)

        if i == len(elementi) - 1:
            path_left_rev.append(f'L {ex_m:.2f},{ey_m:.2f}')

        if e['type'] == 'line':
            path_left_rev.append(f'L {sx_m:.2f},{sy_m:.2f}')
        elif e['type'] in ('cwarc', 'ccwarc'):
            acx = e.get('cx', 0)
            acy = e.get('cy', 0)
            radius = _arc_radius(acx, acy, sr, sz) * scale
            if radius < 0.1:
                radius = _arc_radius(acx, acy, er, ez) * scale
            sweep = 0 if e['type'] == 'cwarc' else 1
            large = _arc_large_flag(er, ez, sr, sz, acx, acy, e['type'] != 'cwarc')
            path_left_rev.append(f'A {radius:.2f},{radius:.2f} 0 {large} {sweep} {sx_m:.2f},{sy_m:.2f}')

    full_path = d_right + ' ' + ' '.join(path_left_rev) + ' Z'

    # Asse Z tratteggiato
    az_y1 = margin - 5
    az_y2 = margin + max_z * scale + 5

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
  viewBox="0 0 {width} {height}" style="background:transparent">
  <line x1="{cx_svg}" y1="{az_y1:.1f}" x2="{cx_svg}" y2="{az_y2:.1f}"
    stroke="#ccc" stroke-width="0.5" stroke-dasharray="4,3"/>
  <path d="{full_path}" fill="{colore}" fill-opacity="0.25" stroke="{colore}" stroke-width="1.5"/>
</svg>'''
    return svg


def render_fresa_svg(elementi_profilo=None, elementi_taglio=None,
                     diametro_mm=None, lunghezza_mm=None,
                     tipo='FLAT', raggio_mm=0, width=200, height=300,
                     colore_corpo='#6b7280', colore_taglio='#ef4444'):
    """Genera SVG del profilo fresa.

    Se elementi_profilo non vuoto: usa cont2D.
    Altrimenti: fallback parametrico da tipo/diametro/raggio/lunghezza.
    """
    if elementi_profilo:
        return render_holder_svg(elementi_profilo, width=width, height=height, colore=colore_corpo)

    # Fallback parametrico
    if not diametro_mm or not lunghezza_mm:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><text x="10" y="25" font-size="12" fill="#aaa">dati insufficienti</text></svg>'

    r = diametro_mm / 2
    cr = raggio_mm or 0
    l = lunghezza_mm
    margin = 15
    max_dim = max(r, l)
    scale = min((width / 2 - margin) / r, (height - 2 * margin) / l) if r > 0 and l > 0 else 1.0
    cx = width / 2

    def tx(rr):
        return cx + rr * scale

    def ty(zz):
        return margin + zz * scale

    path = ''
    if tipo == 'BALL':
        # Semicerchio punta + cilindro
        path = (f'M {tx(0):.1f},{ty(0):.1f} '
                f'A {r*scale:.1f},{r*scale:.1f} 0 0 1 {tx(r):.1f},{ty(r):.1f} '
                f'L {tx(r):.1f},{ty(l):.1f} '
                f'L {tx(-r):.1f},{ty(l):.1f} '
                f'L {tx(-r):.1f},{ty(r):.1f} '
                f'A {r*scale:.1f},{r*scale:.1f} 0 0 1 {tx(0):.1f},{ty(0):.1f} Z')
    elif tipo == 'BULL':
        # Raccordo torico
        y_cr = cr  # dove finisce il raccordo
        path = (f'M {tx(0):.1f},{ty(0):.1f} '
                f'L {tx(r-cr):.1f},{ty(0):.1f} '
                f'A {cr*scale:.1f},{cr*scale:.1f} 0 0 1 {tx(r):.1f},{ty(cr):.1f} '
                f'L {tx(r):.1f},{ty(l):.1f} '
                f'L {tx(-r):.1f},{ty(l):.1f} '
                f'L {tx(-r):.1f},{ty(cr):.1f} '
                f'A {cr*scale:.1f},{cr*scale:.1f} 0 0 1 {tx(-(r-cr)):.1f},{ty(0):.1f} Z')
    elif tipo == 'DRILL':
        # Cono punta 118deg + cilindro
        punta_h = r * 0.6  # approssimazione punta
        path = (f'M {tx(0):.1f},{ty(0):.1f} '
                f'L {tx(r):.1f},{ty(punta_h):.1f} '
                f'L {tx(r):.1f},{ty(l):.1f} '
                f'L {tx(-r):.1f},{ty(l):.1f} '
                f'L {tx(-r):.1f},{ty(punta_h):.1f} Z')
    else:
        # FLAT / default: cilindro semplice
        path = (f'M {tx(-r):.1f},{ty(0):.1f} '
                f'L {tx(r):.1f},{ty(0):.1f} '
                f'L {tx(r):.1f},{ty(l):.1f} '
                f'L {tx(-r):.1f},{ty(l):.1f} Z')

    # Asse
    az_y1 = margin - 5
    az_y2 = margin + l * scale + 5

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
  viewBox="0 0 {width} {height}" style="background:transparent">
  <line x1="{cx}" y1="{az_y1:.1f}" x2="{cx}" y2="{az_y2:.1f}"
    stroke="#ccc" stroke-width="0.5" stroke-dasharray="4,3"/>
  <path d="{path}" fill="{colore_corpo}" fill-opacity="0.2" stroke="{colore_corpo}" stroke-width="1.5"/>
</svg>'''
    return svg
