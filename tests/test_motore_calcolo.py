import pytest
import sqlite3
import math
import tempfile
import os

from tools.motore_calcolo import (
    calcola_n_rpm,
    calcola_fxy,
    calcola_parametri_nctool
)

@pytest.fixture
def db_path():
    """Crea un database SQLite in memoria/temp file con schema base e dati test"""
    fd, path = tempfile.mkstemp()
    os.close(fd)

    with sqlite3.connect(path) as conn:
        cur = conn.cursor()

        # Schema aggiornato
        cur.executescript('''
            CREATE TABLE tipo_utensile (id INTEGER PRIMARY KEY, codice TEXT);
            CREATE TABLE FamiglieUtensile (id INTEGER PRIMARY KEY, nome TEXT UNIQUE, tipo TEXT);
            CREATE TABLE Materiali (id INTEGER PRIMARY KEY, nome_master TEXT UNIQUE);
            CREATE TABLE Lavorazioni (id INTEGER PRIMARY KEY, nome TEXT, vc_base REAL, fz_D_ratio REAL, ap_D_ratio REAL, ae_D_ratio REAL, scopo TEXT);
            CREATE TABLE utensile (id INTEGER PRIMARY KEY, codice_interno TEXT, alias TEXT, id_tipo INTEGER, famiglia_id INTEGER, diametro_mm REAL, num_taglienti INTEGER, lunghezza_totale_mm REAL, id_portautensile INTEGER, passo_mm REAL);
            CREATE TABLE FamiglieHolder (id INTEGER PRIMARY KEY, nome TEXT, k_vc REAL, k_fz REAL);
            CREATE TABLE portautensile (id INTEGER PRIMARY KEY, codice_interno TEXT, famiglia_holder_id INTEGER);
            CREATE TABLE ParametriBase (id INTEGER PRIMARY KEY, famiglia_id INTEGER, materiale_id INTEGER, lavorazione_id INTEGER, scopo TEXT, k_vc REAL, k_fz REAL, k_ap REAL, k_ae REAL, fz_base REAL);
            CREATE TABLE FattoriCorrezione (id INTEGER PRIMARY KEY, famiglia_id INTEGER, tipo_fattore TEXT, range_min REAL, range_max REAL, k_vc REAL, k_fz REAL, k_ap REAL);
        ''')

        # Dati test
        cur.executescript('''
            INSERT INTO tipo_utensile (id, codice) VALUES (1, 'BULL');
            INSERT INTO FamiglieUtensile (id, nome, tipo) VALUES (1, 'Fresa_Test', 'BULL');
            INSERT INTO Materiali (id, nome_master) VALUES (1, 'Mat_Test');
            INSERT INTO Lavorazioni (id, nome, vc_base, fz_D_ratio, ap_D_ratio, ae_D_ratio, scopo)
            VALUES (1, 'Lav_Test', 100.0, 0.04, 0.5, 0.5, 'sgrossatura');

            INSERT INTO FamiglieHolder (id, nome, k_vc, k_fz) VALUES (1, 'Holder_Test', 0.9, 0.9);
            INSERT INTO portautensile (id, codice_interno, famiglia_holder_id) VALUES (1, 'H1', 1);

            INSERT INTO utensile (id, codice_interno, alias, id_tipo, famiglia_id, diametro_mm, num_taglienti, lunghezza_totale_mm, id_portautensile)
            VALUES (1, 'U1', 'BULL_D10', 1, 1, 10.0, 4, 50.0, 1);

            INSERT INTO ParametriBase (famiglia_id, materiale_id, lavorazione_id, scopo, k_vc, k_fz, k_ap, k_ae)
            VALUES (1, 1, 1, 'sgrossatura', 1.1, 1.1, 1.0, 1.0);

            -- L/D = 50/10 = 5.0
            INSERT INTO FattoriCorrezione (famiglia_id, tipo_fattore, range_min, range_max, k_vc, k_fz, k_ap)
            VALUES (1, 'lunghezza_diametro', 4.0, 6.0, 0.8, 0.8, 1.0);
        ''')
        conn.commit()

    yield path
    os.remove(path)

def test_calcola_n_rpm():
    vc = 150.0
    d = 10.0
    expected = (vc * 1000) / (math.pi * d)
    assert math.isclose(calcola_n_rpm(vc, d), expected, rel_tol=1e-5)
    assert calcola_n_rpm(vc, 0) == 0.0

def test_calcola_fxy():
    fz = 0.1
    z = 4
    n = 1000
    expected = fz * z * n
    assert math.isclose(calcola_fxy(fz, z, n), expected, rel_tol=1e-5)

def test_calcola_parametri_nctool_new_signature(db_path):
    # Calcolo su Utensile 1, Lavorazione 1, Materiale 1
    r = calcola_parametri_nctool(db_path, 1, 1, 1)
    assert "error" not in r

    # Vc attesa: lav.vc_base(100) * pb.k_vc(1.1) * k_ld(0.8) * k_h(0.9) = 79.2
    expected_vc = 100.0 * 1.1 * 0.8 * 0.9
    assert math.isclose(r['vc'], expected_vc, rel_tol=1e-5)

    # fz atteso: lav.fz_ratio(0.04) * D(10) * pb.k_fz(1.1) * k_ld(0.8) * k_h(0.9) = 0.3168
    expected_fz = 0.04 * 10.0 * 1.1 * 0.8 * 0.9
    assert math.isclose(r['fz'], expected_fz, rel_tol=1e-5)

    # Ap atteso: lav.ap_ratio(0.5) * D(10) * pb.k_ap(1.0) = 5.0
    assert math.isclose(r['ap'], 5.0)

def test_calcola_parametri_tap(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO FamiglieUtensile (id, nome, tipo) VALUES (2, 'Tap_Fam', 'TAP')")
        conn.execute("INSERT INTO utensile (id, codice_interno, alias, id_tipo, famiglia_id, diametro_mm, passo_mm) VALUES (2, 'U2', 'M10', 1, 2, 10.0, 1.5)")
        conn.execute("INSERT INTO ParametriBase (famiglia_id, materiale_id, lavorazione_id, scopo, k_vc, k_fz, k_ap, k_ae) VALUES (2, 1, 1, 'sgrossatura', 1.0, 1.0, 1.0, 1.0)")
        conn.commit()

    r = calcola_parametri_nctool(db_path, 2, 1, 1)
    # Vc = 100 * 1 * 1 * 1 = 100
    # n = 100 * 1000 / (pi * 10) = 3183.09...
    # Fxy = n * passo = 3183.09 * 1.5 = 4774.6...
    assert math.isclose(r['fxy'], 3183.09886 * 1.5, rel_tol=1e-3)

def test_calcola_parametri_thread(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO FamiglieUtensile (id, nome, tipo) VALUES (3, 'Thread_Fam', 'THREAD')")
        conn.execute("INSERT INTO utensile (id, codice_interno, alias, id_tipo, famiglia_id, diametro_mm, num_taglienti) VALUES (3, 'U3', 'TH1', 1, 3, 10.0, 1)")
        conn.execute("INSERT INTO ParametriBase (famiglia_id, materiale_id, lavorazione_id, scopo, k_vc, k_fz, k_ap, k_ae, fz_base) VALUES (3, 1, 1, 'sgrossatura', 1.0, 1.0, 1.0, 1.0, 0.05)")
        conn.commit()

    r = calcola_parametri_nctool(db_path, 3, 1, 1)
    # Vc = 100
    # fz = pb.fz_base = 0.05
    assert math.isclose(r['fz'], 0.05)
