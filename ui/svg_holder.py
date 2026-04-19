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
# FUNZIONE 1 — Profilo fresa (cont2D o fallback parametrico)
# ═══════════════════════════════════════════════════════════════

def render_fresa_svg(elementi_profilo=None, elementi_taglio=None,
                     diametro_mm=10, lunghezza_totale_mm=60,
                     lunghezza_tagl_mm=None, lunghezza_utile_mm=None,
                     fuori_pinza_mm=None, diam_stelo_mm=None,
                     raggio_punta_mm=0, tipo='BULL',
                     shaft_chamfer_len=None, shaft_chamfer_pos=None,
                     shaft_chamfer_angle=None,
                     reach_tool_mm=None, reach_extension_mm=None, extension_name=None,
                     d_gola_mm=None, h_gola_mm=None,
                     width=220, height=400):
    """Genera SVG del profilo fresa con zone colorate + prolunga + gola.

    Orientamento: punta in basso, gambo/prolunga in alto.
    Altezza disegnata = fuori_pinza_mm (solo parte che sporge dal holder).
    """
    D = diametro_mm or 10
    R = raggio_punta_mm or 0
    L_tagl = lunghezza_tagl_mm or (lunghezza_totale_mm or 60) * 0.25
    L_utile = lunghezza_utile_mm or L_tagl
    if L_utile < L_tagl:
        L_utile = L_tagl
    D_stelo = diam_stelo_mm or D
    FP = fuori_pinza_mm or lunghezza_totale_mm or 60
    r_ext = reach_extension_mm or 0
    r_tool = reach_tool_mm or FP
    D_gola = d_gola_mm or 0
    H_gola = h_gola_mm or 0

    # Altezza totale disegnata = fuori_pinza (solo parte che sporge)
    H_tot = FP
    margin = 25
    label_w = 55
    max_r = max(D / 2, D_stelo / 2, D * 0.65 if r_ext > 0 else 0)
    if max_r <= 0:
        max_r = 5

    scala = min((height - 2 * margin) / H_tot if H_tot > 0 else 1,
                (width / 2 - margin - label_w / 2) / max_r)
    cx = (width - label_w) / 2

    def ty(z_mm):
        """z=0 punta (basso), z=H_tot sommita (alto). Ritorna y SVG."""
        return (height - margin) - z_mm * scala

    def txr(r): return cx + r * scala
    def txl(r): return cx - r * scala

    r_tagl = D / 2
    r_stelo = D_stelo / 2
    r_gola = D_gola / 2 if D_gola > 0 else 0
    r_prolunga = D * 0.65 if r_ext > 0 else 0

    parts = []

    # ═══ BRANCH A: cont2D reale per la fresa ═══
    use_cont2d = elementi_profilo and len(elementi_profilo) > 3

    if use_cont2d:
        all_r_c = [abs(float(e.get('ex', e.get('sx', 0)))) for e in elementi_profilo]
        all_z_c = [abs(float(e.get('ey', e.get('sy', 0)))) for e in elementi_profilo]
        max_r_c = max(all_r_c) if all_r_c else r_tagl
        max_z_c = max(all_z_c) if all_z_c else r_tool
        if max_r_c <= 0: max_r_c = 1
        if max_z_c <= 0: max_z_c = 1
        # Riscala per far stare il cont2D nella zona fresa (da 0 a r_tool)
        sc_r = (width / 2 - margin - label_w / 2) / max(max_r_c, r_prolunga or 1)
        sc_z = (r_tool * scala) / max_z_c if max_z_c > 0 else scala
        path = _cont2d_to_svg_path(elementi_profilo, cx, height, margin, sc_r, sc_z)
        if path:
            parts.append(f'<path d="{path}" fill="#1e3a8a" fill-opacity="0.2" stroke="#1e3a8a" stroke-width="1.2"/>')
    else:
        # ═══ BRANCH B: parametrico con zone ═══
        # Zone dal basso verso l'alto

        # Z1: Tagliente (0 → L_tagl)
        h1 = L_tagl * scala
        y1_top = ty(L_tagl)
        y1_bot = ty(0)
        if tipo == 'BALL':
            arc_r = r_tagl * scala
            cyl_h = h1 - arc_r
            if cyl_h > 0:
                parts.append(f'<rect x="{txl(r_tagl):.1f}" y="{y1_top:.1f}" width="{r_tagl*2*scala:.1f}" height="{cyl_h:.1f}" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
            parts.append(f'<path d="M {txl(r_tagl):.1f},{y1_bot - arc_r:.1f} A {arc_r:.1f},{arc_r:.1f} 0 1 0 {txr(r_tagl):.1f},{y1_bot - arc_r:.1f} Z" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
        elif tipo == 'BULL' and R > 0:
            cr = min(R, r_tagl) * scala
            cyl_h = h1 - cr
            if cyl_h > 0:
                parts.append(f'<rect x="{txl(r_tagl):.1f}" y="{y1_top:.1f}" width="{r_tagl*2*scala:.1f}" height="{cyl_h:.1f}" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
            ri = (r_tagl - R) * scala
            parts.append(f'<path d="M {txl(r_tagl):.1f},{y1_bot - cr:.1f} A {cr:.1f},{cr:.1f} 0 0 0 {cx - ri:.1f},{y1_bot:.1f} L {cx + ri:.1f},{y1_bot:.1f} A {cr:.1f},{cr:.1f} 0 0 0 {txr(r_tagl):.1f},{y1_bot - cr:.1f} Z" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
        elif tipo == 'DRILL':
            ph = r_tagl * 0.6 * scala
            ch = h1 - ph
            if ch > 0:
                parts.append(f'<rect x="{txl(r_tagl):.1f}" y="{y1_top:.1f}" width="{r_tagl*2*scala:.1f}" height="{ch:.1f}" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
            parts.append(f'<polygon points="{txl(r_tagl):.1f},{y1_bot - ph:.1f} {txr(r_tagl):.1f},{y1_bot - ph:.1f} {cx:.1f},{y1_bot:.1f}" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
        else:
            parts.append(f'<rect x="{txl(r_tagl):.1f}" y="{y1_top:.1f}" width="{r_tagl*2*scala:.1f}" height="{h1:.1f}" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')

        # Z2: Gola (L_tagl → L_tagl+H_gola)
        z_after_tagl = L_tagl
        if D_gola > 0 and H_gola > 0.5:
            h_g = H_gola * scala
            y_g_top = ty(L_tagl + H_gola)
            y_g_bot = ty(L_tagl)
            # Trapezio: da r_tagl in basso a r_gola in mezzo a r_tagl/r_stelo in alto
            pts_g = (f'{txl(r_tagl):.1f},{y_g_bot:.1f} {txr(r_tagl):.1f},{y_g_bot:.1f} '
                     f'{txr(r_gola):.1f},{y_g_top + h_g*0.2:.1f} {txr(r_gola):.1f},{y_g_top:.1f} '
                     f'{txl(r_gola):.1f},{y_g_top:.1f} {txl(r_gola):.1f},{y_g_top + h_g*0.2:.1f}')
            parts.append(f'<polygon points="{pts_g}" fill="#7c3aed" fill-opacity="0.25" stroke="#6d28d9" stroke-width="1"/>')
            z_after_tagl = L_tagl + H_gola

        # Z3: Utile/scarico (after gola → L_utile)
        if L_utile > z_after_tagl:
            h_u = (L_utile - z_after_tagl) * scala
            y_u = ty(L_utile)
            r_u = r_tagl - 0.25 if r_tagl > 1 else r_tagl
            parts.append(f'<rect x="{txl(r_u):.1f}" y="{y_u:.1f}" width="{r_u*2*scala:.1f}" height="{h_u:.1f}" fill="#bfdbfe" stroke="#60a5fa" stroke-width="1"/>')

        # Z4: Gambo (L_utile → r_tool)
        z_gambo_start = max(L_utile, z_after_tagl)
        z_gambo_end = r_tool if r_ext > 0 else FP
        if z_gambo_end > z_gambo_start:
            h_gam = (z_gambo_end - z_gambo_start) * scala
            y_gam = ty(z_gambo_end)
            if abs(r_stelo - r_tagl) > 0.3 and shaft_chamfer_pos:
                # Transizione conica
                z_ch = min(shaft_chamfer_pos, z_gambo_end)
                y_ch = ty(z_ch)
                y_gs = ty(z_gambo_start)
                pts_t = (f'{txl(r_tagl):.1f},{y_gs:.1f} {txr(r_tagl):.1f},{y_gs:.1f} '
                         f'{txr(r_stelo):.1f},{y_ch:.1f} {txr(r_stelo):.1f},{y_gam:.1f} '
                         f'{txl(r_stelo):.1f},{y_gam:.1f} {txl(r_stelo):.1f},{y_ch:.1f}')
                parts.append(f'<polygon points="{pts_t}" fill="#e5e7eb" stroke="#9ca3af" stroke-width="1"/>')
            else:
                parts.append(f'<rect x="{txl(r_stelo):.1f}" y="{y_gam:.1f}" width="{r_stelo*2*scala:.1f}" height="{h_gam:.1f}" fill="#e5e7eb" stroke="#9ca3af" stroke-width="1"/>')

    # Z5: Prolunga (r_tool → r_tool+r_ext)
    if r_ext > 0:
        y_ext_top = ty(r_tool + r_ext)
        y_ext_bot = ty(r_tool)
        h_ext = r_ext * scala
        # Raccordo breve in basso + cilindro + raccordo in alto
        raccordo = min(2 * scala, h_ext * 0.1)
        parts.append(f'<polygon points="{txl(r_stelo):.1f},{y_ext_bot:.1f} {txr(r_stelo):.1f},{y_ext_bot:.1f} '
            f'{txr(r_prolunga):.1f},{y_ext_bot - raccordo:.1f} {txr(r_prolunga):.1f},{y_ext_top + raccordo:.1f} '
            f'{txr(r_stelo):.1f},{y_ext_top:.1f} {txl(r_stelo):.1f},{y_ext_top:.1f} '
            f'{txl(r_prolunga):.1f},{y_ext_top + raccordo:.1f} {txl(r_prolunga):.1f},{y_ext_bot - raccordo:.1f}" '
            f'fill="#c4b5fd" stroke="#8b5cf6" stroke-width="1"/>')
        # Label prolunga
        if extension_name:
            y_lbl = (y_ext_top + y_ext_bot) / 2
            parts.append(f'<text x="{txr(r_prolunga) + 4:.0f}" y="{y_lbl + 3:.1f}" '
                f'font-size="8" fill="#8b5cf6" font-family="sans-serif">{extension_name[:25]}</text>')

    # ═══ ASSE CENTRALE ═══
    parts.append(f'<line x1="{cx}" y1="{ty(H_tot) - 5:.1f}" x2="{cx}" y2="{ty(0) + 5:.1f}" '
        f'stroke="#ddd" stroke-width="0.5" stroke-dasharray="3,3"/>')

    # ═══ LINEA FUORI PINZA (SEMPRE) ═══
    if FP > 0:
        y_fp = ty(FP)
        if y_fp >= margin - 5:
            parts.append(f'<line x1="{margin - 5:.0f}" y1="{y_fp:.1f}" x2="{txr(max_r) + 5:.0f}" y2="{y_fp:.1f}" '
                f'stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4,3"/>')
            parts.append(f'<text x="{txr(max_r) + 8:.0f}" y="{y_fp + 4:.1f}" '
                f'font-size="10" fill="#f59e0b" font-family="monospace">{FP:.1f}</text>')

    # ═══ QUOTA D/R ═══
    parts.append(f'<text x="{margin:.0f}" y="{height - 5:.0f}" font-size="9" fill="#888" '
        f'font-family="sans-serif">D{D}{"R" + str(R) if R else ""}</text>')

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
