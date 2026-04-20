"""
svg_holder.py — Renderer SVG per profilo fresa e holder.
Punta IN BASSO (z=0), gambo/prolunga IN ALTO (z=FP).
Logica specchiatura identica per holder e fresa.
"""
import math


# ═══════════════════════════════════════════════════════════════
# Helper: disegna profilo cont2D simmetrico
# Stessa logica di render_holder_svg (forward + backward mirror)
# ═══════════════════════════════════════════════════════════════

def _disegna_profilo_simmetrico(elementi, to_x, to_y, scala,
                                 fill='#1e3a8a', stroke='#1e40af'):
    """Disegna profilo cont2D come path SVG chiuso simmetrico.
    to_x(r): cx + r*scala (r positivo=destra, negativo=sinistra)
    to_y(z): (height-margin) - z*scala
    """
    if not elementi or len(elementi) < 2:
        return ''

    def _ar(cx_a, cy_a, px, py):
        return math.sqrt((cx_a - px)**2 + (cy_a - py)**2)

    path = []

    # Forward (lato destro, r positivo)
    for i, e in enumerate(elementi):
        sr = abs(float(e.get('sx', 0)))
        sz = float(e.get('sy', 0))
        er = abs(float(e.get('ex', 0)))
        ez = float(e.get('ey', 0))
        if i == 0:
            path.append(f'M {to_x(sr):.2f},{to_y(sz):.2f}')
        if e.get('type', 'line') == 'line':
            path.append(f'L {to_x(er):.2f},{to_y(ez):.2f}')
        elif e['type'] in ('cwarc', 'ccwarc'):
            acx = abs(float(e.get('cx', 0)))
            acy = float(e.get('cy', 0))
            r = _ar(acx, acy, sr, sz) * scala
            if r < 0.1:
                r = _ar(acx, acy, er, ez) * scala
            sweep = 0 if e['type'] == 'cwarc' else 1
            path.append(f'A {r:.2f},{r:.2f} 0 0 {sweep} {to_x(er):.2f},{to_y(ez):.2f}')

    # Backward (lato sinistro, -r)
    for i in range(len(elementi) - 1, -1, -1):
        e = elementi[i]
        sr = abs(float(e.get('sx', 0)))
        sz = float(e.get('sy', 0))
        er = abs(float(e.get('ex', 0)))
        ez = float(e.get('ey', 0))
        if i == len(elementi) - 1:
            path.append(f'L {to_x(-er):.2f},{to_y(ez):.2f}')
        if e.get('type', 'line') == 'line':
            path.append(f'L {to_x(-sr):.2f},{to_y(sz):.2f}')
        elif e['type'] in ('cwarc', 'ccwarc'):
            acx = abs(float(e.get('cx', 0)))
            acy = float(e.get('cy', 0))
            r = _ar(acx, acy, sr, sz) * scala
            if r < 0.1:
                r = _ar(acx, acy, er, ez) * scala
            sweep = 1 if e['type'] == 'cwarc' else 0
            path.append(f'A {r:.2f},{r:.2f} 0 0 {sweep} {to_x(-sr):.2f},{to_y(sz):.2f}')

    path.append('Z')
    return f'<path d="{" ".join(path)}" fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>'


# ═══════════════════════════════════════════════════════════════
# FUNZIONE 1 — Profilo fresa
# ═══════════════════════════════════════════════════════════════

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
    D = diametro_mm or 10
    R = raggio_punta_mm or 0
    FP = fuori_pinza_mm or lunghezza_totale_mm or 60
    r_tool = reach_tool_mm or FP
    if r_tool <= 0:
        r_tool = FP
    r_ext = reach_extension_mm or 0
    L_tagl = lunghezza_tagl_mm or D * 0.3

    # Tipo esplicito
    t = (tipo or '').upper()
    if chamfer_angle_gradi and chamfer_angle_gradi > 0:
        tipo_r = 'CHAMFER'
    elif t == 'BALL':
        tipo_r = 'BALL'
    elif t == 'BULL':
        tipo_r = 'BULL'
    elif t in ('DRILL', 'REAM', 'TAP', 'THREAD', 'LOLLIPOP', 'FLAT'):
        tipo_r = t
    elif angolo_punta_gradi and angolo_punta_gradi > 0 and (not R or R == 0):
        tipo_r = 'DRILL'
    elif R and D and abs(R - D / 2) < 0.3:
        tipo_r = 'BALL'
    elif R and R > 0:
        tipo_r = 'BULL'
    else:
        tipo_r = 'FLAT'

    # BALL: R = D/2 per definizione
    if tipo_r == 'BALL' and (not R or R <= 0):
        R = D / 2.0

    # Scala
    margin = 24
    label_w = 50
    cx = (width - label_w) / 2.0
    r_max = D / 2.0
    scala_z = (height - 2 * margin) / FP if FP > 0 else 1
    scala_r = (cx - margin) / r_max if r_max > 0 else 1
    scala = min(scala_z, scala_r)

    def yz(z):
        return (height - margin) - z * scala

    def xr(r):
        return cx + abs(r) * scala

    def xl(r):
        return cx - abs(r) * scala

    def to_x(r):
        return cx + r * scala

    def to_y(z):
        return (height - margin) - z * scala

    def trap(zb, zt, rb, rt, fill, stroke):
        if zt <= zb:
            return ''
        return (f'<path d="M {xl(rb):.1f},{yz(zb):.1f} L {xr(rb):.1f},{yz(zb):.1f} '
                f'L {xr(rt):.1f},{yz(zt):.1f} L {xl(rt):.1f},{yz(zt):.1f} Z" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>')

    parts = []

    # ═══ ZONA 1: GAMBO (freeShaft o parametrico) — disegnato PRIMA ═══
    usa_freeshaft = (elementi_gambo and len(elementi_gambo) >= 2)
    if usa_freeshaft:
        troncati = []
        for e in elementi_gambo:
            ez = abs(float(e.get('ey', 0)))
            if ez <= r_tool:
                troncati.append(e)
            else:
                if troncati:
                    prev_e = troncati[-1]
                    pz = abs(float(prev_e.get('ey', 0)))
                    pr = abs(float(prev_e.get('ex', 0)))
                    cr = abs(float(e.get('ex', 0)))
                    if ez > pz:
                        frac = (r_tool - pz) / (ez - pz)
                        ri = pr + frac * (cr - pr)
                        troncati.append({'type': 'line',
                            'sx': str(pr), 'sy': str(pz),
                            'ex': str(ri), 'ey': str(r_tool)})
                break
        if troncati and len(troncati) >= 2:
            parts.append(_disegna_profilo_simmetrico(
                troncati, to_x, to_y, scala,
                fill='#e5e7eb', stroke='#9ca3af'))
    elif r_tool > L_tagl:
        D_stelo = diam_stelo_mm or D
        if shaft_chamfer_pos_mm and shaft_chamfer_pos_mm > L_tagl:
            z_ch = min(shaft_chamfer_pos_mm, r_tool)
            parts.append(trap(L_tagl, z_ch, D / 2, D / 2, '#e5e7eb', '#9ca3af'))
            if r_tool > z_ch:
                parts.append(trap(z_ch, r_tool, D / 2, D_stelo / 2, '#d1d5db', '#9ca3af'))
        else:
            parts.append(trap(L_tagl, r_tool, D / 2, D_stelo / 2, '#e5e7eb', '#9ca3af'))

    # ═══ ZONA 2: TAGLIENTE (parametrico) — disegnato DOPO (sovrappone) ═══
    if tipo_r == 'BALL':
        arc_r = R * scala
        y_chord = yz(R)
        # sweep=0: antiorario in SVG = curva verso y maggiore = verso punta (z=0)
        parts.append(f'<path d="M {xl(R):.1f},{y_chord:.1f} '
                     f'A {arc_r:.1f},{arc_r:.1f} 0 0 0 {xr(R):.1f},{y_chord:.1f} Z" '
                     f'fill="#1e3a8a" stroke="#1e40af" stroke-width="0.8"/>')
        if L_tagl > R + 0.3:
            parts.append(trap(R, L_tagl, D / 2, D / 2, '#1e3a8a', '#1e40af'))
    elif tipo_r == 'BULL' and R > 0:
        cr = R * scala
        half_flat = max((D / 2 - R), 0) * scala
        y_R = yz(R)
        y_0 = yz(0)
        parts.append(f'<path d="M {xr(D/2):.1f},{y_R:.1f} '
                     f'A {cr:.1f},{cr:.1f} 0 0 1 {cx + half_flat:.1f},{y_0:.1f} '
                     f'L {cx - half_flat:.1f},{y_0:.1f} '
                     f'A {cr:.1f},{cr:.1f} 0 0 1 {xl(D/2):.1f},{y_R:.1f} Z" '
                     f'fill="#1e3a8a" stroke="#1e40af" stroke-width="0.8"/>')
        if L_tagl > R:
            parts.append(trap(R, L_tagl, D / 2, D / 2, '#1e3a8a', '#1e40af'))
    elif tipo_r == 'DRILL':
        ang = angolo_punta_gradi or 118
        h_p = (D / 2) / math.tan(math.radians(ang / 2)) if 0 < ang < 180 else D * 0.3
        h_p = min(h_p, L_tagl)
        parts.append(trap(0, h_p, 0, D / 2, '#1e3a8a', '#1e40af'))
        if L_tagl > h_p:
            parts.append(trap(h_p, L_tagl, D / 2, D / 2, '#1e3a8a', '#1e40af'))
    elif tipo_r == 'CHAMFER':
        r_tip = (tip_diameter_mm / 2) if tip_diameter_mm and tip_diameter_mm > 0 else 0.5
        parts.append(trap(0, L_tagl, r_tip, D / 2, '#1e3a8a', '#1e40af'))
    else:
        parts.append(trap(0, L_tagl, D / 2, D / 2, '#1e3a8a', '#1e40af'))

    # ═══ ZONA 3: PROLUNGA (r_tool → FP) ═══
    if r_ext > 0 and FP > r_tool:
        r_prol = D / 2
        parts.append(trap(r_tool, FP, r_prol, r_prol, '#c4b5fd', '#8b5cf6'))
        if extension_name:
            yl = yz(r_tool + r_ext / 2)
            parts.append(f'<text x="{xr(r_prol) + 4:.0f}" y="{yl + 3:.1f}" '
                         f'font-size="8" fill="#6d28d9" font-family="sans-serif">'
                         f'{extension_name[:22]}</text>')

    # ═══ DECORAZIONI ═══
    parts.append(f'<line x1="{cx}" y1="{yz(FP) - 5:.1f}" x2="{cx}" y2="{yz(0) + 5:.1f}" '
                 f'stroke="#ddd" stroke-width="0.5" stroke-dasharray="3,3"/>')
    y_fp = yz(FP)
    parts.append(f'<line x1="{margin:.0f}" y1="{y_fp:.1f}" '
                 f'x2="{xr(r_max) + 4:.0f}" y2="{y_fp:.1f}" '
                 f'stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4,3"/>')
    parts.append(f'<text x="{xr(r_max) + 7:.0f}" y="{y_fp + 4:.1f}" '
                 f'font-size="10" fill="#f59e0b" font-family="monospace">{FP:.1f}</text>')
    lbl = f'D{D}'
    if R:
        lbl += f'R{R}'
    parts.append(f'<text x="{cx:.0f}" y="{height - 5}" text-anchor="middle" '
                 f'font-size="9" fill="#666" font-family="sans-serif">{lbl}</text>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" style="background:transparent">'
            f'{"".join(parts)}</svg>')


# ═══════════════════════════════════════════════════════════════
# FUNZIONE 2 — Profilo holder da cont2D (identica, non toccare)
# ═══════════════════════════════════════════════════════════════

def _arc_radius(cx, cy, px, py):
    return math.sqrt((cx - px) ** 2 + (cy - py) ** 2)


def render_holder_svg(elementi, width=300, height=400, colore='#6366f1', margin=15):
    """Genera SVG del profilo holder da elementi cont2D."""
    if not elementi:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><text x="10" y="25" font-size="12" fill="#aaa">nessuna geometria</text></svg>'

    all_r = [0.0]
    all_z = [0.0]
    for e in elementi:
        for k in ('sx', 'ex'):
            if e.get(k) is not None:
                all_r.append(abs(float(e[k])))
        for k in ('sy', 'ey'):
            if e.get(k) is not None:
                all_z.append(abs(float(e[k])))

    max_r = max(all_r) or 1.0
    max_z = max(all_z) or 1.0

    usable_w = (width / 2) - margin
    usable_h = height - 2 * margin
    scale = min(usable_w / max_r, usable_h / max_z)
    svg_cx = width / 2

    def to_x(r):
        return svg_cx + r * scale

    def to_y(z):
        return (height - margin) - z * scale

    path_parts = []
    for i, e in enumerate(elementi):
        sr = float(e.get('sx', 0))
        sz = float(e.get('sy', 0))
        er = float(e.get('ex', 0))
        ez = float(e.get('ey', 0))
        if i == 0:
            path_parts.append(f'M {to_x(sr):.2f},{to_y(sz):.2f}')
        if e['type'] == 'line':
            path_parts.append(f'L {to_x(er):.2f},{to_y(ez):.2f}')
        elif e['type'] in ('cwarc', 'ccwarc'):
            acx_v = float(e.get('cx', 0))
            acy_v = float(e.get('cy', 0))
            radius = _arc_radius(acx_v, acy_v, sr, sz) * scale
            if radius < 0.1:
                radius = _arc_radius(acx_v, acy_v, er, ez) * scale
            sweep = 0 if e['type'] == 'cwarc' else 1
            path_parts.append(f'A {radius:.2f},{radius:.2f} 0 0 {sweep} {to_x(er):.2f},{to_y(ez):.2f}')

    for i in range(len(elementi) - 1, -1, -1):
        e = elementi[i]
        sr = float(e.get('sx', 0))
        sz = float(e.get('sy', 0))
        er = float(e.get('ex', 0))
        ez = float(e.get('ey', 0))
        if i == len(elementi) - 1:
            path_parts.append(f'L {to_x(-er):.2f},{to_y(ez):.2f}')
        if e['type'] == 'line':
            path_parts.append(f'L {to_x(-sr):.2f},{to_y(sz):.2f}')
        elif e['type'] in ('cwarc', 'ccwarc'):
            acx_v = float(e.get('cx', 0))
            acy_v = float(e.get('cy', 0))
            radius = _arc_radius(acx_v, acy_v, sr, sz) * scale
            if radius < 0.1:
                radius = _arc_radius(acx_v, acy_v, er, ez) * scale
            sweep = 1 if e['type'] == 'cwarc' else 0
            path_parts.append(f'A {radius:.2f},{radius:.2f} 0 0 {sweep} {to_x(-sr):.2f},{to_y(sz):.2f}')

    path_parts.append('Z')
    d = ' '.join(path_parts)

    y1 = to_y(max_z) - 5
    y2 = to_y(0) + 5

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" style="background:transparent">'
            f'<line x1="{svg_cx}" y1="{y1:.1f}" x2="{svg_cx}" y2="{y2:.1f}" '
            f'stroke="#ddd" stroke-width="0.5" stroke-dasharray="4,3"/>'
            f'<path d="{d}" fill="{colore}" fill-opacity="0.2" stroke="#4f46e5" stroke-width="1.5"/>'
            f'</svg>')
