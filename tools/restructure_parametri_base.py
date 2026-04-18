import sqlite3
import sys
import os

def restructure_parametri_base(db_path):
    if not os.path.exists(db_path):
        print(f"Errore: Il database '{db_path}' non esiste.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # TASK 1: Aggiunge colonne mancanti (PRAGMA check prima di ALTER)
        cursor.execute("PRAGMA table_info(ParametriBase)")
        columns = [col[1] for col in cursor.fetchall()]

        needed = [
            ("k_vc", "REAL DEFAULT 1.0"),
            ("k_fz", "REAL DEFAULT 1.0"),
            ("k_ap", "REAL DEFAULT 1.0"),
            ("k_ae", "REAL DEFAULT 1.0"),
            ("approvato", "INTEGER DEFAULT 0"),
            ("lavorazione_id", "INTEGER REFERENCES Lavorazioni(id)")
        ]

        added_any = False
        for col_name, col_def in needed:
            if col_name not in columns:
                print(f"Aggiunta colonna {col_name}...")
                cursor.execute(f"ALTER TABLE ParametriBase ADD COLUMN {col_name} {col_def}")
                added_any = True

        # Poiché dobbiamo inserire molti record per la stessa coppia (famiglia, materiale)
        # con lo stesso 'scopo' ma diversa 'lavorazione_id', il vecchio vincolo
        # UNIQUE(famiglia_id, materiale_id, scopo) va rimosso.
        # In SQLite l'unico modo è ricreare la tabella.

        print("Ristrutturazione vincoli tabella ParametriBase...")
        cursor.execute("PRAGMA foreign_keys=OFF")

        # Recuperiamo i dati esistenti se vogliamo preservarli (ma il task dice DELETE FROM)
        # Quindi svuotiamo e ricreiamo con il nuovo vincolo.

        cursor.execute("DROP TABLE IF EXISTS ParametriBase_new")
        cursor.execute("""
            CREATE TABLE ParametriBase_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                famiglia_id INTEGER NOT NULL REFERENCES FamiglieUtensile(id),
                materiale_id INTEGER NOT NULL REFERENCES Materiali(id),
                lavorazione_id INTEGER REFERENCES Lavorazioni(id),
                scopo TEXT NOT NULL,
                vc_base REAL DEFAULT 0,
                fz_base REAL DEFAULT 0,
                k_vc REAL DEFAULT 1.0,
                k_fz REAL DEFAULT 1.0,
                k_ap REAL DEFAULT 1.0,
                k_ae REAL DEFAULT 1.0,
                ae_pct REAL DEFAULT 50.0,
                ap_base REAL,
                note TEXT,
                fonte TEXT DEFAULT 'manuale',
                approvato INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(famiglia_id, materiale_id, lavorazione_id)
            )
        """)

        # Non trasferiamo dati perché il task dice DELETE FROM ParametriBase
        cursor.execute("DROP TABLE ParametriBase")
        cursor.execute("ALTER TABLE ParametriBase_new RENAME TO ParametriBase")

        cursor.execute("PRAGMA foreign_keys=ON")

        # Fattori per materiale (da SmartTool)
        fattori_materiali = {
            '1.2343_43HRC': {'k_vc': 1.00, 'k_fz': 1.00, 'k_ap': 1.00, 'k_ae': 1.000},
            'Dievar':       {'k_vc': 0.90, 'k_fz': 0.90, 'k_ap': 0.90, 'k_ae': 0.667},
            'TQ1':          {'k_vc': 0.90, 'k_fz': 0.90, 'k_ap': 0.90, 'k_ae': 0.900},
            'Orvar':        {'k_vc': 0.95, 'k_fz': 0.95, 'k_ap': 0.95, 'k_ae': 0.950}
        }

        # Recupera FamiglieUtensile, Materiali, Lavorazioni
        cursor.execute("SELECT id FROM FamiglieUtensile")
        famiglie = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT id, nome_master FROM Materiali")
        materiali = cursor.fetchall()

        cursor.execute("SELECT id, scopo FROM Lavorazioni")
        lavorazioni = cursor.fetchall()

        print(f"Trovate {len(famiglie)} famiglie, {len(materiali)} materiali, {len(lavorazioni)} lavorazioni.")

        count = 0
        for f_id in famiglie:
            for m_id, m_nome in materiali:
                f_mat = fattori_materiali.get(m_nome, {'k_vc': 1.0, 'k_fz': 1.0, 'k_ap': 1.0, 'k_ae': 1.0})
                for l_id, l_scopo in lavorazioni:
                    cursor.execute("""
                        INSERT INTO ParametriBase
                        (famiglia_id, materiale_id, lavorazione_id, scopo,
                         k_vc, k_fz, k_ap, k_ae, approvato)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (f_id, m_id, l_id, l_scopo,
                          f_mat['k_vc'], f_mat['k_fz'], f_mat['k_ap'], f_mat['k_ae']))
                    count += 1

        conn.commit()
        print(f"Record inseriti: {count}")

    except Exception as e:
        print(f"Errore durante la ristrutturazione: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 tools/restructure_parametri_base.py <path_to_db>")
    else:
        restructure_parametri_base(sys.argv[1])
