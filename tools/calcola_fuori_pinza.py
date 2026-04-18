#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calcola_fuori_pinza.py - Calcola automaticamente 'fuori_pinza_mm' per utensili CNC

Logica di calcolo:
- Se lunghezza_totale_mm disponibile: fuori_pinza_mm = lunghezza_totale_mm * 0.65
- Se solo lunghezza_tagliente_mm: fuori_pinza_mm = lunghezza_tagliente_mm * 1.3
- Per DRILL/TAP: fattore 0.70 invece di 0.65
- Arrotonda a 1 decimale
- Aggiorna il DB e stampa un report
"""

import os
import sys
import sqlite3
from pathlib import Path

# Aggiungi la root al path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / 'database' / 'tool_master.db'


def calcola_fuori_pinza(tipo, lunghezza_totale, lunghezza_tagliente):
    """
    Calcola fuori_pinza_mm in base ai parametri disponibili.

    Args:
        tipo (str): Tipo utensile (BALL, FLAT, BULL, DRILL, TAP, THREAD, REAM, SPOT)
        lunghezza_totale (float): lunghezza_totale_mm (può essere None)
        lunghezza_tagliente (float): lunghezza_tagliente_mm (può essere None)

    Returns:
        float or None: fuori_pinza_mm calcolato (1 decimale) o None se dati insufficienti
    """
    # Determina il fattore in base al tipo
    if tipo and tipo.upper() in ['DRILL', 'TAP']:
        fattore_base = 0.70
    else:
        fattore_base = 0.65

    # Priorita': lunghezza_totale se disponibile
    if lunghezza_totale is not None and lunghezza_totale > 0:
        fuori = lunghezza_totale * fattore_base
    elif lunghezza_tagliente is not None and lunghezza_tagliente > 0:
        # Fallback: usa lunghezza tagliente con fattore 1.3
        fuori = lunghezza_tagliente * 1.3
    else:
        # Dati insufficienti
        return None

    # Arrotonda a 1 decimale
    return round(fuori, 1)


def esegui_calcolo(dry_run=False, verbose=True):
    """
    Legge utensili dal DB, calcola fuori_pinza_mm, aggiorna il DB.

    Args:
        dry_run (bool): Se True, non aggiorna il DB (solo simulazione)
        verbose (bool): Se True, stampa log dettagliato

    Returns:
        dict: {aggiornati: int, errori: list, report: list}
    """
    if not DB_PATH.exists():
        return {'aggiornati': 0, 'errori': [f'DB non trovato: {DB_PATH}'], 'report': []}

    aggiornati = 0
    errori = []
    report = []

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Leggi tutti gli utensili
        cursor.execute("""
            SELECT id, nome, tipo, lunghezza_totale_mm, lunghezza_tagliente_mm,
                   fuori_pinza_mm
            FROM utensile
            ORDER BY id
        """)

        utensili = cursor.fetchall()

        if verbose:
            print(f'\n=== Calcolo fuori_pinza_mm ===')
            print(f'Totale utensili nel DB: {len(utensili)}')
            print()

        # Processa ogni utensile
        for u in utensili:
            uid = u['id']
            nome = u['nome']
            tipo = u['tipo']
            lunghezza_totale = u['lunghezza_totale_mm']
            lunghezza_tagliente = u['lunghezza_tagliente_mm']
            fuori_attuale = u['fuori_pinza_mm']

            # Salta se gia' calcolato
            if fuori_attuale is not None:
                continue

            # Calcola
            fuori_nuovo = calcola_fuori_pinza(tipo, lunghezza_totale, lunghezza_tagliente)

            if fuori_nuovo is None:
                # Dati insufficienti per questo utensile
                msg = f'ID {uid:3d} - {nome:30s} SKIP (dati insufficienti)'
                errori.append(msg)
                report.append(msg)
                if verbose:
                    print(msg)
            else:
                # Aggiorna il DB
                if not dry_run:
                    cursor.execute(
                        'UPDATE utensile SET fuori_pinza_mm = ? WHERE id = ?',
                        (fuori_nuovo, uid)
                    )

                msg = f'ID {uid:3d} - {nome:30s} -> {fuori_nuovo:.1f} mm'
                report.append(msg)
                aggiornati += 1

                if verbose:
                    print(msg)

        # Commit solo se non dry_run
        if not dry_run:
            conn.commit()

        conn.close()

        # Stampa summary
        summary = f'\n=== REPORT ===\nAggiornati: {aggiornati}\nErrori/Skip: {len(errori)}\n'
        if verbose:
            print(summary)

        report.append(summary)

        return {
            'aggiornati': aggiornati,
            'errori': errori,
            'report': report,
            'dry_run': dry_run
        }

    except Exception as e:
        msg = f'Errore durante il calcolo: {str(e)}'
        errori.append(msg)
        if verbose:
            print(f'[ERROR] {msg}')
        return {'aggiornati': 0, 'errori': errori, 'report': []}


if __name__ == '__main__':
    # Se chiamato direttamente da CLI
    import argparse

    parser = argparse.ArgumentParser(description='Calcola fuori_pinza_mm per utensili')
    parser.add_argument('--dry-run', action='store_true', help='Non aggiorna il DB')
    parser.add_argument('--quiet', action='store_true', help='Output silenzioso')

    args = parser.parse_args()

    result = esegui_calcolo(dry_run=args.dry_run, verbose=not args.quiet)

    if result['errori']:
        print(f"\n[ATTENZIONE] {len(result['errori'])} errori/skip")

    sys.exit(0 if result['aggiornati'] > 0 or args.dry_run else 1)
