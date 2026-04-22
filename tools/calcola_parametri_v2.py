"""
calcola_parametri_v2.py — Calcolo parametri taglio con cascata standard industriale.

Cascata:
  1. ParametriSottoFamiglia (sottofamiglia x materiale) — override
  2. ParametriBase_v2 (famiglia x materiale) — valori base
  3. Lavorazioni_v2 (strategia) — fattori k
  4. FattoriCorrezione_v2 (holder + L/D) — fattori k
"""
import math
import sqlite3


def calcola_parametri(utensile, materiale_id, lavorazione_id, conn):
    """Calcola Vc, fz, ap, ae per un utensile su un materiale con una strategia.

    Args:
        utensile: dict con diametro_mm, fuori_pinza_mm, famiglia_id,
                  sottofamiglia_id, num_taglienti, nome_pinza/holder_name
        materiale_id: id in Materiali
        lavorazione_id: id in Lavorazioni_v2
        conn: connessione SQLite con row_factory=Row

    Returns: dict con vc, n_rpm, fz, f_mm_min, ap, ae, ld_ratio, fattori
             oppure None se parametri base non trovati.
    """
    D = float(utensile.get('diametro_mm') or 0)
    if D <= 0:
        return None
    FP = float(utensile.get('fuori_pinza_mm') or 0)
    famiglia_id = utensile.get('famiglia_id')
    sottofam_id = utensile.get('sottofamiglia_id')

    if not famiglia_id:
        return None

    # ── STEP 1+2: Parametri base con cascata sottofamiglia → famiglia ──
    vc_base = fz_D = ap_D = ae_D = None

    if sottofam_id:
        psf = conn.execute("""SELECT vc_base, fz_D_ratio, ap_D_ratio, ae_D_ratio
            FROM ParametriSottoFamiglia
            WHERE sottofamiglia_id=? AND materiale_id=?""",
            (sottofam_id, materiale_id)).fetchone()
        if psf:
            vc_base = psf['vc_base']
            fz_D = psf['fz_D_ratio']
            ap_D = psf['ap_D_ratio']
            ae_D = psf['ae_D_ratio']

    pb = conn.execute("""SELECT vc_base, fz_D_ratio, ap_D_ratio, ae_D_ratio
        FROM ParametriBase_v2
        WHERE famiglia_id=? AND materiale_id=?""",
        (famiglia_id, materiale_id)).fetchone()

    if pb:
        if vc_base is None: vc_base = pb['vc_base']
        if fz_D is None: fz_D = pb['fz_D_ratio']
        if ap_D is None: ap_D = pb['ap_D_ratio']
        if ae_D is None: ae_D = pb['ae_D_ratio']

    if vc_base is None:
        return None

    # ── STEP 3: Fattori strategia (lavorazione) ──
    lav = conn.execute("SELECT k_vc, k_fz, k_ap, k_ae FROM Lavorazioni_v2 WHERE id=?",
                       (lavorazione_id,)).fetchone()
    k_s_vc = lav['k_vc'] if lav else 1.0
    k_s_fz = lav['k_fz'] if lav else 1.0
    k_s_ap = lav['k_ap'] if lav else 1.0
    k_s_ae = lav['k_ae'] if lav else 1.0

    # ── STEP 4a: Fattore holder ──
    holder_name = utensile.get('nome_pinza') or utensile.get('holder_name') or ''
    # Cerca match per famiglia holder
    k_h_vc = k_h_fz = k_h_ap = 1.0
    if holder_name:
        # Cerca nella tabella FamiglieHolder prima
        fh = conn.execute("""SELECT fh.k_vc, fh.k_fz, fh.k_ap
            FROM portautensile p
            JOIN FamiglieHolder fh ON p.famiglia_holder_id = fh.id
            WHERE p.codice_interno = ?""", (holder_name,)).fetchone()
        if fh:
            k_h_vc = fh['k_vc'] if fh['k_vc'] is not None else 1.0
            k_h_fz = fh['k_fz'] if fh['k_fz'] is not None else 1.0
            k_h_ap = fh['k_ap'] if fh['k_ap'] is not None else 1.0

    # ── STEP 4b: Fattore L/D ──
    ld_ratio = FP / D if D > 0 and FP > 0 else 0
    k_ld_vc = k_ld_fz = k_ld_ap = 1.0
    if ld_ratio > 0:
        k_ld = conn.execute("""SELECT k_vc, k_fz, k_ap FROM FattoriCorrezione_v2
            WHERE tipo_fattore='ld_ratio' AND range_min <= ? AND range_max > ?""",
            (ld_ratio, ld_ratio)).fetchone()
        if k_ld:
            k_ld_vc = k_ld['k_vc']
            k_ld_fz = k_ld['k_fz']
            k_ld_ap = k_ld['k_ap']

    # ── CALCOLO FINALE ──
    Vc = vc_base * k_s_vc * k_h_vc * k_ld_vc
    fz = (fz_D or 0) * D * k_s_fz * k_h_fz * k_ld_fz
    ap = (ap_D or 0) * D * k_s_ap * k_h_ap * k_ld_ap
    ae = (ae_D or 0) * D * k_s_ae

    n_rpm = (Vc * 1000) / (math.pi * D) if D > 0 else 0
    n_taglienti = utensile.get('num_taglienti') or 2
    F_mm_min = fz * n_taglienti * n_rpm

    lav_nome = ''
    if lav:
        lr = conn.execute("SELECT nome FROM Lavorazioni_v2 WHERE id=?", (lavorazione_id,)).fetchone()
        lav_nome = lr['nome'] if lr else ''

    return {
        'vc': round(Vc, 1),
        'n_rpm': round(n_rpm, 0),
        'fz': round(fz, 4),
        'f_mm_min': round(F_mm_min, 1),
        'ap': round(ap, 2),
        'ae': round(ae, 2),
        'ld_ratio': round(ld_ratio, 1),
        'fattori': {
            'base': f'Vc={vc_base} fz_D={fz_D}',
            'strategia': f'{lav_nome} k_vc={k_s_vc} k_fz={k_s_fz}',
            'holder': f'k_vc={k_h_vc} k_fz={k_h_fz}',
            'ld': f'L/D={ld_ratio:.1f} k_vc={k_ld_vc} k_fz={k_ld_fz}',
        }
    }


if __name__ == '__main__':
    conn = sqlite3.connect('database/tool_master.db')
    conn.row_factory = sqlite3.Row
    u = conn.execute("""SELECT * FROM utensile
        WHERE famiglia_id IS NOT NULL AND diametro_mm > 0 LIMIT 1""").fetchone()
    if u:
        mat = conn.execute("SELECT id FROM Materiali LIMIT 1").fetchone()
        lav = conn.execute("SELECT id FROM Lavorazioni_v2 WHERE nome='SGR_PIANI'").fetchone()
        if mat and lav:
            r = calcola_parametri(dict(u), mat['id'], lav['id'], conn)
            print(f"Utensile: {u['alias']} D={u['diametro_mm']}")
            print(f"Risultato: {r}")
    conn.close()
