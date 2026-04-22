"""
migra_parametri_v1_a_v2.py — Migra ParametriBase vecchio → ParametriBase_v2

Logica:
  Per ogni famiglia x materiale, prende i valori k_vc/k_fz dal vecchio
  ParametriBase e li combina con la Lavorazione SGR_PIANI (riferimento)
  per ottenere Vc_base e fz_D assoluti.
"""
import sqlite3
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else 'database/tool_master.db'

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Leggi vecchi parametri (famiglia x materiale, lavorazione SGR_PIANI come ref)
old_params = conn.execute("""
    SELECT pb.famiglia_id, pb.materiale_id, pb.k_vc, pb.k_fz, pb.k_ap, pb.k_ae,
           l.vc_base as lav_vc, l.fz_D_ratio as lav_fz, l.nome as lav_nome
    FROM ParametriBase pb
    JOIN Lavorazioni l ON pb.lavorazione_id = l.id
    WHERE l.nome = 'SGR_PIANI'
""").fetchall()

count = 0
for p in old_params:
    vc = (p['lav_vc'] or 100) * (p['k_vc'] or 1.0)
    fz_D = (p['lav_fz'] or 0.04) * (p['k_fz'] or 1.0)
    try:
        conn.execute("""INSERT OR IGNORE INTO ParametriBase_v2
            (famiglia_id, materiale_id, vc_base, fz_D_ratio, ap_D_ratio, ae_D_ratio, fonte)
            VALUES (?,?,?,?,0.5,0.3,'migrato_v1')""",
            (p['famiglia_id'], p['materiale_id'], round(vc, 1), round(fz_D, 4)))
        count += 1
    except Exception as e:
        print(f"  Skip fam={p['famiglia_id']} mat={p['materiale_id']}: {e}")

conn.commit()
total = conn.execute("SELECT COUNT(*) FROM ParametriBase_v2").fetchone()[0]
print(f"Migrati {count} record → ParametriBase_v2 (totale: {total})")
conn.close()
