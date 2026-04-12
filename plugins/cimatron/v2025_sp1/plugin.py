"""
plugins/cimatron/v2025_sp1/plugin.py
Plugin Cimatron 2025 SP1 — eredita CimatronCore.
Verificato su file reale Cimatron_2025.zip (96 utensili, ~87 colonne, UTF-16).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from plugins.cimatron._core import CimatronCore

class CimatronV2025SP1(CimatronCore):
    software='Cimatron'; versione='2025 SP1'; estensioni=['.zip']
    autore='human'
    note='Verificato su Cimatron_2025.zip, 96 utensili, ~87 colonne, encoding UTF-16'
    FIRMA={
        'header_contiene':['V25.0.SP1','2025 SP1','V25.0.sp1'],
        'estensione':'.zip','struttura':'zip_csv_pipe','encoding':'utf-16',
    }

    def _match_versione(self, versione_file):
        if not versione_file: return 0.0
        vf=versione_file.upper()
        if 'V25.0.SP1' in vf or '2025 SP1' in vf: return 1.0   # match esatto
        if 'V25.0' in vf or '2025' in vf:          return 0.7   # stesso anno SP diverso
        if 'CIMATRON' in vf:                        return 0.4   # Cimatron versione diversa
        return 0.0
