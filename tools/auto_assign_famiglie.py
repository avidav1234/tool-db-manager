import sqlite3
import argparse
import re

def ensure_holder_schema(cursor):
    """Assicura che la tabella FamiglieHolder e la colonna su portautensile esistano."""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS FamiglieHolder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        )
    ''')

    cursor.execute("PRAGMA table_info(portautensile)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'famiglia_holder_id' not in columns:
        cursor.execute("ALTER TABLE portautensile ADD COLUMN famiglia_holder_id INTEGER REFERENCES FamiglieHolder(id)")

def ensure_famiglia_utensile(cursor, nome):
    cursor.execute("SELECT id FROM FamiglieUtensile WHERE nome = ?", (nome,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO FamiglieUtensile (nome, tipo) VALUES (?, ?)", (nome, 'auto_generated'))
    return cursor.lastrowid

def ensure_famiglia_holder(cursor, nome):
    cursor.execute("SELECT id FROM FamiglieHolder WHERE nome = ?", (nome,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO FamiglieHolder (nome) VALUES (?)", (nome,))
    return cursor.lastrowid

def process_utensili(cursor, dry_run):
    print("\n--- AUTO-ASSIGN FAMIGLIE UTENSILE ---")

    cursor.execute("""
        SELECT u.id, u.alias, tu.codice as tipo, mu.codice as materiale_tagliente
        FROM utensile u
        LEFT JOIN tipo_utensile tu ON u.id_tipo = tu.id
        LEFT JOIN materiale_utensile mu ON u.id_materiale = mu.id
        WHERE u.famiglia_id IS NULL OR u.famiglia_id = ''
    """)
    utensili = cursor.fetchall()

    assegnati = 0
    non_assegnati = 0
    stats = {}

    for ut in utensili:
        uid, alias, tipo, mat = ut
        alias = alias or ""
        tipo = tipo or ""
        mat = mat or ""

        fam_nome = None

        # Logica esatta richiesta:
        if tipo == 'BALL' and ('fin' in alias.lower()):
            fam_nome = 'MD_SFERISCHE_fin'
        elif tipo == 'BALL':
            fam_nome = 'MD_SFERISCHE_sgr'

        elif tipo == 'BULL' and ('hf' in alias.lower()) and mat == 'HM':
            fam_nome = 'MD_TORICHE_sgr_HF'
        elif tipo == 'BULL' and mat == 'INSERTI' and ('fin' in alias.lower()):
            fam_nome = 'INSERTI_TORICHE_fin'
        elif tipo == 'BULL' and mat == 'INSERTI' and ('hf' in alias.lower()):
            fam_nome = 'INSERTI_TORICHE_sgr_HF'
        elif tipo == 'BULL' and mat == 'INSERTI':
            fam_nome = 'INSERTI_TORICHE_sgr'
        elif tipo == 'BULL':
            fam_nome = 'MD_TORICHE_sgr'

        elif tipo == 'DRILL' and mat == 'INSERTI':
            fam_nome = 'INSERTI_PUNTE'
        elif tipo == 'DRILL':
            fam_nome = 'MD_PUNTE'

        elif tipo == 'BALL' and mat == 'INSERTI' and ('fin' in alias.lower()):
            fam_nome = 'INSERTI_SFERICHE_fin'
        elif tipo == 'BALL' and mat == 'INSERTI':
            fam_nome = 'INSERTI_SFERICHE_sgr'

        elif tipo == 'TAP':
            fam_nome = 'MASCHI'
        elif tipo == 'THREAD':
            fam_nome = 'PETTINI'
        elif tipo == 'REAM':
            fam_nome = 'ALESATORI'
        elif tipo in ('CHAMFER', 'SPOT'):
            fam_nome = 'SMS_SVAS'

        if fam_nome:
            assegnati += 1
            stats[fam_nome] = stats.get(fam_nome, 0) + 1
            if not dry_run:
                fid = ensure_famiglia_utensile(cursor, fam_nome)
                cursor.execute("UPDATE utensile SET famiglia_id = ? WHERE id = ?", (fid, uid))
        else:
            non_assegnati += 1

    print(f"Utensili elaborati: {len(utensili)}")
    print(f"Assegnati: {assegnati}")
    print(f"Non assegnati: {non_assegnati}")
    for fam, count in stats.items():
        print(f"  - {fam}: {count}")

def process_holders(cursor, dry_run):
    print("\n--- AUTO-ASSIGN FAMIGLIE HOLDER ---")

    cursor.execute("""
        SELECT id, codice_interno
        FROM portautensile
        WHERE famiglia_holder_id IS NULL OR famiglia_holder_id = ''
    """)
    holders = cursor.fetchall()

    assegnati = 0
    non_assegnati = 0
    stats = {}

    for h in holders:
        hid, codice = h
        codice = codice or ""

        fam_nome = None

        if 'TSF' in codice.upper() or 'TFS' in codice.upper():
            # estrai numeri
            matches = re.findall(r'\d+', codice)
            lunghezza = int(matches[-1]) if matches else 0
            if lunghezza > 100:
                fam_nome = 'Idraulico_Lungo'
            else:
                fam_nome = 'Idraulico_Corto'

        elif 'TENDO' in codice.upper() and 'ZERO' in codice.upper():
            fam_nome = 'Idraulico_Tendo_ZERO'

        elif 'TENDO' in codice.upper() and ('SLIM' in codice.upper()):
            matches = re.findall(r'\d+', codice)
            lunghezza = int(matches[-1]) if matches else 0
            if lunghezza > 150:
                fam_nome = 'Idraulico_Tendo_Slim_Lungo'
            else:
                fam_nome = 'Idraulico_Tendo_Slim'

        elif 'TEND' in codice.upper() or 'SCHUNK' in codice.upper():
            fam_nome = 'Idraulico_Corto'

        elif 'SLSA' in codice.upper() or 'SLSB' in codice.upper():
            fam_nome = 'Caletto'

        elif 'WELDON' in codice.upper():
            fam_nome = 'Weldon'

        elif 'UP' in codice.upper() or 'ER' in codice.upper() or 'PINZA' in codice.upper():
            fam_nome = 'Pinza_ER'

        if fam_nome:
            assegnati += 1
            stats[fam_nome] = stats.get(fam_nome, 0) + 1
            if not dry_run:
                fid = ensure_famiglia_holder(cursor, fam_nome)
                cursor.execute("UPDATE portautensile SET famiglia_holder_id = ? WHERE id = ?", (fid, hid))
        else:
            non_assegnati += 1

    print(f"Holder elaborati: {len(holders)}")
    print(f"Assegnati: {assegnati}")
    print(f"Non assegnati: {non_assegnati}")
    for fam, count in stats.items():
        print(f"  - {fam}: {count}")

def main():
    parser = argparse.ArgumentParser(description="Auto-assegna le famiglie utensile e holder.")
    parser.add_argument("db_path", help="Percorso del database SQLite")
    parser.add_argument("--dry-run", action="store_true", help="Mostra solo cosa farebbe")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    cursor = conn.cursor()

    try:
        if not args.dry_run:
            ensure_holder_schema(cursor)
        elif args.dry_run:
            try:
                 cursor.execute("SELECT 1 FROM portautensile WHERE famiglia_holder_id IS NULL LIMIT 1")
            except sqlite3.OperationalError:
                 pass

        process_utensili(cursor, args.dry_run)

        ensure_holder_schema(cursor)

        process_holders(cursor, args.dry_run)

        if not args.dry_run:
            conn.commit()
            print("\nDatabase aggiornato con successo.")
        else:
            print("\nDRY RUN: nessuna modifica al database.")

    except Exception as e:
        print(f"Errore: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
