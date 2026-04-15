"""
svg_profilo.py â Genera profilo SVG 2D utensile + holder
Asse verticale, punta in basso.
Usa polyline raw Hypermill per profili accurati (holder + freeShaft).
"""
import struct
import math
import json as _json
import os
import sys

# Importa decoder universale (unico per importer + renderer)
_learner_path = os.path.join(os.path.dirname(__file__), '..', 'learner')
if _learner_path not in sys.path:
    sys.path.insert(0, _learner_path)
from polyline_decoder import decode_polyline as _decode_polyline_raw, polyline_to_drawing_coords as _poly_to_drawing  # noqa


def _parse_json_profilo(js_str):
    """Parsa profilo_*_json. I punti JSON sono giÃ  solo quelli del profilo
    esterno (salvati da decode_polyline) â nessuna origine da aggiungere."""
    if not js_str:
        return []
    try:
        raw = _json.loads(js_str)
        if isinstance(raw, dict):
            raw = raw.get('punti', [])
        return [(float(r), float(z)) for r, z in raw if float(r) >= 0.01]
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

    # ââ Parametri geometrici âââââââââââââââââââââââââââââââââââââââââ
    D            = float(u.get('diametro_mm') or 0)
    R            = float(u.get('raggio_punta_mm') or 0)
    L_tot        = float(u.get('lunghezza_totale_mm') or 0)
    L_tagl       = float(u.get('lunghezza_tagl_mm') or 0)
    fuori_pinza  = float(u.get('fuori_pinza_mm') or 0)
    D_stelo      = float(u.get('diam_stelo_mm') or 0)
    tipo         = u.get('tipo') or 'FLAT'
    gage_length  = float(u.get('gage_length_mm') or 0)
    angolo_punta = float(u.get('angolo_punta_gradi') or 118)
    # Lunghezza fisica totale fresa â necessaria per convertire coordinate
    # della freeShaft polyline (z misurata dal FONDO gambo, non dalla punta)
    total_length = float(u.get('lunghezza_totale_mm') or L_tot)

    if D <= 0 or L_tot <= 0:
        return '<svg width="200" height="100"><text x="10" y="50" fill="#999" font-size="12">Dati geometrici insufficienti</text></svg>'

    # ââ Lettura profili (polyline raw prioritaria, fallback JSON, ultimo fallback segmenti) ââ
    holder_poly = u.get('holder_polyline_raw') or u.get('profilo_polyline_raw')
    shaft_poly  = u.get('shaft_polyline_raw')

    holder_pts = []
    holder_z_tot = 0.0
    if holder_poly:
        holder_pts, holder_z_tot = _decode_polyline_raw(holder_poly)
        # Converti dal sistema polyline (z=0 alla base HSK) al sistema disegno
        # (z=0 alla punta, z cresce verso la base) tramite flip Z + offset z_tot.
        # Verificato su ground truth DXF TSF0800-90_HSK-A63.
        if holder_pts and holder_z_tot > 0:
            holder_pts = _poly_to_drawing(holder_pts, holder_z_tot)
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
        shaft_pts_raw, shaft_z_tot = _decode_polyline_raw(shaft_poly)
        # Stessa trasformazione flip Z applicata al profilo gambo fresa
        if shaft_pts_raw and shaft_z_tot > 0:
            shaft_pts = _poly_to_drawing(shaft_pts_raw, shaft_z_tot)
        else:
            shaft_pts = shaft_pts_raw
    if not shaft_pts:
        shaft_pts = _parse_json_profilo(u.get('profilo_gambo_json'))

    # ââ Calcolo scala e canvas âââââââââââââââââââââââââââââââââââââââ
    # Scala uniforme sul diametro massimo effettivo di TUTTO il contenuto
    # (fresa + holder): niente cap ad-hoc, niente overflow.

    # 1. Diametro massimo fresa (tagliente + stelo + raccordi)
    d_fresa = max(D, D_stelo if D_stelo > 0 else 0)
    for r, z in shaft_pts:
        d_fresa = max(d_fresa, r * 2)

    # 2. Diametro massimo holder (polyline + segmenti DB + campi derivati)
    d_holder = 0.0
    for r, z in holder_pts:
        d_holder = max(d_holder, r * 2)
    for s in segmenti:
        d_holder = max(
            d_holder,
            float(s.get('diametro_inf_mm') or 0),
            float(s.get('diametro_sup_mm') or 0),
        )
    d_holder = max(d_holder, float(u.get('d_hsk_mm') or 0))

    # 3. Diametro totale del disegno
    d_totale = max(d_fresa, d_holder)
    if d_totale <= 0:
        d_totale = D

    # 4. Altezza totale: fresa (fuori_pinza) + holder (da polyline o segmenti)
    fresa_h = fuori_pinza if fuori_pinza > 0 else L_tot
    holder_h = 0.0
    if holder_pts:
        holder_h = holder_pts[-1][1]
        if holder_z_tot > holder_h:
            holder_h = holder_z_tot
    elif segmenti:
        holder_h = sum(float(s.get('lunghezza_mm') or 0) for s in segmenti)
    draw_total_h = fresa_h + holder_h if holder_h > 0 else fresa_h
    if draw_total_h <= 0:
        draw_total_h = L_tot

    # 5. Canvas W fisso, H adattivo
    W, margin_left, margin_right = 340, 50, 100
    margin_top, margin_bottom = 30, 30
    draw_w = W - margin_left - margin_right

    # 6. Scala uniforme (garantisce tutto nel canvas, fattore 1.2 = 10% respiro per lato)
    scale_x = draw_w / (d_totale * 1.2) if d_totale > 0 else 1.0

    # 7. Cap altezza: max 900px
    max_H = 900
    scale_y_max = (max_H - margin_top - margin_bottom) / draw_total_h if draw_total_h > 0 else 1.0
    scale = min(scale_x, scale_y_max)

    H = max(int(draw_total_h * scale + margin_top + margin_bottom), 200)

    # 8. Centro orizzontale â draw_w centrato nel canvas
    cx = margin_left + draw_w / 2

    def y_at(z_mm):
        return H - margin_bottom - z_mm * scale

    def x_left(d_mm):
        return cx - (d_mm / 2) * scale

    def x_right(d_mm):
        return cx + (d_mm / 2) * scale

    # ââ Colori âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # ZONA 1: PUNTA FRESA â geometria specifica per tipo
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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
        # Fresa a centrare: cono con angolo 90Â° default (45Â° per lato)
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

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # ZONA 2: GAMBO FRESA
    # Costruisce i segmenti del gambo da dati scalari verificati.
    # Struttura reale: [tagliente] â [clearance Ã D] â [raccordo] â [gambo Ã D_stelo]
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    stelo_start = tip_h
    stelo_end   = fuori_pinza if fuori_pinza > 0 else L_tot
    d_stelo     = D_stelo if D_stelo > 0 else D
    clearance   = float(u.get('clearance_length_mm') or 0)

    gambo_segs = []  # lista di (d_inf, d_sup, z_bot, z_top)
    neck = d_stelo > D + 0.5  # gambo piÃ¹ largo del tagliente â c'Ã¨ un neck

    if stelo_end > stelo_start:
        if not neck:
            # Caso 1: gambo cilindrico uniforme
            if d_stelo > 0:
                gambo_segs.append((d_stelo, d_stelo, stelo_start, stelo_end))
        else:
            # Caso 2/3: neck tool â zona ridotta Ã D + raccordo + gambo Ã D_stelo
            z_clearance_top = stelo_start + clearance if clearance > 0 else stelo_end
            z_clearance_top = min(z_clearance_top, stelo_end)

            if clearance > 0 and z_clearance_top > stelo_start:
                # Cilindro ridotto Ã D (neck)
                gambo_segs.append((D, D, stelo_start, z_clearance_top))

            if z_clearance_top < stelo_end:
                # Raccordo conico D â d_stelo (lungo 3mm o 5% del gambo)
                l_raccordo = max(3.0, (stelo_end - z_clearance_top) * 0.05)
                l_raccordo = min(l_raccordo, stelo_end - z_clearance_top)
                z_raccordo_top = z_clearance_top + l_raccordo

                gambo_segs.append((D, d_stelo, z_clearance_top, z_raccordo_top))

                # Cilindro gambo fino alla pinza
                if z_raccordo_top < stelo_end:
                    gambo_segs.append((d_stelo, d_stelo, z_raccordo_top, stelo_end))

    # Rendering segmenti gambo
    for d_inf, d_sup, z_bot, z_top in gambo_segs:
        if z_top <= z_bot or d_inf <= 0:
            continue
        y_bot_px = y_at(z_bot)
        y_top_px = y_at(z_top)
        h_px = (z_top - z_bot) * scale
        if h_px < 0.3:
            continue
        if abs(d_inf - d_sup) < 0.1:
            parts.append(
                f'<rect x="{x_left(d_inf)}" y="{y_top_px}" '
                f'width="{d_inf*scale}" height="{h_px}" '
                f'fill="{STELO_FILL}" fill-opacity="0.5" '
                f'stroke="{STELO_STROKE}" stroke-width="1"/>'
            )
        else:
            parts.append(
                f'<polygon points="'
                f'{x_left(d_inf)},{y_bot_px} {x_right(d_inf)},{y_bot_px} '
                f'{x_right(d_sup)},{y_top_px} {x_left(d_sup)},{y_top_px}" '
                f'fill="{STELO_FILL}" fill-opacity="0.5" '
                f'stroke="{STELO_STROKE}" stroke-width="1"/>'
            )

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # ZONA 3: LINEA FUORI PINZA
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if fuori_pinza > 0:
        y_fp = y_at(fuori_pinza)
        parts.append(
            f'<line x1="{margin_left}" y1="{y_fp}" x2="{W-margin_right+10}" y2="{y_fp}" '
            f'stroke="#ef4444" stroke-width="1" stroke-dasharray="5,4"/>'
        )
        parts.append(
            f'<text x="{margin_left-3}" y="{y_fp-3}" font-size="9" fill="#ef4444" text-anchor="end" font-weight="600">FP</text>'
        )

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # ZONA 4: HOLDER â fonte di veritÃ  universale
    # 1) Polyline raw (holder_polyline_raw / profilo_punti_json) â valida
    #    per TUTTI i tipi di holder: TSF, SLSA, Weldon, BigKaiser, ecc.
    # 2) Segmenti DB (portautensile_segmento) â fallback
    # 3) Nessun fallback ad-hoc per tipo
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    y_holder_base = fuori_pinza if fuori_pinza > 0 else L_tot
    holder_segs = []

    # PrioritÃ  1: punti reali dalla polyline.
    # I segmenti vengono costruiti dai dati presenti nella polyline.
    # Se il primo punto ha z > 0 (Tipo B, es. TSF), il rendering estende
    # un cilindro del diametro r_pt0 dalla base holder fino a z_pt0 â
    # non inventa un nuovo diametro, estende solo ciÃ² che la polyline dice.
    if holder_pts and len(holder_pts) >= 2:
        r0_poly, z0_poly = holder_pts[0]
        if z0_poly > 2.0:
            # Estensione cilindrica della prima zona (non coperta da polyline)
            d0 = round(r0_poly * 2, 2)
            holder_segs.append((d0, d0, round(z0_poly, 2)))

        # Segmenti successivi dalla polyline â regola universale pendenza:
        # |Îr/Îz| > 1.0 (45Â°) indica spigolo CAD (cilindro + spigolo implicito),
        # â¤ 1.0 indica cono graduale (trapezio).
        PENDENZA_SPIGOLO = 1.0
        for i in range(1, len(holder_pts)):
            r_prev, z_prev = holder_pts[i-1]
            r_curr, z_curr = holder_pts[i]
            l_seg = z_curr - z_prev
            if l_seg <= 0.01:
                continue
            pendenza = abs(r_curr - r_prev) / l_seg
            if pendenza > PENDENZA_SPIGOLO:
                # Spigolo: cilindro Ã r_prev, transizione verticale implicita al segmento successivo
                holder_segs.append((round(r_prev*2, 2), round(r_prev*2, 2), round(l_seg, 2)))
            else:
                # Cono graduale
                holder_segs.append((round(r_prev*2, 2), round(r_curr*2, 2), round(l_seg, 2)))

        # Estensione fino a z_tot (cilindro finale se la polyline lo indica)
        if holder_z_tot > 0 and holder_pts:
            r_last, z_last = holder_pts[-1]
            if holder_z_tot > z_last + 0.01:
                holder_segs.append((round(r_last*2, 2), round(r_last*2, 2), round(holder_z_tot - z_last, 2)))

        # Fallback ai segmenti DB se la polyline non ha prodotto segmenti
        if not holder_segs and segmenti:
            for s in segmenti:
                d_i = float(s.get('diametro_inf_mm') or 0)
                d_s = float(s.get('diametro_sup_mm') or 0)
                l = float(s.get('lunghezza_mm') or 0)
                if l > 0.01:
                    holder_segs.append((d_i, d_s, l))

    # PrioritÃ  2: segmenti DB (fallback quando polyline assente)
    elif segmenti:
        for s in segmenti:
            d_i = float(s.get('diametro_inf_mm') or 0)
            d_s = float(s.get('diametro_sup_mm') or 0)
            l = float(s.get('lunghezza_mm') or 0)
            if l > 0.01:
                holder_segs.append((d_i, d_s, l))
    # PrioritÃ  3 eliminata: nessuna ricostruzione da campi derivati

    # Rendering unificato dei segmenti
    y_cursor = y_holder_base
    for d_inf, d_sup, h_seg in holder_segs:
        if h_seg <= 0 or d_inf <= 0:
            y_cursor += h_seg
            continue
        z_abs_bot = y_cursor
        z_abs_top = y_cursor + h_seg
        y_seg_bot = y_at(z_abs_bot)
        y_seg_top = y_at(z_abs_top)
        seg_h_px = h_seg * scale
        if seg_h_px < 0.5:
            y_cursor += h_seg
            continue
        if abs(d_inf - d_sup) < 0.1:
            parts.append(
                f'<rect x="{x_left(d_inf)}" y="{y_seg_top}" width="{d_inf*scale}" height="{seg_h_px}" '
                f'fill="{HOLDER_FILL}" fill-opacity="0.25" stroke="{HOLDER_STROKE}" stroke-width="1.2"/>'
            )
        else:
            parts.append(
                f'<polygon points="{x_left(d_inf)},{y_seg_bot} {x_right(d_inf)},{y_seg_bot} '
                f'{x_right(d_sup)},{y_seg_top} {x_left(d_sup)},{y_seg_top}" '
                f'fill="{HOLDER_FILL}" fill-opacity="0.25" stroke="{HOLDER_STROKE}" stroke-width="1.2"/>'
            )
        y_cursor += h_seg

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # ZONA 5: QUOTE E NOME
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    nome = u.get('alias') or u.get('codice_interno') or ''
    if nome:
        nome_short = nome[:25] + ('â¦' if len(nome) > 25 else '')
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
