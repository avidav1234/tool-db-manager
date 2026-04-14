"""
polyline_decoder.py — Decoder universale polyline Hypermill

Unica fonte di verità. Nessuna logica type-specific.

Struttura polyline (verified su ground truth CAD — TSF D10 L090 + SLSA06 180):

  Byte layout: big-endian double (8 byte) ogni campo
    offset 128 + k*104:  r_k (raggio mm del punto k)
    offset 128 + k*104 + 8: z_k (posizione assiale mm del punto k)
    offset 552: z_tot (lunghezza totale holder, AFFIDABILE solo quando
                       l'ultimo punto valido è un cilindro; per holder con
                       profilo monotono crescente fino alla fine può essere
                       un valore intermedio)

Ogni punto (r_k, z_k) è una transizione geometrica nel profilo di rivoluzione.

REGOLA UNIVERSALE (verificata su CAD):
  Il profilo esterno segue r monotonamente NON DECRESCENTE dal naso alla flangia.
  Punti successivi dove r DIMINUISCE rispetto al max precedente rappresentano
  la geometria INTERNA (cavità HSK) e NON fanno parte del profilo esterno.

  Esempio TSF D10 L090 (polyline ha 4 punti):
    k=0  (12.5,  85.87)  r_max=12.5          → MANTIENI (slim end)
    k=1  (31.5,  94.00)  r_max=31.5          → MANTIENI (flangia start)
    k=2  (28.5, 101.12)  r=28.5 < 31.5       → SCARTA   (interno HSK)
    k=3  (28.5, 103.87)  r=28.5 < 31.5       → SCARTA   (interno HSK)
    Estensione z_tot (552→120): ultimo punto è cilindro max → (31.5, 120)

  Esempio SLSA06 180 (polyline ha 9 punti):
    k=0..8  r monotonamente crescente da 4.5 a 31.5  → MANTIENI TUTTI
    Nessuna estensione necessaria

NESSUNA logica if 'TSF' in name o simili. La regola è geometrica e universale.
"""
import struct
import math


def decode_polyline(raw_bytes):
    """
    Decode universale polyline Hypermill.

    Ritorna lista di punti (r_mm, z_mm) del profilo ESTERNO dal primo punto
    della polyline alla fine fisica dell'holder.

    Filtra automaticamente i punti della geometria interna HSK (quelli dove
    r diminuisce rispetto al massimo raggiunto).

    Estende l'ultimo punto fino a z_tot (offset 552) se:
      - offset 552 è maggiore dell'ultimo z del profilo esterno
      - l'ultimo punto è un cilindro (r == r_max)

    Args:
        raw_bytes: bytes della polyline (da Geometries.polyline)

    Returns:
        list di (r, z) del profilo esterno. Vuota se polyline non valida.
    """
    if not raw_bytes or not isinstance(raw_bytes, (bytes, bytearray)) or len(raw_bytes) < 144:
        return []

    # Step 1: leggi tutti i punti grezzi a offset 128 + k*104
    raw_pts = []
    for base in range(128, len(raw_bytes) - 15, 104):
        try:
            r = struct.unpack('>d', raw_bytes[base:base+8])[0]
            z = struct.unpack('>d', raw_bytes[base+8:base+16])[0]
            if (not math.isnan(r) and not math.isinf(r) and
                not math.isnan(z) and not math.isinf(z) and
                r >= 0.01 and z > 0 and r < 500 and z < 2000):
                raw_pts.append((round(r, 4), round(z, 4)))
        except Exception:
            continue

    if not raw_pts:
        return []

    # Step 2: filtro monotonia — mantieni solo punti dove r >= r_max_precedente
    # Questo esclude la geometria interna HSK (r decrescente) dal profilo esterno
    exterior = []
    r_max = 0.0
    for r, z in raw_pts:
        if r >= r_max - 1e-6:
            exterior.append((r, z))
            if r > r_max:
                r_max = r
        # Else: punto interno (cavità HSK) — scartato

    if not exterior:
        return []

    # Step 3: estensione fino a z_tot (offset 552) se l'ultimo punto è cilindro
    if len(raw_bytes) >= 560:
        try:
            z_tot = struct.unpack('>d', raw_bytes[552:560])[0]
            if (not math.isnan(z_tot) and not math.isinf(z_tot) and
                0 < z_tot < 2000):
                r_last, z_last = exterior[-1]
                # Estendi solo se z_tot > z_last (altrimenti offset 552 non è z_tot reale)
                if z_tot > z_last + 0.1:
                    exterior.append((r_last, round(z_tot, 4)))
        except Exception:
            pass

    return exterior


def decode_with_origin(raw_bytes):
    """
    Come decode_polyline ma aggiunge un punto di origine a z=0 per il rendering.

    - Tipo A (z_pt0 < 2mm): il naso è già nella polyline (es. SLSA) →
      aggiunge (0.0, 0.0) per chiudere il profilo in punta.

    - Tipo B (z_pt0 >= 2mm): il naso NON è nella polyline (es. TSF) →
      aggiunge (r_pt0, 0.0) estendendo il primo cilindro. Questo NON
      ricostruisce il cono slim reale; per quello serve il campo esterno
      d1_serraggio_mm (non presente nella polyline Hypermill).

    Questa è una CONVENZIONE DI RENDERING, non una decodifica.
    Il decode_polyline() puro non aggiunge origine.

    Args:
        raw_bytes: bytes della polyline

    Returns:
        list di (r, z) con origine aggiunta, vuota se polyline invalida.
    """
    pts = decode_polyline(raw_bytes)
    if not pts:
        return []

    r0, z0 = pts[0]
    if z0 < 2.0:
        return [(0.0, 0.0)] + pts
    else:
        return [(r0, 0.0)] + pts


def get_z_max(points):
    """Ritorna la z massima (fine fisica del profilo)."""
    if not points:
        return 0.0
    return max(z for _, z in points)
