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
        - profilo: lista di (r_mm, z_mm) del profilo esterno, dal primo
          punto fino a quando un rientro > 2mm su r_max segnala l'ingresso
          nella geometria interna HSK (terminazione del profilo esterno).
        - z_tot: dal terminatore r=0, o z dell'ultimo punto valido.

    Regola profilo esterno:
      - r <= 0 → scarta (dati anomali o terminatore)
      - r > 0 e rientro < 2mm rispetto a r_max → aggiungi al profilo
      - rientro >= 2mm dopo aver raggiunto r_max → STOP (geometria interna HSK)

    Verificato su:
      TSF D10 L090 (rientro 3mm → stop)
      TSF D06 L120 (rientro 1.4mm → continua fino flangia)
      A63 SLSA10 180 (monotono → tutto incluso)
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

    # Soglia: rientro oltre questo valore = geometria interna HSK
    RIENTRO_LIMITE = 2.0  # mm

    profilo = []
    z_tot = 0.0
    r_max = 0.0
    inside_hsk = False  # flag: siamo entrati nella geometria interna HSK?

    for r, z in raw_pts:
        if abs(r) < 1e-6:
            # Terminatore — sempre aggiornato, anche dopo ingresso in HSK
            if z > z_tot:
                z_tot = z
            continue
        if r < 0:
            # Dato anomalo
            continue
        # Se già dentro HSK, non aggiungere al profilo ma continua a scorrere
        # per trovare il terminatore finale
        if inside_hsk:
            continue
        # Se abbiamo raggiunto r_max e r scende > soglia → entriamo nell'HSK
        if r_max > 0 and r < r_max - RIENTRO_LIMITE:
            inside_hsk = True
            continue
        profilo.append((r, z))
        if r > r_max:
            r_max = r

    # Se nessun terminatore, z_tot = z dell'ultimo punto valido
    if z_tot <= 0 and profilo:
        z_tot = profilo[-1][1]

    return profilo, z_tot


def get_z_tot(raw_bytes):
    """Ritorna solo z_tot senza costruire il profilo completo."""
    _, z_tot = decode_polyline(raw_bytes)
    return z_tot
