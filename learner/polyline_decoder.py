"""
polyline_decoder.py — Decoder universale polyline Hypermill

Unica fonte di verità per leggere le polyline binarie degli holder/frese
Hypermill. Usato sia dall'importer che dal renderer SVG.

Struttura polyline (verified sui CAD):
  big-endian double, step 104 byte da offset 128
  r = bytes[base:base+8]
  z = bytes[base+8:base+16]

Ogni punto è una transizione geometrica (r=raggio in mm, z=posizione dalla punta).
L'ultimo punto valido della polyline rappresenta la fine fisica dell'holder.

NOTA IMPORTANTE: l'offset 552 NON è sempre z_tot. Per SLSA contiene un valore
intermedio. Usare SEMPRE z_last del punto finale valido come riferimento.

NESSUNA logica type-specific — la polyline è l'unica fonte.
"""
import struct
import math


def decode_hypermill_polyline(polyline):
    """
    Ritorna lista di punti (r, z) che descrivono il profilo esterno dell'holder.

    I punti sono nell'ordine che la polyline fornisce: tipicamente dal naso
    (o prima transizione dopo il naso) verso la flangia. Non aggiunge origine
    né estensioni — ritorna esattamente i punti letti.

    Args:
        polyline: bytes della polyline Hypermill (da Geometries.polyline)

    Returns:
        list di tuple (r_mm, z_mm) ordinate per z crescente.
        Lista vuota se polyline invalida.
    """
    if not polyline or not isinstance(polyline, (bytes, bytearray)) or len(polyline) < 144:
        return []

    pts = []
    for base in range(128, len(polyline) - 15, 104):
        try:
            r = struct.unpack('>d', polyline[base:base+8])[0]
            z = struct.unpack('>d', polyline[base+8:base+16])[0]
            if (not math.isnan(r) and not math.isinf(r) and
                not math.isnan(z) and not math.isinf(z) and
                r >= 0.01 and z > 0 and r < 500 and z < 2000):
                pts.append((round(r, 4), round(z, 4)))
        except Exception:
            continue

    return pts


def decode_with_origin(polyline):
    """
    Come decode_hypermill_polyline ma aggiunge un punto di origine a z=0:

      - Tipo A (z_pt0 < 2mm): origine esplicita (0.0, 0.0) — il naso è già
        presente nella polyline (es. SLSA).

      - Tipo B (z_pt0 >= 2mm): estende il cilindro da z=0 con (r_pt0, 0) —
        il naso NON è nella polyline (es. TSF). Questo è una convenzione
        di rendering, NON una ricostruzione geometrica: il naso reale di
        un TSF può essere più piccolo (cono slim), ma quella informazione
        non è nella polyline Hypermill.

    Per avere la geometria reale del naso (es. TSF con cono Ø10→Ø25),
    serve consultare i campi derivati d1_serraggio_mm in separata sede.

    Args:
        polyline: bytes della polyline

    Returns:
        list di tuple (r, z) con origine aggiunta, vuota se polyline invalida.
    """
    pts = decode_hypermill_polyline(polyline)
    if not pts:
        return []

    r0, z0 = pts[0]
    if z0 < 2.0:
        # Tipo A: naso già presente
        return [(0.0, 0.0)] + pts
    else:
        # Tipo B: estendi cilindro da z=0
        return [(r0, 0.0)] + pts


def get_z_max(points):
    """Ritorna la z massima della lista di punti (lunghezza totale holder/gambo)."""
    if not points:
        return 0.0
    return max(z for _, z in points)
