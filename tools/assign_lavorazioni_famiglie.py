import sqlite3
import sys
import os

def assign_lavorazioni_famiglie(db_path):
    if not os.path.exists(db_path):
        print(f"Errore: Il database '{db_path}' non esiste.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # STEP 1 — Crea tabella nel DB
        print("STEP 1: Creazione tabella famiglia_lavorazioni...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS famiglia_lavorazioni (
                famiglia_id INTEGER REFERENCES FamiglieUtensile(id),
                lavorazione_id INTEGER REFERENCES Lavorazioni(id),
                PRIMARY KEY (famiglia_id, lavorazione_id)
            );
        """)

        # STEP 2 — Popola la tabella con logica di mapping
        print("STEP 2: Popolamento tabella con mapping...")

        mappings = [
            # 1. Famiglie FRESATURA
            {
                "famiglie": [
                    "MD_TORICHE_sgr", "MD_TORICHE_fin", "MD_TORICHE_sgr_HF",
                    "MD_SFERISCHE_sgr", "MD_SFERISCHE_fin",
                    "INSERTI_TORICHE_sgr", "INSERTI_TORICHE_fin", "INSERTI_TORICHE_sgr_HF",
                    "INSERTI_SFERICHE_sgr", "INSERTI_SFERICHE_fin"
                ],
                "lavorazioni": [
                    "SGR_PIANI", "SGR_PARETI", "SGR_HSC", "SGR_HPC",
                    "RIPRESA", "PREFINITURA", "FINITURA_PIANI",
                    "FINITURA_HSC", "FINITURA_HPC"
                ]
            },
            # 2. Famiglie FORATURA
            {
                "famiglie": ["MD_PUNTE", "INSERTI_PUNTE"],
                "lavorazioni": ["FORATURA"]
            },
            # 3. Famiglia ALESATORI
            {
                "famiglie": ["ALESATORI"],
                "lavorazioni": ["ALESATURA"]
            },
            # 4. Famiglia MASCHI
            {
                "famiglie": ["MASCHI"],
                "lavorazioni": ["FRESATURA_FILETTI"]
            },
            # 5. Famiglia PETTINI
            {
                "famiglie": ["PETTINI"],
                "lavorazioni": ["FRESATURA_FILETTI"]
            },
            # 6. Famiglia SMS_SVAS
            {
                "famiglie": ["SMS_SVAS"],
                "lavorazioni": ["SGR_PIANI", "PREFINITURA"]
            }
        ]

        for mapping in mappings:
            for f_nome in mapping["famiglie"]:
                for l_nome in mapping["lavorazioni"]:
                    cursor.execute("""
                        INSERT OR IGNORE INTO famiglia_lavorazioni (famiglia_id, lavorazione_id)
                        SELECT f.id, l.id
                        FROM FamiglieUtensile f, Lavorazioni l
                        WHERE f.nome = ? AND l.nome = ?
                    """, (f_nome, l_nome))

        # STEP 3 — Filtra ParametriBase
        print("STEP 3: Pulizia ParametriBase...")
        cursor.execute("""
            DELETE FROM ParametriBase
            WHERE (famiglia_id, lavorazione_id) NOT IN (
                SELECT famiglia_id, lavorazione_id FROM famiglia_lavorazioni
            );
        """)

        # STEP 4 — Verifica
        print("\nSTEP 4: Verifica risultati")
        print("-" * 30)

        cursor.execute("""
            SELECT f.nome, COUNT(*) as n_lavorazioni
            FROM famiglia_lavorazioni fl
            JOIN FamiglieUtensile f ON fl.famiglia_id=f.id
            GROUP BY f.nome ORDER BY f.nome;
        """)
        rows = cursor.fetchall()
        print(f"{'Famiglia':<30} | {'N. Lavorazioni':<15}")
        print("-" * 50)
        for row in rows:
            print(f"{row[0]:<30} | {row[1]:<15}")

        cursor.execute("SELECT COUNT(*) as parametri_rimasti FROM ParametriBase;")
        parametri_rimasti = cursor.fetchone()[0]
        print("-" * 50)
        print(f"ParametriBase rimasti: {parametri_rimasti}")

        conn.commit()
        print("\nOperazione completata con successo.")

    except Exception as e:
        print(f"\nErrore durante l'esecuzione: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 tools/assign_lavorazioni_famiglie.py <path_to_db>")
        sys.exit(1)
    else:
        assign_lavorazioni_famiglie(sys.argv[1])
