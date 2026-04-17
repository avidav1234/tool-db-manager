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

def get_fattori_diametro(db_path: str, famiglia_id: int, diametro_mm: float, db_conn=None) -> dict:
    """
    Legge dalla tabella FattoriCorrezione i fattori k_vc, k_fz, k_ap
    per il tipo_fattore 'diametro' relativo al diametro specificato.
    """
    default_factors = {'k_vc': 1.0, 'k_fz': 1.0, 'k_ap': 1.0}
    try:
        conn = db_conn or sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute('''
            SELECT k_vc, k_fz, k_ap
            FROM FattoriCorrezione
            WHERE famiglia_id = ? AND tipo_fattore = 'diametro'
              AND range_min <= ? AND range_max >= ?
            LIMIT 1
        ''', (famiglia_id, diametro_mm, diametro_mm))
        row = cur.fetchone()
        if not db_conn:
            conn.close()
        if row:
            return dict(row)
    except sqlite3.Error as e:
        print(f"Errore DB in get_fattori_diametro: {e}")
    return default_factors

def get_fattori_ld(db_path: str, famiglia_id: int, diametro_mm: float, lunghezza_mm: float, db_conn=None) -> dict:
    """
    Legge i fattori per il rapporto L/D (lunghezza_diametro) dalla tabella FattoriCorrezione.
    """
    default_factors = {'k_vc': 1.0, 'k_fz': 1.0, 'k_ap': 1.0}
    if diametro_mm <= 0:
        return default_factors

    ld_ratio = lunghezza_mm / diametro_mm

    try:
        conn = db_conn or sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute('''
            SELECT k_vc, k_fz, k_ap
            FROM FattoriCorrezione
            WHERE famiglia_id = ? AND tipo_fattore = 'lunghezza_diametro'
              AND range_min <= ? AND range_max >= ?
            LIMIT 1
        ''', (famiglia_id, ld_ratio, ld_ratio))
        row = cur.fetchone()
        if not db_conn:
            conn.close()
        if row:
            return dict(row)
    except sqlite3.Error as e:
        print(f"Errore DB in get_fattori_ld: {e}")
    return default_factors

def calcola_parametri_nctool(db_path: str, nctool_id: int, materiale_id: int, scopo: str, db_conn=None) -> bool:
    """
    Esegue il calcolo a cascata per un NCTool e salva/aggiorna in ParametriTaglio.
    """
    conn = None
    try:
        conn = db_conn or sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.row_factory = sqlite3.Row

        # 1. Recupera dati NCTool, Utensile, Holder e Famiglia
        cur.execute('''
            SELECT nc.id, nc.utensile_id, nc.holder_id, nc.fuori_pinza_mm,
                   u.famiglia_id, u.diametro_taglio_mm, u.num_denti,
                   h.k_vc as holder_k_vc, h.k_fz as holder_k_fz
            FROM NCTools nc
            JOIN utensile u ON nc.utensile_id = u.id
            LEFT JOIN Holders h ON nc.holder_id = h.id
            WHERE nc.id = ?
        ''', (nctool_id,))
        nctool = cur.fetchone()

        if not nctool:
            if not db_conn: conn.close()
            return False

        famiglia_id = nctool['famiglia_id']
        diametro = nctool['diametro_taglio_mm'] or 0.0
        n_taglienti = nctool['num_denti'] or 2
        fuori_pinza = nctool['fuori_pinza_mm'] or 0.0
        holder_k_vc = nctool['holder_k_vc'] if nctool['holder_k_vc'] is not None else 1.0
        holder_k_fz = nctool['holder_k_fz'] if nctool['holder_k_fz'] is not None else 1.0

        # 2. Recupera ParametriBase
        cur.execute('''
            SELECT vc_base, fz_base, ae_pct, ap_base
            FROM ParametriBase
            WHERE famiglia_id = ? AND materiale_id = ? AND scopo = ?
        ''', (famiglia_id, materiale_id, scopo))
        pb = cur.fetchone()

        if not pb:
            if not db_conn: conn.close()
            return False # Parametri base non trovati

        vc_base = pb['vc_base']
        fz_base = pb['fz_base']
        ae_pct = pb['ae_pct'] or 50.0
        ap_base = pb['ap_base'] or 0.0

        # 3. Calcola fattori correzione
        fattori_diam = get_fattori_diametro(db_path, famiglia_id, diametro, db_conn=conn)
        fattori_ld = get_fattori_ld(db_path, famiglia_id, diametro, fuori_pinza, db_conn=conn)

        # 4. Applica fattori
        k_vc_tot = fattori_diam['k_vc'] * fattori_ld['k_vc'] * holder_k_vc
        k_fz_tot = fattori_diam['k_fz'] * fattori_ld['k_fz'] * holder_k_fz
        k_ap_tot = fattori_diam['k_ap'] * fattori_ld['k_ap']

        vc_calc = vc_base * k_vc_tot
        fz_calc = fz_base * k_fz_tot
        ap_calc = ap_base * k_ap_tot
        ae_calc = diametro * (ae_pct / 100.0)

        # 5. Calcola n_rpm e fxy
        n_rpm = calcola_n_rpm(vc_calc, diametro)
        fxy = calcola_fxy(fz_calc, n_taglienti, n_rpm)

        # Tracciabilità
        formula_usata = "Cascade formula base * K_diam * K_ld * K_holder"
        fattori_applicati = f"k_vc:{k_vc_tot:.2f}, k_fz:{k_fz_tot:.2f}, k_ap:{k_ap_tot:.2f}"

        # 6. Salva in ParametriTaglio (upsert)
        cur.execute('''
            INSERT INTO ParametriTaglio
            (nctool_id, materiale_id, scopo, vc, n_rpm, fz, fxy, ae_mm, ap_mm, formula_usata, fattori_applicati, fonte)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'calcolato')
            ON CONFLICT(nctool_id, materiale_id, scopo) DO UPDATE SET
                vc = excluded.vc,
                n_rpm = excluded.n_rpm,
                fz = excluded.fz,
                fxy = excluded.fxy,
                ae_mm = excluded.ae_mm,
                ap_mm = excluded.ap_mm,
                formula_usata = excluded.formula_usata,
                fattori_applicati = excluded.fattori_applicati,
                fonte = 'calcolato'
        ''', (nctool_id, materiale_id, scopo, vc_calc, n_rpm, fz_calc, fxy, ae_calc, ap_calc, formula_usata, fattori_applicati))

        # Aggiorna anche NCTools con i valori calcolati principali (opzionale, ma utile per rapida consultazione)
        cur.execute('''
            UPDATE NCTools
            SET vc_calcolato = ?, fz_calcolato = ?, n_rpm_calcolato = ?
            WHERE id = ?
        ''', (vc_calc, fz_calc, n_rpm, nctool_id))

        if not db_conn:
            conn.commit()
            conn.close()

        return True

    except sqlite3.Error as e:
        print(f"Errore DB in calcola_parametri_nctool: {e}")
        if not db_conn and conn:
            conn.close()
        return False

def calcola_tutti_nctool(db_path: str, dry_run: bool = False):
    """
    Ricalcola i parametri per tutti gli NCTools.
    Se dry_run=True, effettua le SELECT ma fa un ROLLBACK.
    """
    ricalcolati = 0
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Ottiene tutte le combinazioni possibili NCTool - Materiale - Scopo presenti nei ParametriBase
            # per le famiglie degli NCTools.
            cur.execute('''
                SELECT nc.id as nctool_id, pb.materiale_id, pb.scopo
                FROM NCTools nc
                JOIN utensile u ON nc.utensile_id = u.id
                JOIN ParametriBase pb ON u.famiglia_id = pb.famiglia_id
            ''')

            combinazioni = cur.fetchall()

            if dry_run:
                conn.execute("BEGIN TRANSACTION")

            for comb in combinazioni:
                # Esegue il calcolo
                successo = calcola_parametri_nctool(db_path, comb['nctool_id'], comb['materiale_id'], comb['scopo'], db_conn=conn)
                if successo:
                    ricalcolati += 1

            if dry_run:
                conn.execute("ROLLBACK")
                print(f"Dry run: {ricalcolati} calcoli simulati, nessuna modifica al DB.")
            else:
                conn.commit()
                print(f"Calcolati {ricalcolati} set di parametri.")

        return ricalcolati
    except sqlite3.Error as e:
        print(f"Errore DB in calcola_tutti_nctool: {e}")
        return 0

if __name__ == '__main__':
    # test semplice
    vc = 150
    d = 10
    rpm = calcola_n_rpm(vc, d)
    print(f"Vc={vc}, D={d} -> {rpm:.0f} RPM")
