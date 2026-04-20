"""
svg_holder.py — Renderer SVG per profilo fresa e holder.

Orientamento: punta IN BASSO, gambo/attacco IN ALTO.
Coordinate SVG: y=0 in alto, y cresce verso il basso.
"""
import math


# ═══════════════════════════════════════════════════════════════
# Converter cont2D → SVG path
# ═══════════════════════════════════════════════════════════════

def _cont2d_to_svg_path(elementi, cx, height, margin, scala_r, scala_z):
    """Converte lista elem2D cont2D in path SVG chiuso simmetrico.

    Coordinate cont2D: (r, z) con z=0 in basso (punta fresa).
    Coordinate SVG: x = cx + r*scala_r, y = (height-margin) - z*scala_z.
    """
    if not elementi:
        return None

    def to_svg(r, z):
        return cx + r * scala_r, (height - margin) - z * scala_z

    # Lato destro
    path_right = []
    prev_r, prev_z = None, None
    for e in elementi:
        sx = float(e.get('sx', prev_r or 0))
        sy = float(e.get('sy', prev_z or 0))
        ex = float(e.get('ex', 0))
        ey = float(e.get('ey', 0))
        etype = e.get('type', 'line')
        if prev_r is None:
            x0, y0 = to_svg(sx, sy)
            path_right.append(f'M {x0:.2f},{y0:.2f}')
        ex_svg, ey_svg = to_svg(ex, ey)
        if etype == 'line':
            path_right.append(f'L {ex_svg:.2f},{ey_svg:.2f}')
        elif etype in ('cwarc', 'ccwarc'):
            cx_a = float(e.get('cx', 0))
            cy_a = float(e.get('cy', 0))
            r_arc = math.sqrt((sx - cx_a)**2 + (sy - cy_a)**2) * scala_r
            if r_arc < 0.1:
                r_arc = math.sqrt((ex - cx_a)**2 + (ey - cy_a)**2) * scala_r
            sweep = 0 if etype == 'cwarc' else 1  # Y flip inverts sweep
            path_right.append(f'A {r_arc:.2f},{r_arc:.2f} 0 0 {sweep} {ex_svg:.2f},{ey_svg:.2f}')
        prev_r, prev_z = ex, ey

    # Lato sinistro (specchiato, reversed)
    path_left = []
    for i in range(len(elementi) - 1, -1, -1):
        e = elementi[i]
        sx = float(e.get('sx', 0))
        sy = float(e.get('sy', 0))
        ex = float(e.get('ex', 0))
        ey = float(e.get('ey', 0))
        etype = e.get('type', 'line')
        if i == len(elementi) - 1:
            lx, ly = to_svg(-ex, ey)
            path_left.append(f'L {lx:.2f},{ly:.2f}')
        sx_svg, sy_svg = to_svg(-sx, sy)
        if etype == 'line':
            path_left.append(f'L {sx_svg:.2f},{sy_svg:.2f}')
        elif etype in ('cwarc', 'ccwarc'):
            cx_a = float(e.get('cx', 0))
            cy_a = float(e.get('cy', 0))
            r_arc = math.sqrt((ex - cx_a)**2 + (ey - cy_a)**2) * scala_r
            if r_arc < 0.1:
                r_arc = math.sqrt((sx - cx_a)**2 + (sy - cy_a)**2) * scala_r
            sweep = 1 if etype == 'cwarc' else 0  # reversed + mirrored
            path_left.append(f'A {r_arc:.2f},{r_arc:.2f} 0 0 {sweep} {sx_svg:.2f},{sy_svg:.2f}')

    return ' '.join(path_right) + ' ' + ' '.join(path_left) + ' Z'


# ═══════════════════════════════════════════════════════════════
# FUNZIONE 1 — Profilo fresa completo
# ═══════════════════════════════════════════════════════════════

def render_fresa_svg(
    diametro_mm=10, lunghezza_totale_mm=60,
    lunghezza_tagl_mm=None, lunghezza_utile_mm=None,
    fuori_pinza_mm=None, diam_stelo_mm=None,
    raggio_punta_mm=0, tipo='BULL', angolo_punta_gradi=None,
    shaft_chamfer_len=None, shaft_chamfer_pos=None, shaft_chamfer_angle=None,
    shaft_type=None, collar=0,
    chamfer_angle_gradi=None, chamfer_height_mm=None, disc_height_mm=None,
    reach_tool_mm=None, reach_extension_mm=None,
    extension_name=None, extension_profilo=None, extension_diameter_mm=None,
    d_gola_mm=None, h_gola_mm=None, tip_diameter_mm=None,
    elementi_profilo=None, elementi_gambo=None, elementi_taglio=None,
    alias=None, width=220, height=400):
    """Genera SVG del profilo fresa usando tutti i dati reali dal DB.

    Orientamento: punta in basso, gambo/prolunga in alto.
    Altezza disegnata = fuori_pinza_mm (solo parte che sporge).
    """
    # ── Normalizzazione input ──
    D = diametro_mm or 10
    R = raggio_punta_mm or 0
    L_tagl = lunghezza_tagl_mm or (lunghezza_totale_mm or 60) * 0.25
    L_utile = lunghezza_utile_mm or L_tagl
    if L_utile < L_tagl:
        L_utile = L_tagl
    if shaft_type == 'none' or not diam_stelo_mm or diam_stelo_mm <= 0:
        D_stelo = D
    elif D > 0 and diam_stelo_mm > 0 and D > diam_stelo_mm * 1.2:
        # Fresa a inserti: Dst e' il filetto interno, non il corpo esterno.
        D_stelo = tip_diameter_mm if (tip_diameter_mm and tip_diameter_mm > diam_stelo_mm) else D
    else:
        D_stelo = diam_stelo_mm
    FP = fuori_pinza_mm or lunghezza_totale_mm or 60
    r_ext = reach_extension_mm or 0
    r_tool = reach_tool_mm or FP
    if r_tool <= 0:
        r_tool = FP
    # Gola coerenza
    D_gola = d_gola_mm or 0
    H_gola = h_gola_mm or 0
    if D_gola > 0 and not (0 < D_gola < D):
        D_gola = 0; H_gola = 0
    tip_D = tip_diameter_mm or 0

    # ── Tipo reale dai dati ──
    t = (tipo or '').upper()
    if chamfer_angle_gradi and chamfer_angle_gradi > 0 and t not in ('DRILL',):
        tipo_r = 'CHAMFER'
    elif t == 'DRILL' or (angolo_punta_gradi and angolo_punta_gradi > 0 and R == 0 and t not in ('BULL','BALL','FLAT','REAM','THREAD','TAP','LOLLIPOP')):
        tipo_r = 'DRILL'
    elif t in ('REAM','TAP','THREAD','LOLLIPOP'):
        tipo_r = t
    elif R and D and abs(R - D / 2) < 0.3:
        tipo_r = 'BALL'
    elif R and R > 0:
        tipo_r = 'BULL'
    else:
        tipo_r = t or 'FLAT'

    # ── Scala ──
    margin = 28
    label_w = 55
    cx = (width - label_w) / 2
    H_tot = FP
    r_tagl = D / 2
    r_stelo = D_stelo / 2
    r_max = max(r_tagl, r_stelo, (extension_diameter_mm or D_stelo) / 2)
    if r_max <= 0: r_max = 5
    scala_z = (height - 2 * margin) / H_tot if H_tot > 0 else 1
    scala_r = (cx - margin) / r_max if r_max > 0 else 1
    scala = min(scala_z, scala_r)

    def yz(z_mm): return (height - margin) - z_mm * scala
    def xr(r_mm): return cx + r_mm * scala
    def xl(r_mm): return cx - r_mm * scala

    def trap(zb, zt, rb, rt, fill, stroke, op=1.0):
        """Trapezio simmetrico: z_bottom, z_top, r_bottom, r_top."""
        if zt <= zb or zt <= 0: return ''
        opstr = f' fill-opacity="{op}"' if op < 1 else ''
        return (f'<path d="M {xl(rb):.1f},{yz(zb):.1f} L {xr(rb):.1f},{yz(zb):.1f} '
                f'L {xr(rt):.1f},{yz(zt):.1f} L {xl(rt):.1f},{yz(zt):.1f} Z" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="0.8"{opstr}/>')

    parts = []

    # ── PUNTA (zona tagliente z=0 → L_tagl) ──
    if tipo_r == 'CHAMFER':
        # Cono svasatore: da tip_D/2 in basso a D/2 in alto
        r_tip = max(tip_D / 2, 0.5) if tip_D > 0 else 1
        parts.append(trap(0, L_tagl, r_tip, r_tagl, '#1e3a8a', '#1e40af'))
    elif tipo_r == 'DRILL':
        ang = angolo_punta_gradi or 118
        h_punta = (D / 2) / math.tan(math.radians(ang / 2)) if ang > 0 and ang < 180 else D * 0.3
        h_punta = min(h_punta, L_tagl * 0.8)
        parts.append(trap(0, h_punta, 0.1, r_tagl, '#1e3a8a', '#1e40af'))
        if L_tagl > h_punta:
            parts.append(trap(h_punta, L_tagl, r_tagl, r_tagl, '#1e3a8a', '#1e40af'))
    elif tipo_r == 'BALL':
        arc_r = r_tagl * scala
        y_arc = yz(R)
        parts.append(f'<path d="M {xl(r_tagl):.1f},{y_arc:.1f} A {arc_r:.1f},{arc_r:.1f} 0 0 1 {xr(r_tagl):.1f},{y_arc:.1f} Z" fill="#1e3a8a" stroke="#1e40af" stroke-width="1"/>')
        if L_tagl > R + 0.5:
            parts.append(trap(R, L_tagl, r_tagl, r_tagl, '#1e3a8a', '#1e40af'))
    elif tipo_r == 'BULL' and R > 0:
        cr = min(R, r_tagl) * scala
        ri = max((r_tagl - R), 0) * scala
        y_cr = yz(R)
        if L_tagl > R:
            parts.append(trap(R, L_tagl, r_tagl, r_tagl, '#1e3a8a', '#1e40af'))
        parts.append(f'<path d="M {xl(r_tagl):.1f},{y_cr:.1f} A {cr:.1f},{cr:.1f} 0 0 0 {cx - ri:.1f},{yz(0):.1f} L {cx + ri:.1f},{yz(0):.1f} A {cr:.1f},{cr:.1f} 0 0 0 {xr(r_tagl):.1f},{y_cr:.1f} Z" fill="#1e3a8a" stroke="#1e40af" stroke-width="1"/>')
    else:
        parts.append(trap(0, L_tagl, r_tagl, r_tagl, '#1e3a8a', '#1e40af'))

    # ── GOLA (se presente) ──
    z_post = L_tagl
    if D_gola > 0 and H_gola > 0.5:
        r_gola = D_gola / 2
        z_gola_end = L_tagl + H_gola
        parts.append(trap(L_tagl, L_tagl + H_gola * 0.15, r_tagl, r_gola, '#7c3aed', '#6d28d9', 0.85))
        parts.append(trap(L_tagl + H_gola * 0.15, z_gola_end - H_gola * 0.15, r_gola, r_gola, '#7c3aed', '#6d28d9', 0.85))
        parts.append(trap(z_gola_end - H_gola * 0.15, z_gola_end, r_gola, r_stelo, '#7c3aed', '#6d28d9', 0.85))
        z_post = z_gola_end
    elif L_utile > L_tagl:
        # Zona utile (scaricata)
        r_u = r_tagl - 0.2 if r_tagl > 1 else r_tagl
        parts.append(trap(L_tagl, L_utile, r_u, r_u, '#bfdbfe', '#60a5fa'))
        z_post = L_utile

    # ── CORPO / GAMBO (z_post → z_gambo_end) ──
    is_inserti = D > 0 and D_stelo > 0 and D > D_stelo * 1.2
    z_gambo_end = r_tool if r_ext > 0 else FP
    if z_gambo_end > z_post:
        r_u_eff = r_tagl - 0.2 if r_tagl > 1 else r_tagl
        r_bot = D_gola / 2 if D_gola > 0 else (r_u_eff if L_utile > L_tagl else r_tagl)

        if is_inserti and shaft_chamfer_pos and shaft_chamfer_pos > z_post:
            # Fresa a inserti: corpo largo (D) fino allo smusso, poi si stringe
            z_smusso = min(shaft_chamfer_pos, z_gambo_end)
            r_corpo = r_tagl
            if z_smusso > z_post:
                parts.append(trap(z_post, z_smusso, r_bot, r_corpo, '#e5e7eb', '#9ca3af'))
            if z_gambo_end > z_smusso:
                parts.append(trap(z_smusso, z_gambo_end, r_corpo, r_stelo, '#d1d5db', '#9ca3af'))

        elif shaft_chamfer_pos and shaft_chamfer_pos > z_post:
            # Fresa integrale con shaft chamfer
            z_ch = min(shaft_chamfer_pos, z_gambo_end)
            parts.append(trap(z_post, z_ch, r_bot, r_stelo, '#e5e7eb', '#9ca3af'))
            if z_gambo_end > z_ch:
                parts.append(trap(z_ch, z_gambo_end, r_stelo, r_stelo, '#e5e7eb', '#9ca3af'))

        elif abs(r_bot - r_stelo) > 0.3:
            trans_h = min(3, (z_gambo_end - z_post) * 0.3)
            parts.append(trap(z_post, z_post + trans_h, r_bot, r_stelo, '#d1d5db', '#9ca3af'))
            if z_gambo_end > z_post + trans_h:
                parts.append(trap(z_post + trans_h, z_gambo_end, r_stelo, r_stelo, '#e5e7eb', '#9ca3af'))

        else:
            parts.append(trap(z_post, z_gambo_end, r_stelo, r_stelo, '#e5e7eb', '#9ca3af'))

    # ── PROLUNGA ──
    if r_ext > 0:
        r_p = (extension_diameter_mm or D_stelo) / 2
        if extension_profilo and len(extension_profilo) > 2:
            all_z_e = [abs(float(e.get('ey', e.get('sy', 0)))) for e in extension_profilo]
            max_z_e = max(all_z_e) if all_z_e else r_ext
            if max_z_e <= 0: max_z_e = 1
            def ext_svg(r, z):
                return cx + r * scala, yz(r_tool + z * r_ext / max_z_e)
            pr = []; prev = (None, None)
            for e in extension_profilo:
                sx_e = float(e.get('sx', prev[0] or 0)); sy_e = float(e.get('sy', prev[1] or 0))
                ex_e = float(e.get('ex', 0)); ey_e = float(e.get('ey', 0))
                if prev[0] is None:
                    x0, y0 = ext_svg(sx_e, sy_e); pr.append(f'M {x0:.1f},{y0:.1f}')
                xn, yn = ext_svg(ex_e, ey_e); pr.append(f'L {xn:.1f},{yn:.1f}')
                prev = (ex_e, ey_e)
            pl = []
            for e in reversed(extension_profilo):
                ex_e = float(e.get('ex', 0)); ey_e = float(e.get('ey', 0))
                xm, ym = ext_svg(-ex_e, ey_e); pl.append(f'L {xm:.1f},{ym:.1f}')
            parts.append(f'<path d="{" ".join(pr)} {" ".join(pl)} Z" fill="#c4b5fd" stroke="#8b5cf6" stroke-width="1"/>')
        else:
            parts.append(trap(r_tool, r_tool + r_ext, r_stelo, r_p, '#c4b5fd', '#8b5cf6'))
        if extension_name:
            yl = yz(r_tool + r_ext / 2)
            parts.append(f'<text x="{xr(r_p) + 4:.0f}" y="{yl + 3:.1f}" font-size="8" fill="#8b5cf6" font-family="sans-serif">{extension_name[:25]}</text>')

    # ── ASSE CENTRALE ──
    parts.append(f'<line x1="{cx}" y1="{yz(H_tot) - 5:.1f}" x2="{cx}" y2="{yz(0) + 5:.1f}" stroke="#ddd" stroke-width="0.5" stroke-dasharray="3,3"/>')

    # ── LINEA FUORI PINZA (SEMPRE) ──
    if FP > 0:
        yf = yz(FP)
        if yf >= margin - 5:
            parts.append(f'<line x1="{margin - 5:.0f}" y1="{yf:.1f}" x2="{xr(r_max) + 5:.0f}" y2="{yf:.1f}" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4,3"/>')
            parts.append(f'<text x="{xr(r_max) + 8:.0f}" y="{yf + 4:.1f}" font-size="10" fill="#f59e0b" font-family="monospace">{FP:.1f}</text>')

    # ── QUOTA ──
    lbl = f'D{D}'
    if R: lbl += f'R{R}'
    if tipo_r == 'CHAMFER' and chamfer_angle_gradi: lbl += f' {chamfer_angle_gradi:.0f}deg'
    if tipo_r == 'DRILL' and angolo_punta_gradi: lbl += f' {angolo_punta_gradi:.0f}deg'
    parts.append(f'<text x="{cx}" y="{height - 5}" text-anchor="middle" font-size="9" fill="#666" font-family="sans-serif">{lbl}</text>')

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="background:transparent">{"".join(parts)}</svg>'


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

    max_r = max(all_r) or 1.0
    max_z = max(all_z) or 1.0

    usable_w = (width / 2) - margin
    usable_h = height - 2 * margin
    scale = min(usable_w / max_r, usable_h / max_z)
    svg_cx = width / 2

    def to_x(r):
        return svg_cx + r * scale

    def to_y(z):
        # z=0 in basso, z=max in alto
        return (height - margin) - z * scale

    # Build right-side path
    path_parts = []
    for i, e in enumerate(elementi):
        sr = e.get('sx', 0)
        sz = e.get('sy', 0)
        er = e.get('ex', 0)
        ez = e.get('ey', 0)

        if i == 0:
            path_parts.append(f'M {to_x(sr):.2f},{to_y(sz):.2f}')

        if e['type'] == 'line':
            path_parts.append(f'L {to_x(er):.2f},{to_y(ez):.2f}')
        elif e['type'] in ('cwarc', 'ccwarc'):
            acx_v = e.get('cx', 0)
            acy_v = e.get('cy', 0)
            radius = _arc_radius(acx_v, acy_v, sr, sz) * scale
            if radius < 0.1:
                radius = _arc_radius(acx_v, acy_v, er, ez) * scale
            # In SVG Y is flipped, so sweep direction inverts
            sweep = 0 if e['type'] == 'cwarc' else 1
            path_parts.append(f'A {radius:.2f},{radius:.2f} 0 0 {sweep} {to_x(er):.2f},{to_y(ez):.2f}')

    # Mirror: trace back from end to start on left side
    for i in range(len(elementi) - 1, -1, -1):
        e = elementi[i]
        sr = e.get('sx', 0)
        sz = e.get('sy', 0)
        er = e.get('ex', 0)
        ez = e.get('ey', 0)

        if i == len(elementi) - 1:
            # Connect right end to left end
            path_parts.append(f'L {to_x(-er):.2f},{to_y(ez):.2f}')

        if e['type'] == 'line':
            path_parts.append(f'L {to_x(-sr):.2f},{to_y(sz):.2f}')
        elif e['type'] in ('cwarc', 'ccwarc'):
            acx_v = e.get('cx', 0)
            acy_v = e.get('cy', 0)
            radius = _arc_radius(acx_v, acy_v, sr, sz) * scale
            if radius < 0.1:
                radius = _arc_radius(acx_v, acy_v, er, ez) * scale
            # Reversed direction + mirror
            sweep = 1 if e['type'] == 'cwarc' else 0
            path_parts.append(f'A {radius:.2f},{radius:.2f} 0 0 {sweep} {to_x(-sr):.2f},{to_y(sz):.2f}')

    path_parts.append('Z')
    d = ' '.join(path_parts)

    # Asse centrale
    y1 = to_y(max_z) - 5
    y2 = to_y(0) + 5

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
  viewBox="0 0 {width} {height}" style="background:transparent">
  <line x1="{svg_cx}" y1="{y1:.1f}" x2="{svg_cx}" y2="{y2:.1f}"
    stroke="#ddd" stroke-width="0.5" stroke-dasharray="4,3"/>
  <path d="{d}" fill="{colore}" fill-opacity="0.2" stroke="#4f46e5" stroke-width="1.5"/>
</svg>'''
    return svg
