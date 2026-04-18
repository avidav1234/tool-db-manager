import sqlite3
import math

def calcola_n_rpm(vc: float, diametro_mm: float) -> float:
    """
    Calcola i giri al minuto (n) data la velocità di taglio (Vc) e il diametro.
    Formula: n = (Vc * 1000) / (pi * D)
    """
    if diametro_mm <= 0:
        return 0.0
    return (vc * 1000.0) / (math.pi * diametro_mm)

def calcola_fxy(fz: float, n_taglienti: int, n_rpm: float) -> float:
    """
    Calcola l'avanzamento al minuto (Fxy) dato l'avanzamento per dente (fz),
    numero di taglienti (z) e giri (n).
    Formula: Fxy = fz * z * n
    """
    return fz * n_taglienti * n_rpm

def calcola_parametri_nctool(db_path, utensile_id, lavorazione_id, materiale_id, portautensile_id=None):
    """
    Calcola i parametri di taglio ottimali basati sulla combinazione di
    utensile, lavorazione, materiale e (opzionalmente) portautensile.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 1. Recupera dati Utensile e Famiglia
        cursor.execute("""
            SELECT u.*, f.tipo as tipo_famiglia
            FROM utensile u
            LEFT JOIN FamiglieUtensile f ON u.famiglia_id = f.id
            WHERE u.id = ?
        """, (utensile_id,))
        utensile = cursor.fetchone()
        if not utensile:
            return {"error": f"Utensile {utensile_id} non trovato"}

        # 2. Legge ParametriBase JOIN Lavorazioni JOIN Materiali
        cursor.execute("""
            SELECT pb.*, l.vc_base as lav_vc_base, l.fz_D_ratio, l.ap_D_ratio, l.ae_D_ratio, l.nome as nome_lavorazione,
                   m.nome_master as nome_materiale
            FROM ParametriBase pb
            JOIN Lavorazioni l ON pb.lavorazione_id = l.id
            JOIN Materiali m ON pb.materiale_id = m.id
            WHERE pb.famiglia_id = ?
              AND pb.materiale_id = ?
              AND pb.lavorazione_id = ?
        """, (utensile['famiglia_id'], materiale_id, lavorazione_id))
        pb = cursor.fetchone()

        if not pb:
            return {"error": "Parametri base non trovati per questa combinazione"}

        # 3. Calcola fattore L/D
        d = utensile['diametro_mm'] or 0.0
        l_tot = utensile['lunghezza_totale_mm'] or 0.0
        ld_ratio = l_tot / d if d > 0 else 0

        cursor.execute("""
            SELECT k_vc, k_fz, k_ap
            FROM FattoriCorrezione
            WHERE famiglia_id = ? AND tipo_fattore = 'lunghezza_diametro'
              AND range_min <= ? AND range_max > ?
            LIMIT 1
        """, (utensile['famiglia_id'], ld_ratio, ld_ratio))
        fc_ld = cursor.fetchone()

        k_ld_vc = fc_ld['k_vc'] if fc_ld else 1.0
        k_ld_fz = fc_ld['k_fz'] if fc_ld else 1.0
        # Il prompt non menziona k_ap da FattoriCorrezione per L/D nel punto 2, ma nel punto 4 dice pb.k_ap.
        # Seguo la cascata descrittiva del punto 4.

        # 4. Calcola fattore holder
        k_h_vc = 1.0
        k_h_fz = 1.0

        # Determiniamo quale portautensile usare
        pid = portautensile_id or utensile['id_portautensile']
        if pid:
            cursor.execute("""
                SELECT fh.k_vc, fh.k_fz
                FROM portautensile p
                JOIN FamiglieHolder fh ON p.famiglia_holder_id = fh.id
                WHERE p.id = ?
            """, (pid,))
            holder = cursor.fetchone()
            if holder:
                k_h_vc = holder['k_vc'] if holder['k_vc'] is not None else 1.0
                k_h_fz = holder['k_fz'] if holder['k_fz'] is not None else 1.0

        # 5. Calcola valori finali (Punto 4 del task)
        # Vc  = lav.vc_base × pb.k_vc × k_ld × k_h_vc
        vc = pb['lav_vc_base'] * pb['k_vc'] * k_ld_vc * k_h_vc

        # n   = Vc × 1000 / (π × D)
        n = calcola_n_rpm(vc, d)

        # fz  = lav.fz_D_ratio × D × pb.k_fz × k_ld × k_h_fz
        fz = pb['fz_D_ratio'] * d * pb['k_fz'] * k_ld_fz * k_h_fz

        # Fxy = fz × num_taglienti × n
        z = utensile['num_taglienti'] or 1
        fxy = calcola_fxy(fz, z, n)

        # Ap  = lav.ap_D_ratio × D × pb.k_ap
        ap = pb['ap_D_ratio'] * d * pb['k_ap']

        # Ae  = lav.ae_D_ratio × D × pb.k_ae
        ae = pb['ae_D_ratio'] * d * pb['k_ae']

        # 6. Eccezioni (Punto 5 del task)
        if utensile['tipo_famiglia'] == 'TAP':
            # Fxy = n × passo_mm (ignora fz)
            passo = utensile['passo_mm'] or 0.0
            fxy = n * passo
        elif utensile['tipo_famiglia'] == 'THREAD':
            # usa fz assoluto, non ratio.
            # Immagino che in questo caso fz_D_ratio di Lavorazioni contenga un valore assoluto?
            # O forse ParametriBase.fz_base?
            # "usa fz assoluto, non ratio" -> fz = pb.fz_base (o simile) * pb.k_fz ...
            # Rileggendo: fz = lav.fz_D_ratio * D ...
            # Se è THREAD, usiamo fz = pb.fz_base (assumendo che pb.fz_base sia quello assoluto)
            # Ma il task non specifica dove prendere l'fz assoluto.
            # Spesso fz_base in ParametriBase è quello assoluto se non è un ratio.
            # Vediamo cosa c'è in Lavorazioni: fz_D_ratio.
            # Se "usa fz assoluto", forse intende fz = pb.fz_base * pb.k_fz * k_ld * k_h_fz?
            # Proviamo a vedere se pb ha fz_base. Sì.
            fz = pb['fz_base'] * pb['k_fz'] * k_ld_fz * k_h_fz
            fxy = calcola_fxy(fz, z, n)

        return {
            "utensile": utensile['alias'],
            "lavorazione": pb['nome_lavorazione'],
            "materiale": pb['nome_materiale'],
            "vc": round(vc, 2),
            "n": round(n, 0),
            "fz": round(fz, 4),
            "fxy": round(fxy, 0),
            "ap": round(ap, 2),
            "ae": round(ae, 2),
            "fattori": {
                "k_vc_mat": pb['k_vc'],
                "k_fz_mat": pb['k_fz'],
                "k_ld_vc": k_ld_vc,
                "k_ld_fz": k_ld_fz,
                "k_h_vc": k_h_vc,
                "k_h_fz": k_h_fz
            }
        }

    except Exception as e:
        return {"error": f"Errore durante il calcolo: {e}"}
    finally:
        conn.close()

def calcola_tutti_nctool(db_path: str, dry_run: bool = False):
    # Questa funzione va aggiornata se necessario, ma il task si focalizza su calcola_parametri_nctool
    # Per ora la lasciamo come placeholder o la implementiamo se serve.
    pass

if __name__ == '__main__':
    # test semplice
    vc = 150
    d = 10
    rpm = calcola_n_rpm(vc, d)
    print(f"Vc={vc}, D={d} -> {rpm:.0f} RPM")
