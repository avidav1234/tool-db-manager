"""
export_worknc.py
Export utensili per WorkNC (Hexagon)

STATO: in attesa delle informazioni di versione
-----------------------------------------------
Informazioni necessarie:
  1. Versione WorkNC installata (es. V29, V30, 2025.x)
  2. Viene usata la Tool Library cloud Nexus/Hexagon?
  3. Dove si trova il file della tool library locale?

Una volta ricevute le informazioni, questo modulo sara completato.

Percorsi di implementazione previsti:
  - WorkNC 2025.x con Nexus: integrazione via API MachiningCloud/ToolsUnited
  - WorkNC legacy (V29-V30):  scrittura diretta nel file tool library locale
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')


def export_worknc(output_path: str = None) -> str:
    # TODO: implementare dopo verifica versione
    raise NotImplementedError(
        "Export WorkNC non ancora implementato. "
        "In attesa di informazioni sulla versione installata."
    )


if __name__ == '__main__':
    export_worknc()
