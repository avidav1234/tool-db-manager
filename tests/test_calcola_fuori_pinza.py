#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_calcola_fuori_pinza.py - Test unitari per il calcolo fuori_pinza_mm

Test cases:
1. Utensile BALL con lunghezza totale disponibile (fattore 0.65)
2. Utensile DRILL con lunghezza totale (fattore 0.70)
3. Fallback lunghezza tagliente (fattore 1.3)
4. Dati insufficienti (entrambi None)
5. Valori zero o negativi (skip)
"""

import unittest
import sys
from pathlib import Path

# Aggiungi il path per importare il modulo
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tools.calcola_fuori_pinza import calcola_fuori_pinza


class TestCalcolaFuoriPinza(unittest.TestCase):
    """Test della funzione calcola_fuori_pinza"""

    def test_ball_con_lunghezza_totale(self):
        """BALL con lunghezza_totale_mm: fuori = totale * 0.65"""
        # 100 mm totale -> 65.0 mm
        result = calcola_fuori_pinza('BALL', 100.0, None)
        self.assertEqual(result, 65.0)

    def test_flat_con_lunghezza_totale(self):
        """FLAT con lunghezza_totale_mm: fuori = totale * 0.65"""
        # 80 mm totale -> 52.0 mm
        result = calcola_fuori_pinza('FLAT', 80.0, None)
        self.assertEqual(result, 52.0)

    def test_drill_con_lunghezza_totale(self):
        """DRILL con lunghezza_totale_mm: fuori = totale * 0.70 (fattore diverso)"""
        # 100 mm totale -> 70.0 mm (fattore 0.70 per DRILL)
        result = calcola_fuori_pinza('DRILL', 100.0, None)
        self.assertEqual(result, 70.0)

    def test_tap_con_lunghezza_totale(self):
        """TAP con lunghezza_totale_mm: fuori = totale * 0.70"""
        # 50 mm totale -> 35.0 mm
        result = calcola_fuori_pinza('TAP', 50.0, None)
        self.assertEqual(result, 35.0)

    def test_fallback_lunghezza_tagliente(self):
        """Fallback a lunghezza_tagliente quando totale non disponibile"""
        # 50 mm tagliente -> 65.0 mm (50 * 1.3)
        result = calcola_fuori_pinza('BALL', None, 50.0)
        self.assertEqual(result, 65.0)

    def test_fallback_drill_lunghezza_tagliente(self):
        """DRILL fallback a lunghezza_tagliente (stesso fattore 1.3)"""
        # 40 mm tagliente -> 52.0 mm (40 * 1.3)
        result = calcola_fuori_pinza('DRILL', None, 40.0)
        self.assertEqual(result, 52.0)

    def test_priorita_lunghezza_totale_su_tagliente(self):
        """lunghezza_totale ha priorita' su lunghezza_tagliente"""
        # Con totale=100 e tagliente=50, usa totale
        result = calcola_fuori_pinza('BALL', 100.0, 50.0)
        self.assertEqual(result, 65.0)  # 100 * 0.65

    def test_dati_insufficienti_entrambi_none(self):
        """Quando entrambi None -> ritorna None"""
        result = calcola_fuori_pinza('BALL', None, None)
        self.assertIsNone(result)

    def test_dati_insufficienti_zero(self):
        """Quando entrambi 0 o negativi -> ritorna None"""
        result = calcola_fuori_pinza('FLAT', 0, 0)
        self.assertIsNone(result)

    def test_dati_insufficienti_negativi(self):
        """Numeri negativi sono ignorati"""
        result = calcola_fuori_pinza('BALL', -100.0, -50.0)
        self.assertIsNone(result)

    def test_arrotondamento_a_1_decimale(self):
        """Risultato arrotondato a 1 decimale"""
        # 77 * 0.65 = 50.05 -> 50.1 arrotondato
        result = calcola_fuori_pinza('BALL', 77.0, None)
        self.assertEqual(result, 50.1)
        self.assertIsInstance(result, float)

    def test_case_insensitive_tipo(self):
        """Il tipo e' case-insensitive"""
        result1 = calcola_fuori_pinza('drill', 100.0, None)
        result2 = calcola_fuori_pinza('DRILL', 100.0, None)
        result3 = calcola_fuori_pinza('Drill', 100.0, None)
        self.assertEqual(result1, 70.0)
        self.assertEqual(result2, 70.0)
        self.assertEqual(result3, 70.0)

    def test_tipo_none(self):
        """Se tipo e' None, usa fattore di default 0.65"""
        result = calcola_fuori_pinza(None, 100.0, None)
        self.assertEqual(result, 65.0)

    def test_valori_reali_ball_end_mill(self):
        """Caso reale: Ball End Mill 6mm, lunghezza 50mm"""
        # Utensile tipico: lunghezza totale 50mm
        # fuori_pinza = 50 * 0.65 = 32.5 mm
        result = calcola_fuori_pinza('BALL', 50.0, None)
        self.assertEqual(result, 32.5)

    def test_valori_reali_drill(self):
        """Caso reale: Drill 5mm, lunghezza 75mm"""
        # DRILL con lunghezza 75mm
        # fuori_pinza = 75 * 0.70 = 52.5 mm
        result = calcola_fuori_pinza('DRILL', 75.0, None)
        self.assertEqual(result, 52.5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
