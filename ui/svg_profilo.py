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
    Lunghezza totale: offset 552 (z_tot).

    Ritorna lista [(r, z), ...]:
      - origine: (0,0) Tipo A se z_pt0<2mm, oppure (r_pt0, 0) Tipo B
      - punti validi dal loop
      - estensione finale: se z_last < z_tot e r_last > 0.01, aggiunge (r_last, z_tot)
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

    # Leggi z_tot a offset 552 (lunghezza totale holder)
    z_tot = None
    if len(polyline_bytes) >= 560:
        try:
            zt = struct.unpack('>d', polyline_bytes[552:560])[0]
            if not math.isnan(zt) and not math.isinf(zt) and 0 < zt < 2000:
                z_tot = round(zt, 4)
        except Exception:
            pass

    # Estensione finale: se z_last < z_tot, estendi il cilindro finale
    r_last, z_last = pts[-1]
    if z_tot and z_last < z_tot - 0.1:
        pts.append((r_last, z_tot))

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
    # Lunghezza fisica totale fresa — necessaria per convertire coordinate
    # della freeShaft polyline (z misurata dal FONDO gambo, non dalla punta)
    total_length = float(u.get('lunghezza_totale_mm') or L_tot)

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
    # Diametro max della fresa (tagliente + stelo + raccordi)
    max_d_fresa = max(D, D_stelo if D_stelo > 0 else 0)
    for r, z in shaft_pts:
        if r * 2 > max_d_fresa:
            max_d_fresa = r * 2

    # Diametro max holder
    max_d_holder = max_d_fresa
    for r, z in holder_pts:
        if r * 2 > max_d_holder:
            max_d_holder = r * 2
    for s in segmenti:
        d_s = max(float(s.get('diametro_inf_mm') or 0), float(s.get('diametro_sup_mm') or 0))
        if d_s > max_d_holder:
            max_d_holder = d_s

    # Se holder molto più largo della fresa (es. fresa D2 + holder D63),
    # limita a 3× D_fresa per non schiacciare la fresa nel disegno.
    if max_d_holder > max_d_fresa * 3 and max_d_fresa > 0:
        d_max = max_d_fresa * 3
    else:
        d_max = max_d_holder
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
    # ZONA 1: PUNTA FRESA — geometria specifica per tipo
    # ══════════════════════════════════════════════════════════════════
    tip_h = L_tagl if L_tagl > 0 else min(D * 2, L_tot * 0.3)
    y_bottom = y_at(0)

    if tipo == 'BALL':
        # Semicerchio (sweep=0 = pancia verso il basso) + cilindro sopra
        r_px = (D / 2) * scale
        cy_ball = y_at(D / 2)
        parts.append(
            f'<path d="M {x_left(D)} {cy_ball} A {r_px} {r_px} 0 0 0 {x_right(D)} {cy_ball}" '
            f'fill="{col}" fill-opacity="0.9" stroke="{col}" stroke-width="1.5"/>'
        )
        tip_h = max(L_tagl, D / 2)
        if tip_h > D / 2:
            parts.append(
                f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" '
                f'height="{(tip_h - D/2)*scale}" '
                f'fill="{col}" fill-opacity="0.9" stroke="{col}" stroke-width="1.5"/>'
            )

    elif tipo == 'BULL':
        # Rettangolo con corner radius = R scalato
        r_corner = R * scale if R > 0 else 0
        parts.append(
            f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" '
            f'height="{tip_h*scale}" rx="{r_corner}" ry="{r_corner}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
        )

    elif tipo == 'DRILL':
        # Triangolo punta + cilindro sopra
        half_angle = angolo_punta / 2
        tip_depth = (D / 2) / math.tan(math.radians(half_angle)) if half_angle > 0 else D / 2
        parts.append(
            f'<polygon points="{cx},{y_bottom} '
            f'{x_left(D)},{y_at(tip_depth)} {x_right(D)},{y_at(tip_depth)}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
        )
        if tip_h > tip_depth:
            parts.append(
                f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" '
                f'height="{(tip_h - tip_depth)*scale}" '
                f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
            )
        tip_h = max(tip_h, tip_depth)

    elif tipo == 'THREAD':
        # Fresa a filettare: trapezio leggermente assottigliato in basso
        taper_angle = 15  # gradi per lato
        taper = tip_h * math.tan(math.radians(taper_angle))
        taper = min(taper, D * 0.2)
        d_bottom = max(D - taper * 2, D * 0.6)
        parts.append(
            f'<polygon points='
            f'"{x_left(d_bottom)},{y_bottom} {x_right(d_bottom)},{y_bottom} '
            f'{x_right(D)},{y_at(tip_h)} {x_left(D)},{y_at(tip_h)}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
        )

    elif tipo == 'SPOT':
        # Fresa a centrare: cono con angolo 90° default (45° per lato)
        angle_spot = float(u.get('angolo_punta_gradi') or 90)
        tip_depth = (D / 2) / math.tan(math.radians(angle_spot / 2)) if angle_spot > 0 else D / 2
        tip_depth = min(tip_depth, tip_h)
        parts.append(
            f'<polygon points="{cx},{y_bottom} '
            f'{x_left(D)},{y_at(tip_depth)} {x_right(D)},{y_at(tip_depth)}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
        )
        if tip_h > tip_depth:
            parts.append(
                f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" '
                f'height="{(tip_h - tip_depth)*scale}" '
                f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
            )
        tip_h = max(tip_h, tip_depth)

    elif tipo == 'FORM':
        # Fresa di forma: corner radius grande (R se disponibile, altrimenti 30% D)
        r_corner = min(R * scale, D * scale / 2) if R > 0 else D * scale * 0.3
        parts.append(
            f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" '
            f'height="{tip_h*scale}" rx="{r_corner}" ry="{r_corner}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
        )

    elif tipo == 'LOLLIPOP':
        # Fresa a T / lollipop: collo sottile + disco allargato in punta
        d_collo = D_stelo if D_stelo > 0 else D * 0.5
        disco_h = min(D * 0.4, tip_h * 0.4)
        # Disco allargato (in basso)
        parts.append(
            f'<rect x="{x_left(D)}" y="{y_at(disco_h)}" width="{D*scale}" '
            f'height="{disco_h*scale}" rx="{R*scale if R > 0 else 0}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
        )
        # Collo (sopra il disco)
        if tip_h > disco_h:
            parts.append(
                f'<rect x="{x_left(d_collo)}" y="{y_at(tip_h)}" width="{d_collo*scale}" '
                f'height="{(tip_h - disco_h)*scale}" '
                f'fill="{col}" fill-opacity="0.7" stroke="{col}" stroke-width="1.2"/>'
            )

    elif tipo == 'WOODRUFF':
        # Fresa a disco: disco piatto con raggio esterno
        r_corner = min(R * scale, D * scale / 4) if R > 0 else D * scale * 0.1
        parts.append(
            f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" '
            f'height="{tip_h*scale}" rx="{r_corner}" ry="{r_corner}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
        )

    else:  # FLAT, REAM, TAP, TAPER e altri: rettangolo a spigoli vivi
        parts.append(
            f'<rect x="{x_left(D)}" y="{y_at(tip_h)}" width="{D*scale}" '
            f'height="{tip_h*scale}" '
            f'fill="{col}" fill-opacity="0.85" stroke="{col}" stroke-width="1.5"/>'
        )

    # ══════════════════════════════════════════════════════════════════
    # ZONA 2: GAMBO FRESA
    # Nota: la z nella freeShaft è dal FONDO gambo, conversione necessaria
    # ══════════════════════════════════════════════════════════════════
    stelo_start = tip_h
    stelo_end = fuori_pinza if fuori_pinza > 0 else L_tot

    d_stelo_eff = D_stelo if D_stelo > 0 else (
        shaft_pts[1][0] * 2 if len(shaft_pts) > 1 else D
    )

    # Estrai solo i punti reali del gambo (salta origine artificiale)
    gambo_pts_reali = [(r, z) for r, z in shaft_pts if z > 0.01]

    if gambo_pts_reali and stelo_end > stelo_start:
        # Converti z: z_from_tip = total_length - z_dal_fondo
        gambo_converted = sorted(
            [(r, total_length - z) for r, z in gambo_pts_reali],
            key=lambda p: p[1]
        )
        # Estendi ai bordi della zona stelo
        if gambo_converted and gambo_converted[0][1] > stelo_start:
            gambo_converted.insert(0, (gambo_converted[0][0], stelo_start))
        # Se l'ultimo punto non arriva a stelo_end, aggiungi il cilindro del GAMBO.
        # Il diametro del gambo (cilindro che entra nella pinza) è D_stelo, non r[-1]
        # della polyline (che è il raccordo conico, più largo del gambo vero).
        if gambo_converted and gambo_converted[-1][1] < stelo_end:
            z_raccordo_fine = gambo_converted[-1][1]
            r_gambo = (D_stelo / 2) if D_stelo > 0 else gambo_converted[-1][0]
            # Punto di arrivo del raccordo al diametro del gambo
            gambo_converted.append((r_gambo, z_raccordo_fine))
            # Cilindro gambo fino a stelo_end
            gambo_converted.append((r_gambo, stelo_end))

        # Disegna segmenti con clip a [stelo_start, stelo_end]
        for i in range(1, len(gambo_converted)):
            r_prev, z_prev = gambo_converted[i-1]
            r_curr, z_curr = gambo_converted[i]
            z_a = max(z_prev, stelo_start)
            z_b = min(z_curr, stelo_end)
            if z_b <= z_a:
                continue
            if abs(z_curr - z_prev) > 0.001:
                t_a = (z_a - z_prev) / (z_curr - z_prev)
                t_b = (z_b - z_prev) / (z_curr - z_prev)
            else:
                t_a, t_b = 0.0, 1.0
            ra = r_prev + t_a * (r_curr - r_prev)
            rb = r_prev + t_b * (r_curr - r_prev)
            d_inf = ra * 2
            d_sup = rb * 2
            l_seg = z_b - z_a
            y_bot = y_at(z_a)
            y_top_seg = y_at(z_b)
            if abs(d_inf - d_sup) < 0.1:
                parts.append(
                    f'<rect x="{x_left(d_inf)}" y="{y_top_seg}" '
                    f'width="{d_inf*scale}" height="{l_seg*scale}" '
                    f'fill="{STELO_FILL}" fill-opacity="0.5" stroke="{STELO_STROKE}" stroke-width="1"/>'
                )
            else:
                parts.append(
                    f'<polygon points="{x_left(d_inf)},{y_bot} {x_right(d_inf)},{y_bot} '
                    f'{x_right(d_sup)},{y_top_seg} {x_left(d_sup)},{y_top_seg}" '
                    f'fill="{STELO_FILL}" fill-opacity="0.5" stroke="{STELO_STROKE}" stroke-width="1"/>'
                )
    else:
        # Fallback: cilindro semplice con D_stelo
        stelo_h_px = (stelo_end - stelo_start) * scale
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
