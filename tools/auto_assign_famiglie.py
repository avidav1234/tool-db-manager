#!/usr/bin/env python3
"""
auto_assign_famiglie.py — Assegna automaticamente famiglia_id agli utensili non assegnati.

Regole basate su tipo_utensile + shaft_type:
  BULL + free      → INSERTI_TORICHE_sgr
  BULL + parametric → MD_TORICHE_sgr
  BALL + free      → INSERTI_SFERISCHE_sgr
  BALL + parametric → MD_SFERISCHE_sgr
  DRILL            → MD_PUNTE o INSERTI_PUNTE
  REAM             → ALESATORI
  TAP              → MASCHI
  THREAD           → PETTINI
  LOLLIPOP         → SMS_SVAS
"""
import sqlite3
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else 'database/tool_master.db'

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

famiglie = {r['nome']: r['id'] for r in conn.execute("SELECT id, nome FROM FamiglieUtensile")}

RULES = [
    ('BULL', 'free', 'INSERTI_TORICHE_sgr'),
    ('BULL', 'parametric', 'MD_TORICHE_sgr'),
    ('BULL', 'none', 'INSERTI_TORICHE_sgr'),
    ('BULL', None, 'MD_TORICHE_sgr'),
    ('BALL', 'free', 'INSERTI_SFERISCHE_sgr'),
    ('BALL', 'parametric', 'MD_SFERISCHE_sgr'),
    ('BALL', None, 'MD_SFERISCHE_sgr'),
    ('DRILL', 'free', 'INSERTI_PUNTE'),
    ('DRILL', 'parametric', 'MD_PUNTE'),
    ('DRILL', None, 'MD_PUNTE'),
    ('REAM', None, 'ALESATORI'),
    ('TAP', None, 'MASCHI'),
    ('THREAD', None, 'PETTINI'),
    ('LOLLIPOP', None, 'SMS_SVAS'),
    ('FLAT', None, 'MD_TORICHE_sgr'),
]

utensili = conn.execute("""
    SELECT u.id, u.alias, u.shaft_type, tu.codice as tipo_codice
    FROM utensile u LEFT JOIN tipo_utensile tu ON u.id_tipo = tu.id
    WHERE u.famiglia_id IS NULL
""").fetchall()

assigned = 0
for u in utensili:
    tc = u['tipo_codice'] or 'UNKNOWN'
    st = u['shaft_type']
    fam_id = None
    for rule_tc, rule_st, rule_fam in RULES:
        if tc == rule_tc and (rule_st is None or rule_st == st):
            fam_id = famiglie.get(rule_fam)
            if fam_id:
                break
    if fam_id:
        conn.execute("UPDATE utensile SET famiglia_id=? WHERE id=?", (fam_id, u['id']))
        assigned += 1

conn.commit()
total_unassigned = conn.execute("SELECT COUNT(*) FROM utensile WHERE famiglia_id IS NULL").fetchone()[0]
print(f"Auto-assign: {assigned} assegnati, {total_unassigned} senza famiglia")
conn.close()
