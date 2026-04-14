"""
polyline_decoder.py — Decoder universale polyline Hypermill

Struttura verificata su ground truth CAD:
  - TSF D10 L090  (DXF TSF0800-90_HSK-A63)
  - A63 SLSA10 180

Byte layout (big-endian double, 8 byte):
  offset 128 + k*104      → r_k  (raggio mm del punto k)
  offset 128 + k*104 + 8  → z_k  (posizione assiale mm del punto k)

Terminatore: l'ultimo punto ha r=0, z=z_tot_reale.
  - Non fa parte del profilo disegnabile
  - La sua z è la lunghezza fisica totale dell'holder
  - ATTENZIONE: offset 552 NON è affidabile come z_tot (per SLSA contiene
    un valore intermedio). Usare sempre il terminatore r=0.

Regola profilo esterno (verificata su TSF e SLSA):
  Mantieni solo i punti con r >= r_max_precedente (monotonia non decrescente).
  I punti con r decrescente sono geometria interna HSK — scartarli.

Limiti range verificati sui campioni disponibili: r <= 31.5, z <= 180.
  I limiti nel codice (r < 500, z < 2000) sono conservativi — da aggiornare
  quando si disporrà di dati CAD per holder HSK100 o BT50.
"""

import struct
import math


def decode_polyline(raw_bytes):
    """
    Decodifica una polyline Hypermill.

    Ritorna:
        (profilo, z_tot) dove:
        - profilo: lista di (r_mm, z_mm) del profilo esterno, dal primo punto
          reale fino all'ultimo prima del terminatore. Punti interni HSK esclusi.
        - z_tot: lunghezza fisica totale dell'holder in mm, dalla z del
          terminatore r=0. Vale 0.0 se il terminatore non è trovato.

    Il profilo NON include il naso (z=0) — quella parte non è nella polyline
    Hypermill. Va gestita separatamente dall'importer usando d1_serraggio_mm.
    """
    if not raw_bytes or not isinstance(raw_bytes, (bytes, bytearray)) or len(raw_bytes) < 144:
        return [], 0.0

    # Leggi tutti i punti grezzi a step di 104 byte da offset 128
    raw_pts = []
    for base in range(128, len(raw_bytes) - 15, 104):
        try:
            r = struct.unpack('>d', raw_bytes[base:base+8])[0]
            z = struct.unpack('>d', raw_bytes[base+8:base+16])[0]
            if math.isnan(r) or math.isinf(r) or math.isnan(z) or math.isinf(z):
                continue
            if z < 0 or z > 2000:
                continue
            raw_pts.append((round(r, 4), round(z, 4)))
        except Exception:
            continue

    if not raw_pts:
        return [], 0.0

    # Estrai z_tot dal terminatore r=0 (l'ultimo punto con r=0 dà la lunghezza totale)
    z_tot = 0.0
    profilo_pts = []
    for r, z in raw_pts:
        if abs(r) < 1e-9:
            # Terminatore — prendi la z, non aggiungerlo al profilo
            if z > z_tot:
                z_tot = z
        else:
            profilo_pts.append((r, z))

    if not profilo_pts:
        return [], z_tot

    # Filtro monotonia: mantieni solo r >= r_max (profilo esterno)
    # Scarta i punti con r decrescente (geometria interna HSK)
    exterior = []
    r_max = 0.0
    for r, z in profilo_pts:
        if r >= r_max - 1e-6:
            exterior.append((r, z))
            if r > r_max:
                r_max = r
        # else: punto interno HSK, scartato

    # Se non è stato trovato un terminatore r=0 esplicito, usa la z del
    # punto più lontano come z_tot (fallback per polyline brevi senza terminatore)
    if z_tot <= 0 and exterior:
        z_tot = exterior[-1][1]

    return exterior, z_tot


def get_z_tot(raw_bytes):
    """Ritorna solo z_tot senza costruire il profilo completo."""
    _, z_tot = decode_polyline(raw_bytes)
    return z_tot
