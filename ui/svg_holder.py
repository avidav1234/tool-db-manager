"""
svg_holder.py — Renderer SVG per profilo fresa e holder.

Principio: disegna SOLO cio che dicono i dati (freeTip, freeShaft, parametri).
Nessuna logica ad hoc, nessuna stima, nessuna soglia inventata.
Punta IN BASSO, gambo/prolunga IN ALTO.
"""
import math


# ═══════════════════════════════════════════════════════════════
# Helper: disegna un profilo cont2D come path SVG simmetrico
# ═══════════════════════════════════════════════════════════════

def _disegna_profilo(elementi, cx_svg, scala, yz_fn, xr_fn, xl_fn,
                     z_offset=0, z_scala=1.0,
                     fill='#1e3a8a', stroke='#1e40af'):
    """Converte elem2D in path SVG chiuso simmetrico (destro + mirror sinistro).

    z_offset: traslazione z in mm prima della conversione SVG.
    z_scala: fattore scala z (per comprimere profilo nello spazio disponibile).
    """
    if not elementi or len(elementi) < 2:
        return ''

    def to_y(z_mm):
        return yz_fn(z_mm * z_scala + z_offset)

    def to_xr(r_mm):
        return xr_fn(abs(r_mm))

    def to_xl(r_mm):
        return xl_fn(abs(r_mm))

    path_dx = []
    path_sx_rev = []  # costruito in ordine inverso
    prev_r, prev_z = None, None

    for i, e in enumerate(elementi):
        etype = e.get('type', 'line')
        ex = abs(float(e.get('ex', 0)))
        ey = float(e.get('ey', 0))

        if i == 0:
            sx = abs(float(e.get('sx', ex)))
            sy = float(e.get('sy', ey))
            path_dx.append(f'M {to_xr(sx):.1f},{to_y(sy):.1f}')
            path_sx_rev.append(f'{to_xl(sx):.1f},{to_y(sy):.1f}')
            prev_r, prev_z = sx, sy

        x1 = to_xr(ex)
        y1 = to_y(ey)

        if etype == 'line':
            path_dx.append(f'L {x1:.1f},{y1:.1f}')
            path_sx_rev.append(f'{to_xl(ex):.1f},{y1:.1f}')
        elif etype in ('cwarc', 'ccwarc'):
            cx_a = abs(float(e.get('cx', 0)))
            cy_a = float(e.get('cy', 0))
            r_arc = math.sqrt((prev_r - cx_a)**2 + (prev_z - cy_a)**2) * scala
            if r_arc < 0.1:
                r_arc = math.sqrt((ex - cx_a)**2 + (ey - cy_a)**2) * scala
            sweep_dx = 0 if etype == 'cwarc' else 1
            sweep_sx = 1 if etype == 'cwarc' else 0
            path_dx.append(f'A {r_arc:.2f},{r_arc:.2f} 0 0 {sweep_dx} {x1:.1f},{y1:.1f}')
            path_sx_rev.append(f'A{r_arc:.2f},{r_arc:.2f},0,0,{sweep_sx},{to_xl(ex):.1f},{y1:.1f}')

        prev_r, prev_z = ex, ey

    # Chiudi: ultimo punto destro → ultimo punto sinistro → risali sinistro → Z
    last_xl = to_xl(prev_r)
    last_y = to_y(prev_z)
    # Connetti lato destro a lato sinistro (in alto, poi percorri inverso)
    sx_parts = []
    sx_parts.append(f'L {last_xl:.1f},{last_y:.1f}')
    for item in reversed(path_sx_rev[1:]):
        if item.startswith('A'):
            sx_parts.append(item)
        else:
            sx_parts.append(f'L {item}')
    # Chiudi al primo punto sinistro
    sx_parts.append(f'L {path_sx_rev[0]}')

    d = ' '.join(path_dx) + ' ' + ' '.join(sx_parts) + ' Z'
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="0.8" fill-opacity="0.9"/>'


def _determina_tipo(tipo, R, angolo_punta, chamfer_angle, D):
    t = (tipo or '').upper()
    if chamfer_angle and chamfer_angle > 0:
        return 'CHAMFER'
    if t in ('DRILL', 'REAM', 'TAP', 'THREAD', 'LOLLIPOP'):
        return t
    if angolo_punta and angolo_punta > 0 and (not R or R == 0):
        return 'DRILL'
    if R and D and abs(R - D / 2) < 0.3:
        return 'BALL'
    if R and R > 0:
        return 'BULL'
    return 'FLAT'


# ═══════════════════════════════════════════════════════════════
# FUNZIONE PRINCIPALE — Profilo fresa
# ═══════════════════════════════════════════════════════════════

def render_fresa_svg(
    diametro_mm=10, lunghezza_totale_mm=60,
    lunghezza_tagl_mm=None, raggio_punta_mm=0,
    angolo_punta_gradi=None, tipo='BULL',
    fuori_pinza_mm=None, reach_tool_mm=None,
    reach_extension_mm=None, extension_name=None,
    diam_stelo_mm=None, tip_diameter_mm=None,
    shaft_chamfer_pos_mm=None,
    chamfer_angle_gradi=None,
    elementi_taglio=None,
    elementi_gambo=None,
    width=220, height=400,
    # Compat — accettati ma ignorati
    **kwargs
):
    """Genera SVG profilo fresa. Disegna solo cio che dicono i dati."""
    D = diametro_mm or 10
    R = raggio_punta_mm or 0
    FP = fuori_pinza_mm or lunghezza_totale_mm or 60
    r_tool = reach_tool_mm or FP
    if r_tool <= 0:
        r_tool = FP
    r_ext = reach_extension_mm or 0
    L_tagl = lunghezza_tagl_mm or D * 0.3

    margin = 24
    label_w = 50
    cx = (width - label_w) / 2.0

    # Raggio massimo dai profili reali
    r_massimo = D / 2.0
    for elems in (elementi_gambo, elementi_taglio):
        if elems:
            for e in elems:
                for k in ('ex', 'sx'):
                    v = e.get(k)
                    if v is not None:
                        r_massimo = max(r_massimo, abs(float(v)))

    scala_z = (height - 2 * margin) / FP if FP > 0 else 1
    scala_r = (cx - margin) / r_massimo if r_massimo > 0 else 1
    scala = min(scala_z, scala_r)

    def yz(z):
        return (height - margin) - z * scala

    def xr(r):
        return cx + abs(r) * scala

    def xl(r):
        return cx - abs(r) * scala

    def trap(zb, zt, rb, rt, fill, stroke):
        if zt <= zb:
            return ''
        return (f'<path d="M {xl(rb):.1f},{yz(zb):.1f} L {xr(rb):.1f},{yz(zb):.1f} '
                f'L {xr(rt):.1f},{yz(zt):.1f} L {xl(rt):.1f},{yz(zt):.1f} Z" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>')

    parts = []

    # ── ZONA TAGLIENTE (z=0 → L_tagl) ──
    z_fine_tagl = L_tagl

    if elementi_taglio and len(elementi_taglio) >= 2:
        parts.append(_disegna_profilo(
            elementi_taglio, cx, scala, yz, xr, xl,
            z_offset=0, z_scala=1.0,
            fill='#1e3a8a', stroke='#1e40af'))
        z_fine_tagl = max(abs(float(e.get('ey', e.get('sy', 0)))) for e in elementi_taglio)
    else:
        tipo_r = _determina_tipo(tipo, R, angolo_punta_gradi, chamfer_angle_gradi, D)
        if tipo_r == 'BALL':
            arc_r = R * scala
            y_c = yz(R)
            parts.append(f'<path d="M {xl(R):.1f},{y_c:.1f} '
                         f'A {arc_r:.1f},{arc_r:.1f} 0 0 1 {xr(R):.1f},{y_c:.1f} Z" '
                         f'fill="#1e3a8a" stroke="#1e40af" stroke-width="0.8"/>')
            if L_tagl > R + 0.5:
                parts.append(trap(R, L_tagl, D / 2, D / 2, '#1e3a8a', '#1e40af'))
        elif tipo_r == 'BULL' and R > 0:
            cr = min(R, D / 2) * scala
            ri = max((D / 2 - R), 0) * scala
            y_R = yz(R)
            parts.append(f'<path d="M {xl(D/2):.1f},{y_R:.1f} '
                         f'A {cr:.1f},{cr:.1f} 0 0 0 {cx - ri:.1f},{yz(0):.1f} '
                         f'L {cx + ri:.1f},{yz(0):.1f} '
                         f'A {cr:.1f},{cr:.1f} 0 0 0 {xr(D/2):.1f},{y_R:.1f} Z" '
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

    # ── ZONA GAMBO (z_fine_tagl → r_tool) ──
    if elementi_gambo and len(elementi_gambo) >= 2:
        z_max_g = max(abs(float(e.get('ey', e.get('sy', 0)))) for e in elementi_gambo)
        lung_disp = r_tool - z_fine_tagl
        if z_max_g > 0 and lung_disp > 0:
            z_sc = min(1.0, lung_disp / z_max_g)
            parts.append(_disegna_profilo(
                elementi_gambo, cx, scala, yz, xr, xl,
                z_offset=z_fine_tagl, z_scala=z_sc,
                fill='#e5e7eb', stroke='#9ca3af'))
    elif r_tool > z_fine_tagl:
        D_stelo = diam_stelo_mm or D
        if shaft_chamfer_pos_mm and shaft_chamfer_pos_mm > z_fine_tagl:
            z_ch = min(shaft_chamfer_pos_mm, r_tool)
            parts.append(trap(z_fine_tagl, z_ch, D / 2, D / 2, '#e5e7eb', '#9ca3af'))
            if r_tool > z_ch:
                parts.append(trap(z_ch, r_tool, D / 2, D_stelo / 2, '#d1d5db', '#9ca3af'))
        else:
            parts.append(trap(z_fine_tagl, r_tool, D / 2, D_stelo / 2, '#e5e7eb', '#9ca3af'))

    # ── PROLUNGA (r_tool → FP) ──
    if r_ext > 0:
        r_prol = D / 2
        parts.append(trap(r_tool, FP, r_prol, r_prol, '#c4b5fd', '#8b5cf6'))
        if extension_name:
            yl = yz(r_tool + r_ext / 2)
            parts.append(f'<text x="{xr(r_prol) + 4:.0f}" y="{yl + 3:.1f}" '
                         f'font-size="8" fill="#6d28d9" font-family="sans-serif">'
                         f'{extension_name[:22]}</text>')

    # ── ASSE CENTRALE ──
    parts.append(f'<line x1="{cx}" y1="{yz(FP) - 5:.1f}" x2="{cx}" y2="{yz(0) + 5:.1f}" '
                 f'stroke="#ddd" stroke-width="0.5" stroke-dasharray="3,3"/>')

    # ── LINEA FUORI PINZA (SEMPRE) ──
    y_fp = yz(FP)
    parts.append(f'<line x1="{margin:.0f}" y1="{y_fp:.1f}" '
                 f'x2="{xr(r_massimo) + 4:.0f}" y2="{y_fp:.1f}" '
                 f'stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4,3"/>')
    parts.append(f'<text x="{xr(r_massimo) + 7:.0f}" y="{y_fp + 4:.1f}" '
                 f'font-size="10" fill="#f59e0b" font-family="monospace">{FP:.1f}</text>')

    # ── QUOTA ──
    lbl = f'D{D}'
    if R:
        lbl += f'R{R}'
    parts.append(f'<text x="{cx:.0f}" y="{height - 5}" text-anchor="middle" '
                 f'font-size="9" fill="#666" font-family="sans-serif">{lbl}</text>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" style="background:transparent">'
            f'{"".join(parts)}</svg>')


# ═══════════════════════════════════════════════════════════════
# FUNZIONE 2 — Profilo holder da cont2D
# ═══════════════════════════════════════════════════════════════

def _arc_radius(cx, cy, px, py):
    return math.sqrt((cx - px) ** 2 + (cy - py) ** 2)


def render_holder_svg(elementi, width=300, height=400, colore='#6366f1', margin=15):
    """Genera SVG del profilo holder da elementi cont2D.

    Coordinate cont2D: r (raggio), z (asse longitudinale).
    z=0 = lato mandrino (in basso nell'SVG), z cresce verso attacco macchina (in alto).
    Il profilo viene rispecchiato sull'asse Z per simmetria.
    Orientamento SVG: attacco macchina in alto, apertura holder in basso.
    """
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
