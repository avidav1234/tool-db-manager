"""
svg_profilo.py — Genera profilo SVG 2D di utensile + holder
Asse verticale, punta in basso.
Nessuna libreria esterna — SVG puro.
"""


def genera_svg_profilo(u, segmenti=None):
    """
    Genera SVG inline del profilo utensile.
    u: dict con campi utensile (diametro_mm, raggio_punta_mm, lunghezza_totale_mm, ecc.)
    segmenti: lista di dict portautensile_segmento [{numero_segmento, diametro_inf_mm, diametro_sup_mm, lunghezza_mm}]
    Ritorna stringa SVG.
    """
    if not segmenti:
        segmenti = []

    # Parametri utensile
    D = float(u.get('diametro_mm') or 0)
    R = float(u.get('raggio_punta_mm') or 0)
    L_tot = float(u.get('lunghezza_totale_mm') or 0)
    L_tagl = float(u.get('lunghezza_tagl_mm') or 0)
    fuori_pinza = float(u.get('fuori_pinza_mm') or 0)
    lungh_presa = float(u.get('lungh_presa_mm') or 0)
    D_stelo = float(u.get('diam_stelo_mm') or D * 0.8)
    tipo = u.get('tipo', 'FLAT')
    gage_length = float(u.get('gage_length_mm') or 0)

    if D <= 0 or L_tot <= 0:
        return '<svg width="200" height="100"><text x="10" y="50" fill="#999" font-size="12">Dati geometrici insufficienti</text></svg>'

    # ── Dimensioni canvas ──
    W = 340
    margin_left = 50
    margin_right = 100  # spazio per quote
    margin_top = 30
    margin_bottom = 30
    draw_w = W - margin_left - margin_right

    # Trova diametro max (utensile o holder) per scala
    max_d = D
    for s in segmenti:
        d = max(float(s.get('diametro_inf_mm') or 0), float(s.get('diametro_sup_mm') or 0))
        if d > max_d:
            max_d = d
    if D_stelo > max_d:
        max_d = D_stelo

    # Altezza totale da disegnare
    total_h = fuori_pinza if fuori_pinza > 0 else L_tot
    holder_h = sum(float(s.get('lunghezza_mm') or 0) for s in segmenti)
    draw_total_h = total_h + holder_h

    if draw_total_h <= 0:
        draw_total_h = L_tot

    H = 500
    draw_h = H - margin_top - margin_bottom

    # Scale: pixel per mm
    scale_x = draw_w / (max_d * 1.2)
    scale_y = draw_h / draw_total_h
    scale = min(scale_x, scale_y)

    # Ricalcola H in base alla scala
    H = int(draw_total_h * scale + margin_top + margin_bottom)
    H = max(H, 200)

    cx = margin_left + draw_w / 2  # centro X

    def x_left(diam):
        return cx - (diam / 2) * scale

    def x_right(diam):
        return cx + (diam / 2) * scale

    # Y: punta in basso, holder in alto
    y_bottom = H - margin_bottom  # punta
    y_top = margin_top  # top holder

    def y_at(mm_from_tip):
        return y_bottom - mm_from_tip * scale

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
                 f'viewBox="0 0 {W} {H}" style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px">')

    # ── Asse centrale (tratteggiato) ──
    parts.append(f'<line x1="{cx}" y1="{y_top-10}" x2="{cx}" y2="{y_bottom+10}" '
                 f'stroke="#ddd" stroke-width="0.5" stroke-dasharray="4,4"/>')

    # ══════════════════════════════════════════════════════════════
    # ZONA 1: PUNTA (colore per tipo)
    # ══════════════════════════════════════════════════════════════
    tip_color = {
        'BALL': '#3b82f6', 'FLAT': '#10b981', 'BULL': '#8b5cf6',
        'DRILL': '#f59e0b', 'TAP': '#ef4444', 'REAM': '#06b6d4',
        'THREAD': '#ec4899', 'SPOT': '#f97316', 'FORM': '#6366f1',
    }.get(tipo, '#64748b')

    tip_h = L_tagl if L_tagl > 0 else min(D * 2, L_tot * 0.3)

    if tipo == 'BALL':
        # Semicerchio + cilindro
        r_px = (D / 2) * scale
        cy_ball = y_at(D / 2)
        # Semicerchio (punta) — sweep=0: arco verso il basso (punta della sfera in basso)
        parts.append(f'<path d="M {x_left(D)} {cy_ball} A {r_px} {r_px} 0 0 0 {x_right(D)} {cy_ball}" '
                     f'fill="{tip_color}" fill-opacity="0.9" stroke="{tip_color}" stroke-width="1.5"/>')
        # Corpo cilindrico sopra il semicerchio
        if tip_h > D / 2:
            y_top_tagl = y_at(tip_h)
            parts.append(f'<rect x="{x_left(D)}" y="{y_top_tagl}" width="{D*scale}" height="{(tip_h - D/2)*scale}" '
                         f'fill="{tip_color}" fill-opacity="0.9" stroke="{tip_color}" stroke-width="1.5"/>')

    elif tipo == 'DRILL':
        # Triangolo punta + cilindro
        angle = float(u.get('angolo_punta_gradi') or 118)
        import math
        tip_depth = (D / 2) / math.tan(math.radians(angle / 2))
        y_tip_top = y_at(tip_depth)
        parts.append(f'<polygon points="{cx},{y_bottom} {x_left(D)},{y_tip_top} {x_right(D)},{y_tip_top}" '
                     f'fill="{tip_color}" fill-opacity="0.15" stroke="{tip_color}" stroke-width="1.5"/>')
        if tip_h > tip_depth:
            y_top_tagl = y_at(tip_h)
            parts.append(f'<rect x="{x_left(D)}" y="{y_top_tagl}" width="{D*scale}" height="{(tip_h-tip_depth)*scale}" '
                         f'fill="{tip_color}" fill-opacity="0.15" stroke="{tip_color}" stroke-width="1.5"/>')

    elif tipo == 'BULL':
        # Rettangolo con angoli arrotondati
        y_top_tagl = y_at(tip_h)
        r_corner = min(R * scale, D * scale / 2)
        parts.append(f'<rect x="{x_left(D)}" y="{y_top_tagl}" width="{D*scale}" height="{tip_h*scale}" '
                     f'rx="{r_corner}" ry="{r_corner}" '
                     f'fill="{tip_color}" fill-opacity="0.15" stroke="{tip_color}" stroke-width="1.5"/>')

    else:  # FLAT, THREAD, TAP, REAM, SPOT, FORM
        y_top_tagl = y_at(tip_h)
        parts.append(f'<rect x="{x_left(D)}" y="{y_top_tagl}" width="{D*scale}" height="{tip_h*scale}" '
                     f'fill="{tip_color}" fill-opacity="0.15" stroke="{tip_color}" stroke-width="1.5"/>')

    # ══════════════════════════════════════════════════════════════
    # ZONA 2: STELO (grigio chiaro)
    # ══════════════════════════════════════════════════════════════
    stelo_start = tip_h
    stelo_end = fuori_pinza if fuori_pinza > 0 else L_tot
    if stelo_end > stelo_start and D_stelo > 0:
        y_s_top = y_at(stelo_end)
        y_s_bot = y_at(stelo_start)
        # Transizione conica da D a D_stelo
        if abs(D - D_stelo) > 0.5:
            cone_h = min(D, stelo_end - stelo_start) * 0.3
            y_cone = y_at(stelo_start + cone_h)
            parts.append(f'<polygon points="{x_left(D)},{y_s_bot} {x_right(D)},{y_s_bot} '
                         f'{x_right(D_stelo)},{y_cone} {x_left(D_stelo)},{y_cone}" '
                         f'fill="#cbd5e1" fill-opacity="0.4" stroke="#94a3b8" stroke-width="1"/>')
            parts.append(f'<rect x="{x_left(D_stelo)}" y="{y_s_top}" '
                         f'width="{D_stelo*scale}" height="{(stelo_end - stelo_start - cone_h)*scale}" '
                         f'fill="#cbd5e1" fill-opacity="0.4" stroke="#94a3b8" stroke-width="1"/>')
        else:
            parts.append(f'<rect x="{x_left(D_stelo)}" y="{y_s_top}" '
                         f'width="{D_stelo*scale}" height="{(stelo_end-stelo_start)*scale}" '
                         f'fill="#cbd5e1" fill-opacity="0.4" stroke="#94a3b8" stroke-width="1"/>')

    # ══════════════════════════════════════════════════════════════
    # ZONA 3: HOLDER — profilo reale da polyline raw, fallback a segmenti
    # ══════════════════════════════════════════════════════════════
    punti_raw = []
    raw_json = u.get('profilo_punti_json')
    if raw_json:
        try:
            import json as _json
            punti_raw = _json.loads(raw_json)
        except Exception:
            punti_raw = []

    y_holder_base = fuori_pinza if fuori_pinza > 0 else L_tot

    if punti_raw and len(punti_raw) >= 2:
        # Usa punti raw: ogni punto (r, z) è cumulativo dalla punta
        y_cursor = y_holder_base
        prev_r = None
        prev_z = 0.0
        for i, (r, z) in enumerate(punti_raw):
            if i == 0:
                # Primo punto: cilindro da naso a primo z (diametro=r*2)
                d = r * 2
                l_seg = z
                y_seg_top = y_at(y_cursor + l_seg)
                parts.append(f'<rect x="{x_left(d)}" y="{y_seg_top}" '
                             f'width="{d*scale}" height="{l_seg*scale}" '
                             f'fill="#475569" fill-opacity="0.25" stroke="#1e293b" stroke-width="1"/>')
                y_cursor += l_seg
            else:
                l_seg = z - prev_z
                if l_seg <= 0.01:
                    prev_r, prev_z = r, z
                    continue
                d_inf = prev_r * 2
                d_sup = r * 2
                y_seg_bot = y_at(y_cursor)
                y_seg_top = y_at(y_cursor + l_seg)
                if abs(d_inf - d_sup) < 0.05:
                    parts.append(f'<rect x="{x_left(d_inf)}" y="{y_seg_top}" '
                                 f'width="{d_inf*scale}" height="{l_seg*scale}" '
                                 f'fill="#475569" fill-opacity="0.25" stroke="#1e293b" stroke-width="1"/>')
                else:
                    parts.append(f'<polygon points='
                                 f'"{x_left(d_inf)},{y_seg_bot} {x_right(d_inf)},{y_seg_bot} '
                                 f'{x_right(d_sup)},{y_seg_top} {x_left(d_sup)},{y_seg_top}" '
                                 f'fill="#475569" fill-opacity="0.25" stroke="#1e293b" stroke-width="1"/>')
                y_cursor += l_seg
            prev_r, prev_z = r, z
    elif segmenti:
        # Fallback: usa segmenti collassati
        y_cursor = y_holder_base
        for s in segmenti:
            d_inf = float(s.get('diametro_inf_mm') or 0)
            d_sup = float(s.get('diametro_sup_mm') or 0)
            h_seg = float(s.get('lunghezza_mm') or 0)
            if h_seg <= 0:
                continue
            y_seg_bot = y_at(y_cursor)
            y_seg_top = y_at(y_cursor + h_seg)
            if abs(d_inf - d_sup) < 0.1:
                parts.append(f'<rect x="{x_left(d_inf)}" y="{y_seg_top}" '
                             f'width="{d_inf*scale}" height="{h_seg*scale}" '
                             f'fill="#475569" fill-opacity="0.25" stroke="#475569" stroke-width="1.2"/>')
            else:
                parts.append(f'<polygon points='
                             f'"{x_left(d_inf)},{y_seg_bot} {x_right(d_inf)},{y_seg_bot} '
                             f'{x_right(d_sup)},{y_seg_top} {x_left(d_sup)},{y_seg_top}" '
                             f'fill="#475569" fill-opacity="0.25" stroke="#475569" stroke-width="1.2"/>')
            y_cursor += h_seg

    # ══════════════════════════════════════════════════════════════
    # LINEA FUORI PINZA (tratteggiata rossa)
    # ══════════════════════════════════════════════════════════════
    if fuori_pinza > 0:
        y_fp = y_at(fuori_pinza)
        parts.append(f'<line x1="{margin_left-10}" y1="{y_fp}" x2="{cx + max_d*scale/2 + 10}" y2="{y_fp}" '
                     f'stroke="#ef4444" stroke-width="1" stroke-dasharray="6,3"/>')
        parts.append(f'<text x="{margin_left-12}" y="{y_fp-4}" fill="#ef4444" font-size="9" '
                     f'text-anchor="end" font-weight="600">FP</text>')

    # ══════════════════════════════════════════════════════════════
    # QUOTE (a destra)
    # ══════════════════════════════════════════════════════════════
    qx = cx + max_d * scale / 2 + 15  # x delle linee di quota

    def _quota(y1, y2, label, offset=0):
        xq = qx + offset
        mid_y = (y1 + y2) / 2
        parts.append(f'<line x1="{xq}" y1="{y1}" x2="{xq}" y2="{y2}" stroke="#64748b" stroke-width="0.8"/>')
        parts.append(f'<line x1="{xq-3}" y1="{y1}" x2="{xq+3}" y2="{y1}" stroke="#64748b" stroke-width="0.8"/>')
        parts.append(f'<line x1="{xq-3}" y1="{y2}" x2="{xq+3}" y2="{y2}" stroke="#64748b" stroke-width="0.8"/>')
        parts.append(f'<text x="{xq+5}" y="{mid_y+3}" fill="#475569" font-size="9" font-family="monospace">{label}</text>')

    # Quota diametro
    parts.append(f'<text x="{cx}" y="{y_bottom+18}" fill="#475569" font-size="10" '
                 f'text-anchor="middle" font-family="monospace">D={D}</text>')

    # Quota lunghezza totale
    if L_tot > 0:
        _quota(y_at(0), y_at(L_tot), f'L={L_tot}', 0)

    # Quota fuori pinza
    if fuori_pinza > 0 and fuori_pinza != L_tot:
        _quota(y_at(0), y_at(fuori_pinza), f'FP={fuori_pinza}', 25)

    # Quota gage_length
    if gage_length > 0:
        _quota(y_at(0), y_at(min(gage_length, draw_total_h)), f'GL={gage_length}', 50)

    # Quota raggio (se non zero)
    if R > 0 and tipo != 'FLAT':
        parts.append(f'<text x="{cx}" y="{y_bottom+28}" fill="{tip_color}" font-size="9" '
                     f'text-anchor="middle" font-family="monospace">R={R}</text>')

    # ── Legenda tipo ──
    parts.append(f'<text x="{W/2}" y="16" fill="#475569" font-size="11" text-anchor="middle" '
                 f'font-weight="600">{u.get("alias") or u.get("codice_interno","")}</text>')

    parts.append('</svg>')
    return '\n'.join(parts)
