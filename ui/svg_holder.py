"""
svg_holder.py — Renderer SVG per profilo fresa e holder.

Orientamento: punta IN BASSO, gambo/attacco IN ALTO.
Coordinate SVG: y=0 in alto, y cresce verso il basso.
"""
import math


# ═══════════════════════════════════════════════════════════════
# FUNZIONE 1 — Profilo fresa parametrico
# ═══════════════════════════════════════════════════════════════

def render_fresa_svg(elementi_profilo=None, elementi_taglio=None,
                     diametro_mm=10, lunghezza_totale_mm=60,
                     lunghezza_tagl_mm=None, lunghezza_utile_mm=None,
                     fuori_pinza_mm=None, diam_stelo_mm=None,
                     raggio_punta_mm=0, tipo='BULL',
                     shaft_chamfer_len=None, shaft_chamfer_pos=None,
                     shaft_chamfer_angle=None,
                     width=200, height=350):
    """Genera SVG del profilo fresa con 3 zone colorate.

    Orientamento: punta in basso, gambo in alto.
    Zone: tagliente (blu scuro) | utile/scarico (blu chiaro) | gambo (grigio)
    """
    D = diametro_mm or 10
    R = raggio_punta_mm or 0
    L_tot = lunghezza_totale_mm or 60
    L_tagl = lunghezza_tagl_mm or L_tot * 0.25
    L_utile = lunghezza_utile_mm or L_tagl
    if L_utile < L_tagl:
        L_utile = L_tagl
    D_stelo = diam_stelo_mm or D
    margin = 20
    label_w = 50  # spazio per label a destra

    # Scala: l'intero utensile deve stare in (height - 2*margin)
    max_r = max(D / 2, D_stelo / 2)
    scala_y = (height - 2 * margin) / L_tot if L_tot > 0 else 1
    scala_x = (width / 2 - margin - label_w / 2) / max_r if max_r > 0 else 1
    scala = min(scala_x, scala_y)
    cx = width / 2  # asse centrale

    def ty(z_from_top):
        """z=0 in alto (gambo), z=L_tot in basso (punta)."""
        return margin + z_from_top * scala

    def tx_r(r):
        return cx + r * scala

    def tx_l(r):
        return cx - r * scala

    # Coordinate Y delle zone (z misurata dall'alto)
    y_top = margin                          # top gambo
    y_chamfer = ty(L_tot - L_utile) if L_utile < L_tot else y_top
    y_utile_top = ty(L_tot - L_utile)       # inizio zona utile
    y_tagl_top = ty(L_tot - L_tagl)         # inizio zona tagliente
    y_bottom = ty(L_tot)                    # punta (in basso)

    r_tagl = D / 2
    r_stelo = D_stelo / 2

    parts = []

    # ── ZONA 3: GAMBO (in alto) ──
    if L_utile < L_tot:
        h_gambo = (L_tot - L_utile) * scala
        if h_gambo > 0.5:
            # Transizione (shaft chamfer) dal gambo all'utile
            if shaft_chamfer_pos and shaft_chamfer_angle and shaft_chamfer_angle > 0:
                # Il chamfer e' a shaft_chamfer_pos mm dalla punta
                y_ch_start = ty(L_tot - shaft_chamfer_pos)
                y_ch_end = y_utile_top
                # Gambo sopra il chamfer
                parts.append(f'<rect x="{tx_l(r_stelo):.1f}" y="{y_top:.1f}" '
                    f'width="{r_stelo*2*scala:.1f}" height="{y_ch_start - y_top:.1f}" '
                    f'fill="#e5e7eb" stroke="#9ca3af" stroke-width="1"/>')
                # Trapezio chamfer
                pts = (f'{tx_l(r_stelo):.1f},{y_ch_start:.1f} '
                       f'{tx_r(r_stelo):.1f},{y_ch_start:.1f} '
                       f'{tx_r(r_tagl):.1f},{y_ch_end:.1f} '
                       f'{tx_l(r_tagl):.1f},{y_ch_end:.1f}')
                parts.append(f'<polygon points="{pts}" fill="#d1d5db" stroke="#9ca3af" stroke-width="1"/>')
            else:
                # Gambo semplice con transizione diretta
                if abs(r_stelo - r_tagl) > 0.1:
                    # Trapezio per la transizione
                    mid_y = y_utile_top - min(3 * scala, (y_utile_top - y_top) * 0.3)
                    pts = (f'{tx_l(r_stelo):.1f},{y_top:.1f} '
                           f'{tx_r(r_stelo):.1f},{y_top:.1f} '
                           f'{tx_r(r_stelo):.1f},{mid_y:.1f} '
                           f'{tx_r(r_tagl):.1f},{y_utile_top:.1f} '
                           f'{tx_l(r_tagl):.1f},{y_utile_top:.1f} '
                           f'{tx_l(r_stelo):.1f},{mid_y:.1f}')
                    parts.append(f'<polygon points="{pts}" fill="#e5e7eb" stroke="#9ca3af" stroke-width="1"/>')
                else:
                    parts.append(f'<rect x="{tx_l(r_stelo):.1f}" y="{y_top:.1f}" '
                        f'width="{r_stelo*2*scala:.1f}" height="{y_utile_top - y_top:.1f}" '
                        f'fill="#e5e7eb" stroke="#9ca3af" stroke-width="1"/>')

    # ── ZONA 2: UTILE/SCARICO (tra tagliente e gambo) ──
    h_utile = (L_utile - L_tagl) * scala
    if h_utile > 0.5:
        parts.append(f'<rect x="{tx_l(r_tagl):.1f}" y="{y_utile_top:.1f}" '
            f'width="{r_tagl*2*scala:.1f}" height="{h_utile:.1f}" '
            f'fill="#bfdbfe" stroke="#60a5fa" stroke-width="1"/>')

    # ── ZONA 1: TAGLIENTE (in basso) ──
    h_tagl = L_tagl * scala
    if tipo == 'BALL':
        # Semicerchio in basso + cilindro sopra
        arc_r = r_tagl * scala
        cyl_h = h_tagl - arc_r
        if cyl_h > 0:
            parts.append(f'<rect x="{tx_l(r_tagl):.1f}" y="{y_tagl_top:.1f}" '
                f'width="{r_tagl*2*scala:.1f}" height="{cyl_h:.1f}" '
                f'fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
        # Arco punta
        arc_top = y_bottom - arc_r
        parts.append(f'<path d="M {tx_l(r_tagl):.1f},{arc_top:.1f} '
            f'A {arc_r:.1f},{arc_r:.1f} 0 0 0 {tx_r(r_tagl):.1f},{arc_top:.1f} '
            f'L {tx_r(r_tagl):.1f},{arc_top:.1f} Z" '
            f'fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
        # Fill il semicerchio separatamente per chiudere
        parts.append(f'<path d="M {tx_l(r_tagl):.1f},{arc_top:.1f} '
            f'A {arc_r:.1f},{arc_r:.1f} 0 1 0 {tx_r(r_tagl):.1f},{arc_top:.1f} Z" '
            f'fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')

    elif tipo == 'BULL':
        # Cilindro con raccordo R agli angoli inferiori
        cr = min(R, r_tagl) * scala
        cyl_h = h_tagl - cr
        if cyl_h > 0:
            parts.append(f'<rect x="{tx_l(r_tagl):.1f}" y="{y_tagl_top:.1f}" '
                f'width="{r_tagl*2*scala:.1f}" height="{cyl_h:.1f}" '
                f'fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
        # Raccordo + base
        y_arc = y_bottom - cr
        r_inner = (r_tagl - R) * scala
        if R > 0 and cr > 1:
            path = (f'M {tx_l(r_tagl):.1f},{y_arc:.1f} '
                    f'L {tx_l(r_tagl):.1f},{y_arc:.1f} '
                    f'A {cr:.1f},{cr:.1f} 0 0 0 {cx - r_inner:.1f},{y_bottom:.1f} '
                    f'L {cx + r_inner:.1f},{y_bottom:.1f} '
                    f'A {cr:.1f},{cr:.1f} 0 0 0 {tx_r(r_tagl):.1f},{y_arc:.1f} Z')
            parts.append(f'<path d="{path}" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
        else:
            parts.append(f'<rect x="{tx_l(r_tagl):.1f}" y="{y_arc:.1f}" '
                f'width="{r_tagl*2*scala:.1f}" height="{cr:.1f}" '
                f'fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')

    elif tipo == 'DRILL':
        # Cono punta + cilindro
        punta_h = r_tagl * 0.6 * scala
        cyl_h = h_tagl - punta_h / scala * scala
        if cyl_h > 0:
            parts.append(f'<rect x="{tx_l(r_tagl):.1f}" y="{y_tagl_top:.1f}" '
                f'width="{r_tagl*2*scala:.1f}" height="{cyl_h:.1f}" '
                f'fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')
        pts = (f'{tx_l(r_tagl):.1f},{y_bottom - punta_h:.1f} '
               f'{tx_r(r_tagl):.1f},{y_bottom - punta_h:.1f} '
               f'{cx:.1f},{y_bottom:.1f}')
        parts.append(f'<polygon points="{pts}" fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')

    else:
        # FLAT / TAP / THREAD / REAM — cilindro semplice
        parts.append(f'<rect x="{tx_l(r_tagl):.1f}" y="{y_tagl_top:.1f}" '
            f'width="{r_tagl*2*scala:.1f}" height="{h_tagl:.1f}" '
            f'fill="#1e3a8a" stroke="#1e40af" stroke-width="1.5"/>')

    # ── ASSE CENTRALE ──
    parts.append(f'<line x1="{cx}" y1="{y_top - 5:.1f}" x2="{cx}" y2="{y_bottom + 5:.1f}" '
        f'stroke="#ddd" stroke-width="0.5" stroke-dasharray="3,3"/>')

    # ── LINEA FUORI PINZA ──
    if fuori_pinza_mm and fuori_pinza_mm < L_tot * 3:
        y_fp = ty(L_tot - fuori_pinza_mm)
        if y_fp > y_top and y_fp < y_bottom:
            parts.append(f'<line x1="{margin:.0f}" y1="{y_fp:.1f}" x2="{width - margin:.0f}" y2="{y_fp:.1f}" '
                f'stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="6,3"/>')
            parts.append(f'<text x="{width - margin + 2:.0f}" y="{y_fp + 4:.1f}" '
                f'font-size="10" fill="#f59e0b" font-family="monospace">{fuori_pinza_mm:.1f}</text>')

    # ── QUOTE A DESTRA ──
    x_q = tx_r(max_r) + 8
    # Diametro
    parts.append(f'<text x="{x_q:.0f}" y="{y_bottom - 5:.1f}" font-size="9" fill="#888" '
        f'font-family="sans-serif">D{D}{"R" + str(R) if R else ""}</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
  viewBox="0 0 {width} {height}" style="background:transparent">
{''.join(parts)}
</svg>'''
    return svg


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
