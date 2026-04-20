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
    # path_sx: lista di tuple (tipo, x, y [, r_arc, sweep]) nell'ordine di visita
    path_sx = []
    prev_r, prev_z = None, None

    for i, e in enumerate(elementi):
        etype = e.get('type', 'line')
        ex_raw = float(e.get('ex', 0))
        ey = float(e.get('ey', 0))
        ex = abs(ex_raw)

        if i == 0:
            sx_raw = float(e.get('sx', ex_raw))
            sy = float(e.get('sy', ey))
            sx = abs(sx_raw)
            path_dx.append(f'M {to_xr(sx):.1f},{to_y(sy):.1f}')
            path_sx.append(('M', to_xl(sx), to_y(sy)))
            prev_r, prev_z = sx, sy

        x1 = to_xr(ex)
        y1 = to_y(ey)

        if etype == 'line':
            path_dx.append(f'L {x1:.1f},{y1:.1f}')
            path_sx.append(('L', to_xl(ex), y1))
        elif etype in ('cwarc', 'ccwarc'):
            cx_a = abs(float(e.get('cx', 0)))
            cy_a = float(e.get('cy', 0))
            r_arc = math.sqrt((prev_r - cx_a)**2 + (prev_z - cy_a)**2) * scala
            if r_arc < 0.1:
                r_arc = math.sqrt((ex - cx_a)**2 + (ey - cy_a)**2) * scala
            sweep_dx = 0 if etype == 'cwarc' else 1
            sweep_sx = 1 if etype == 'cwarc' else 0
            path_dx.append(f'A {r_arc:.2f},{r_arc:.2f} 0 0 {sweep_dx} {x1:.1f},{y1:.1f}')
            path_sx.append(('A', r_arc, sweep_sx, to_xl(ex), y1))

        prev_r, prev_z = ex, ey

    # Chiudi: dall'ultimo punto dx → ultimo punto sx, poi percorri sx al contrario
    sx_parts = []
    # Connetti ultimo punto dx al corrispondente punto sx (ultimo della lista)
    last_item = path_sx[-1]
    if last_item[0] == 'L':
        sx_parts.append(f'L {last_item[1]:.1f},{last_item[2]:.1f}')
    elif last_item[0] == 'A':
        sx_parts.append(f'L {last_item[3]:.1f},{last_item[4]:.1f}')

    # Percorri in ordine inverso (dall'alto verso il basso sul lato sinistro)
    for item in reversed(path_sx[1:-1]):
        if item[0] == 'L':
            sx_parts.append(f'L {item[1]:.1f},{item[2]:.1f}')
        elif item[0] == 'A':
            # Inverti sweep per il percorso di ritorno
            sweep_inv = 1 - item[2]
            sx_parts.append(f'A {item[1]:.2f},{item[1]:.2f} 0 0 {sweep_inv} {item[3]:.1f},{item[4]:.1f}')

    # Chiudi al primo punto sinistro
    first_sx = path_sx[0]
    sx_parts.append(f'L {first_sx[1]:.1f},{first_sx[2]:.1f}')

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

    # Raggio massimo: sempre D/2 (il tagliente e' sempre largo D).
    # I profili freeShaft/freeTip possono avere r < D/2 (gambo interno),
    # ma la scala visiva e' basata sul diametro del tagliente.
    r_massimo = D / 2.0

    # Scala su r_tool (non FP): la sfera risulta visibile
    H_tot = r_tool if r_tool > 0 else FP
    scala_z = (height - 2 * margin) / H_tot if H_tot > 0 else 1
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

    # freeTip solo per tipi speciali (LOLLIPOP, CHAMFER, ecc.)
    # Per BULL/BALL/FLAT/DRILL standard il freeTip descrive la geometria inserto, non il profilo laterale
    tipo_r_tagl = _determina_tipo(tipo, R, angolo_punta_gradi, chamfer_angle_gradi, D)
    usa_freetip = (elementi_taglio and len(elementi_taglio) >= 2
                   and tipo_r_tagl not in ('BULL', 'BALL', 'FLAT', 'DRILL', 'REAM', 'TAP', 'THREAD'))

    if usa_freetip:
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
            y_0 = yz(0)
            parts.append(f'<path d="M {xr(D/2):.1f},{y_R:.1f} '
                         f'A {cr:.1f},{cr:.1f} 0 0 1 {cx + ri:.1f},{y_0:.1f} '
                         f'L {cx - ri:.1f},{y_0:.1f} '
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

    # ── ZONA GAMBO (z_fine_tagl → r_tool) ──
    # BALL: non usare freeShaft (copre la sfera — descrive l'intero tool)
    tipo_r_gambo = _determina_tipo(tipo, R, angolo_punta_gradi, chamfer_angle_gradi, D)
    usa_freeshaft = (elementi_gambo and len(elementi_gambo) >= 2
                     and tipo_r_gambo != 'BALL')
    if usa_freeshaft:
        # Tronca freeShaft a z <= r_tool (z > r_tool = vite dentro holder)
        elementi_gambo_troncati = []
        for e in elementi_gambo:
            ez = abs(float(e.get('ey', 0)))
            if ez <= r_tool:
                elementi_gambo_troncati.append(e)
            else:
                prev_e = elementi_gambo_troncati[-1] if elementi_gambo_troncati else e
                prev_z = abs(float(prev_e.get('ey', 0)))
                prev_r = abs(float(prev_e.get('ex', 0)))
                curr_r = abs(float(e.get('ex', 0)))
                curr_z = ez
                if curr_z > prev_z:
                    t = (r_tool - prev_z) / (curr_z - prev_z)
                    r_interp = prev_r + t * (curr_r - prev_r)
                    elementi_gambo_troncati.append({
                        'type': 'line',
                        'sx': str(prev_r), 'sy': str(prev_z),
                        'ex': str(r_interp), 'ey': str(r_tool)
                    })
                break
        if elementi_gambo_troncati:
            parts.append(_disegna_profilo(
                elementi_gambo_troncati, cx, scala, yz, xr, xl,
                z_offset=0, z_scala=1.0,
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
    y_top_asse = max(margin - 5, yz(FP))
    parts.append(f'<line x1="{cx}" y1="{y_top_asse:.1f}" x2="{cx}" y2="{yz(0) + 5:.1f}" '
                 f'stroke="#ddd" stroke-width="0.5" stroke-dasharray="3,3"/>')

    # ── LINEA FUORI PINZA (SEMPRE) ──
    y_fp = max(margin - 3, yz(FP))
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
