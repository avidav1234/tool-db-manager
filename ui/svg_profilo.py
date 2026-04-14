"""
svg_profilo.py — Genera profilo SVG 2D utensile + holder
Asse verticale, punta in basso.
Usa polyline raw Hypermill per profili accurati (holder + freeShaft).
"""
import struct
import math
import json as _json


def _leggi_profilo_polyline(polyline_bytes):
    """
    Decodifica universale polyline binaria Hypermill.
    Valida per: holder (tutti i tipi), freeShaft frese. NON per freeTip.

    Struttura: big-endian double, step 104 bytes da offset 128.
      r = polyline_bytes[base:base+8]
      z = polyline_bytes[base+8:base+16]

    Ritorna lista [(r, z), ...] con punto di origine aggiunto:
      - Tipo A (z_pt0 < 2mm): [(0.0, 0.0)] + punti  (naso esplicito)
      - Tipo B (z_pt0 >= 2mm): [(r_pt0, 0.0)] + punti  (estendi cilindro da z=0)
    """
    if not polyline_bytes or len(polyline_bytes) < 144:
        return []

    pts = []
    for base in range(128, len(polyline_bytes) - 15, 104):
        try:
            r = struct.unpack('>d', polyline_bytes[base:base+8])[0]
            z = struct.unpack('>d', polyline_bytes[base+8:base+16])[0]
            if (not math.isnan(r) and not math.isinf(r) and
                not math.isnan(z) and not math.isinf(z) and
                r >= 0.01 and z > 0 and r < 500 and z < 2000):
                pts.append((round(r, 4), round(z, 4)))
        except Exception:
            pass

    if not pts:
        return []

    r0, z0 = pts[0]
    if z0 < 2.0:
        return [(0.0, 0.0)] + pts
    else:
        return [(r0, 0.0)] + pts


def _parse_json_profilo(js_str):
    """Parsa profilo_*_json e applica stessa logica di origine."""
    if not js_str:
        return []
    try:
        raw = _json.loads(js_str)
        if isinstance(raw, dict):
            raw = raw.get('punti', [])
        pts = [(float(r), float(z)) for r, z in raw if float(r) >= 0.01]
        if not pts:
            return []
        r0, z0 = pts[0]
        if z0 < 2.0:
            return [(0.0, 0.0)] + pts
        else:
            return [(r0, 0.0)] + pts
    except Exception:
        return []


def genera_svg_profilo(u, segmenti=None):
    """
    Genera SVG del profilo utensile + holder.
    u: dict con parametri utensile e opzionalmente:
      holder_polyline_raw (bytes) o profilo_punti_json (str)
      shaft_polyline_raw (bytes) o profilo_gambo_json (str)
    """
    if segmenti is None:
        segmenti = []

    # ── Parametri geometrici ─────────────────────────────────────────
    D            = float(u.get('diametro_mm') or 0)
    R            = float(u.get('raggio_punta_mm') or 0)
    L_tot        = float(u.get('lunghezza_totale_mm') or 0)
    L_tagl       = float(u.get('lunghezza_tagl_mm') or 0)
    fuori_pinza  = float(u.get('fuori_pinza_mm') or 0)
    D_stelo      = float(u.get('diam_stelo_mm') or 0)
    tipo         = u.get('tipo') or 'FLAT'
    gage_length  = float(u.get('gage_length_mm') or 0)
    angolo_punta = float(u.get('angolo_punta_gradi') or 118)

    if D <= 0 or L_tot <= 0:
        return '<svg width="200" height="100"><text x="10" y="50" fill="#999" font-size="12">Dati geometrici insufficienti</text></svg>'

    # ── Lettura profili (polyline raw prioritaria, fallback JSON, ultimo fallback segmenti) ──
    holder_poly = u.get('holder_polyline_raw') or u.get('profilo_polyline_raw')
    shaft_poly  = u.get('shaft_polyline_raw')

    holder_pts = []
    if holder_poly:
        holder_pts = _leggi_profilo_polyline(holder_poly)
    if not holder_pts:
        holder_pts = _parse_json_profilo(u.get('profilo_punti_json'))
    if not holder_pts and segmenti:
        z_cur = 0.0
        tmp = []
        for s in sorted(segmenti, key=lambda x: x.get('numero_segmento', 0)):
            d_inf = float(s.get('diametro_inf_mm') or 0)
            d_sup = float(s.get('diametro_sup_mm') or 0)
            l_seg = float(s.get('lunghezza_mm') or 0)
            if l_seg <= 0:
                continue
            if not tmp:
                tmp.append((d_inf / 2, z_cur))
            tmp.append((d_sup / 2, z_cur + l_seg))
            z_cur += l_seg
        holder_pts = tmp

    shaft_pts = []
    if shaft_poly:
        shaft_pts = _leggi_profilo_polyline(shaft_poly)
    if not shaft_pts:
        shaft_pts = _parse_json_profilo(u.get('profilo_gambo_json'))

    # ── Calcolo scala e canvas ───────────────────────────────────────
    d_max = D
    for r, z in holder_pts:
        if r * 2 > d_max:
            d_max = r * 2
    for r, z in shaft_pts:
        if r * 2 > d_max:
            d_max = r * 2
    if D_stelo > d_max:
        d_max = D_stelo
    if d_max <= 0:
        d_max = D

    fresa_h = fuori_pinza if fuori_pinza > 0 else L_tot
    holder_h = holder_pts[-1][1] if holder_pts else 0
    draw_total_h = fresa_h + holder_h if holder_pts else fresa_h
    if draw_total_h <= 0:
        draw_total_h = L_tot

    W, margin_left, margin_right = 340, 50, 100
    margin_top, margin_bottom = 30, 30
    draw_w = W - margin_left - margin_right

    scale_x = draw_w / (d_max * 1.2) if d_max > 0 else 1
    scale_y = (500 - margin_top - margin_bottom) / draw_total_h if draw_total_h > 0 else 1
    scale = min(scale_x, scale_y)

    H = max(int(draw_total_h * scale + margin_top + margin_bottom), 200)
    cx = margin_left + draw_w / 2

    def y_at(z_mm):
        return H - margin_bottom - z_mm * scale

    def x_left(d_mm):
        return cx - (d_mm / 2) * scale

    def x_right(d_mm):
        return cx + (d_mm / 2) * scale

    # ── Colori ───────────────────────────────────────────────────────
    COLORI = {
        'BALL': '#3b82f6', 'FLAT': '#10b981', 'BULL': '#8b5cf6',
        'DRILL': '#f59e0b', 'TAP': '#ef4444', 'REAM': '#06b6d4',
        'THREAD': '#ec4899', 'SPOT': '#f97316', 'LOLLIPOP': '#6366f1',
        'WOODRUFF': '#84cc16', 'FORM': '#6366f1', 'TAPER': '#a855f7',
    }
    col = COLORI.get(tipo, '#64748b')
    HOLDER_FILL, HOLDER_STROKE = '#475569', '#1e293b'
    STELO_FILL, STELO_STROKE = '#cbd5e1', '#64748b'

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
                 f'viewBox="0 0 {W} {H}" style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px">')

    # Asse centrale tratteggiato
    parts.append(f'<line x1="{cx}" y1="{margin_top-10}" x2="{cx}" y2="{H-margin_bottom+10}" '
                 f'stroke="#ddd" stroke-width="0.5" stroke-dasharray="4,4"/>')

    # ══════════════════════════════════════════════════════════════════
    # ZONA 1: PUNTA FRESA
    # ══════════════════════════════════════════════════════════════════
    tip_h = 0.0

    if tipo == 'BALL':
        r_px = (D / 2) * scale
        cy_ball = y_at(D / 2)
        parts.append(
            f'<path d="M {x_left(D)} {cy_ball} A {r_px} {r_px} 0 0 0 {x_right(D)} {cy_ball}" '
            f'fill="{col}" fill-opacity="0.9" stroke="{col}" stroke-width="1.2"/>'
        )
        tip_h = max(L_tagl, D / 2)
        if tip_h > D / 2:
            cil_h = (tip_h - D / 2) * scale
            parts.append(
                f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" height="{cil_h}" '
                f'fill="{col}" fill-opacity="0.9" stroke="{col}" stroke-width="1.2"/>'
            )

    elif tipo == 'BULL':
        tip_h = L_tagl if L_tagl > 0 else D / 2
        rx_corner = R * scale if R > 0 else 0
        parts.append(
            f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" height="{tip_h*scale}" '
            f'rx="{rx_corner}" ry="{rx_corner}" '
            f'fill="{col}" fill-opacity="0.9" stroke="{col}" stroke-width="1.2"/>'
        )

    elif tipo == 'DRILL':
        base_tip_h = L_tagl if L_tagl > 0 else D * 2
        half_angle = angolo_punta / 2
        tip_depth = (D / 2) / math.tan(math.radians(half_angle)) if half_angle > 0 else D / 2
        parts.append(
            f'<polygon points="{cx},{y_at(0)} {x_left(D)},{y_at(tip_depth)} {x_right(D)},{y_at(tip_depth)}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.2"/>'
        )
        if base_tip_h > tip_depth:
            cil_h = (base_tip_h - tip_depth) * scale
            parts.append(
                f'<rect x="{x_left(D)}" y="{y_at(base_tip_h)}" width="{D*scale}" height="{cil_h}" '
                f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.2"/>'
            )
        tip_h = max(base_tip_h, tip_depth)

    else:  # FLAT, TAP, REAM, THREAD, LOLLIPOP, WOODRUFF, FORM
        tip_h = L_tagl if L_tagl > 0 else min(D * 2, L_tot * 0.3)
        parts.append(
            f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" height="{tip_h*scale}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.2"/>'
        )

    # ══════════════════════════════════════════════════════════════════
    # ZONA 2: GAMBO FRESA
    # ══════════════════════════════════════════════════════════════════
    d_stelo_eff = D_stelo if D_stelo > 0 else (
        shaft_pts[1][0] * 2 if len(shaft_pts) > 1 else D
    )

    if shaft_pts and len(shaft_pts) >= 2:
        # shaft_pts[0] = origine (0,0) o (r0,0) aggiunto dal reader
        # z nei shaft_pts è cumulativo dalla punta dell'utensile
        for i in range(1, len(shaft_pts)):
            r_prev, z_prev = shaft_pts[i-1]
            r_curr, z_curr = shaft_pts[i]
            l_seg = z_curr - z_prev
            if l_seg <= 0.01:
                continue
            d_inf = r_prev * 2
            d_sup = r_curr * 2
            y_seg_bot = y_at(z_prev)
            y_seg_top = y_at(z_curr)
            seg_h = l_seg * scale
            if seg_h < 0.5:
                continue
            if abs(d_inf - d_sup) < 0.1:
                parts.append(
                    f'<rect x="{x_left(d_inf)}" y="{y_seg_top}" width="{d_inf*scale}" height="{seg_h}" '
                    f'fill="{STELO_FILL}" fill-opacity="0.5" stroke="{STELO_STROKE}" stroke-width="1"/>'
                )
            else:
                parts.append(
                    f'<polygon points="{x_left(d_inf)},{y_seg_bot} {x_right(d_inf)},{y_seg_bot} '
                    f'{x_right(d_sup)},{y_seg_top} {x_left(d_sup)},{y_seg_top}" '
                    f'fill="{STELO_FILL}" fill-opacity="0.5" stroke="{STELO_STROKE}" stroke-width="1"/>'
                )
    else:
        stelo_end = fuori_pinza if fuori_pinza > 0 else L_tot
        stelo_h_px = (stelo_end - tip_h) * scale
        if stelo_h_px > 0 and d_stelo_eff > 0:
            parts.append(
                f'<rect x="{x_left(d_stelo_eff)}" y="{y_at(stelo_end)}" '
                f'width="{d_stelo_eff*scale}" height="{stelo_h_px}" '
                f'fill="{STELO_FILL}" fill-opacity="0.4" stroke="{STELO_STROKE}" stroke-width="1"/>'
            )

    # ══════════════════════════════════════════════════════════════════
    # ZONA 3: LINEA FUORI PINZA
    # ══════════════════════════════════════════════════════════════════
    if fuori_pinza > 0:
        y_fp = y_at(fuori_pinza)
        parts.append(
            f'<line x1="{margin_left}" y1="{y_fp}" x2="{W-margin_right+10}" y2="{y_fp}" '
            f'stroke="#ef4444" stroke-width="1" stroke-dasharray="5,4"/>'
        )
        parts.append(
            f'<text x="{margin_left-3}" y="{y_fp-3}" font-size="9" fill="#ef4444" text-anchor="end" font-weight="600">FP</text>'
        )

    # ══════════════════════════════════════════════════════════════════
    # ZONA 4: HOLDER
    # ══════════════════════════════════════════════════════════════════
    if holder_pts and len(holder_pts) >= 2:
        y_holder_base = fuori_pinza if fuori_pinza > 0 else L_tot
        for i in range(1, len(holder_pts)):
            r_prev, z_prev = holder_pts[i-1]
            r_curr, z_curr = holder_pts[i]
            l_seg = z_curr - z_prev
            if l_seg <= 0.01:
                continue
            z_abs_bot = y_holder_base + z_prev
            z_abs_top = y_holder_base + z_curr
            d_inf = r_prev * 2
            d_sup = r_curr * 2
            y_seg_bot = y_at(z_abs_bot)
            y_seg_top = y_at(z_abs_top)
            seg_h = l_seg * scale
            if seg_h < 0.5:
                continue
            if abs(d_inf - d_sup) < 0.01:
                parts.append(
                    f'<rect x="{x_left(d_inf)}" y="{y_seg_top}" width="{d_inf*scale}" height="{seg_h}" '
                    f'fill="{HOLDER_FILL}" fill-opacity="0.25" stroke="{HOLDER_STROKE}" stroke-width="1.2"/>'
                )
            else:
                parts.append(
                    f'<polygon points="{x_left(d_inf)},{y_seg_bot} {x_right(d_inf)},{y_seg_bot} '
                    f'{x_right(d_sup)},{y_seg_top} {x_left(d_sup)},{y_seg_top}" '
                    f'fill="{HOLDER_FILL}" fill-opacity="0.25" stroke="{HOLDER_STROKE}" stroke-width="1.2"/>'
                )

    # ══════════════════════════════════════════════════════════════════
    # ZONA 5: QUOTE E NOME
    # ══════════════════════════════════════════════════════════════════
    nome = u.get('alias') or u.get('codice_interno') or ''
    if nome:
        nome_short = nome[:25] + ('…' if len(nome) > 25 else '')
        parts.append(
            f'<text x="{cx}" y="{margin_top-8}" font-size="10" fill="#475569" '
            f'text-anchor="middle" font-weight="600">{nome_short}</text>'
        )

    x_quote = W - margin_right + 15

    def _quota(label, val, y_pos, color='#334155'):
        parts.append(
            f'<text x="{x_quote}" y="{y_pos}" font-size="9" fill="{color}" '
            f'font-family="monospace">{label}={val}</text>'
        )

    _quota('D', f'{D:.1f}', y_at(0) + 14)
    if R > 0 and tipo != 'FLAT':
        _quota('R', f'{R:.1f}', y_at(0) + 25, col)
    _quota('L', f'{L_tot:.1f}', H // 2)
    if fuori_pinza > 0 and abs(fuori_pinza - L_tot) > 0.1:
        _quota('FP', f'{fuori_pinza:.1f}', y_at(fuori_pinza) + 4, '#ef4444')
    if gage_length > 0:
        y_gl = y_at(fuori_pinza + (gage_length - fuori_pinza) / 2) if fuori_pinza > 0 else margin_top + 15
        _quota('GL', f'{gage_length:.1f}', y_gl, '#0891b2')

    parts.append('</svg>')
    return '\n'.join(parts)
