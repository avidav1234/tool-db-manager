"""
export_hypermill.py
Export utensili per hyperMILL (OPEN MIND Technologies)

STATO: in attesa delle informazioni di versione
-----------------------------------------------
Informazioni necessarie:
  1. Versione hyperMILL installata (es. 2023.1, 2024.2)
  2. Il file del database utensili e locale o su rete condivisa?
  3. E gia presente un database .hdb condiviso tra i programmatori?

Una volta ricevute le informazioni, questo modulo sara completato
con il formato di import corretto per la versione installata.

Percorsi di implementazione previsti:
  - hyperMILL >= 2023: import da XML strutturato
  - hyperMILL < 2023:  sovrascrittura diretta file .hdb (SQLite)
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')


def export_hypermill(output_path: str = None) -> str:
    # TODO: implementare dopo verifica versione
    raise NotImplementedError(
        "Export hyperMILL non ancora implementato. "
        "In attesa di informazioni sulla versione installata."
    )


if __name__ == '__main__':
    export_hypermill()
