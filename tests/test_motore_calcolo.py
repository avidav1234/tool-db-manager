import pytest
import sqlite3
import math
import tempfile
import os

from tools.motore_calcolo import (
    calcola_n_rpm,
    calcola_fxy,
    get_fattori_diametro,
    get_fattori_ld,
    calcola_parametri_nctool,
    calcola_tutti_nctool
)

@pytest.fixture
def db_path():
    """Crea un database SQLite in memoria/temp file con schema base e dati test"""
    # Usa file temporaneo invece di :memory: perche' motore_calcolo.py usa path string
    fd, path = tempfile.mkstemp()
    os.close(fd)

    with sqlite3.connect(path) as conn:
        cur = conn.cursor()

        # Schema minimale
        cur.executescript('''
            CREATE TABLE FamiglieUtensile (id INTEGER PRIMARY KEY, nome TEXT UNIQUE, tipo TEXT, materiale_tagliente TEXT);
            CREATE TABLE Materiali (id INTEGER PRIMARY KEY, nome_master TEXT UNIQUE);
            CREATE TABLE utensile (id INTEGER PRIMARY KEY, famiglia_id INTEGER, diametro_taglio_mm REAL, num_denti INTEGER);
            CREATE TABLE Holders (id INTEGER PRIMARY KEY, nome TEXT, k_vc REAL, k_fz REAL);
            CREATE TABLE NCTools (id INTEGER PRIMARY KEY, utensile_id INTEGER, holder_id INTEGER, nome TEXT, fuori_pinza_mm REAL, vc_calcolato REAL, fz_calcolato REAL, n_rpm_calcolato REAL);
            CREATE TABLE ParametriBase (id INTEGER PRIMARY KEY, famiglia_id INTEGER, materiale_id INTEGER, scopo TEXT, vc_base REAL, fz_base REAL, ae_pct REAL, ap_base REAL);
            CREATE TABLE FattoriCorrezione (id INTEGER PRIMARY KEY, famiglia_id INTEGER, tipo_fattore TEXT, range_min REAL, range_max REAL, k_vc REAL, k_fz REAL, k_ap REAL);
            CREATE TABLE ParametriTaglio (id INTEGER PRIMARY KEY, nctool_id INTEGER, materiale_id INTEGER, scopo TEXT, vc REAL, n_rpm REAL, fz REAL, fxy REAL, ae_mm REAL, ap_mm REAL, formula_usata TEXT, fattori_applicati TEXT, fonte TEXT, UNIQUE(nctool_id, materiale_id, scopo));
        ''')

        # Dati test
        cur.executescript('''
            INSERT INTO FamiglieUtensile (id, nome, tipo, materiale_tagliente) VALUES (1, 'Fresa_Test', 'FLAT', 'HM');
            INSERT INTO Materiali (id, nome_master) VALUES (1, 'Mat_Test');
            INSERT INTO utensile (id, famiglia_id, diametro_taglio_mm, num_denti) VALUES (1, 1, 10.0, 4);
            INSERT INTO Holders (id, nome, k_vc, k_fz) VALUES (1, 'Holder_Test', 0.9, 0.9);
            INSERT INTO NCTools (id, utensile_id, holder_id, nome, fuori_pinza_mm) VALUES (1, 1, 1, 'NCTool_1', 30.0);

            INSERT INTO ParametriBase (famiglia_id, materiale_id, scopo, vc_base, fz_base, ae_pct, ap_base)
            VALUES (1, 1, 'sgrossatura', 200.0, 0.1, 50.0, 5.0);

            INSERT INTO FattoriCorrezione (famiglia_id, tipo_fattore, range_min, range_max, k_vc, k_fz, k_ap)
            VALUES (1, 'diametro', 8.0, 12.0, 1.1, 1.1, 1.0);

            -- L/D per diametro 10 e fuori_pinza 30 -> L/D = 3.0
            INSERT INTO FattoriCorrezione (famiglia_id, tipo_fattore, range_min, range_max, k_vc, k_fz, k_ap)
            VALUES (1, 'lunghezza_diametro', 2.0, 4.0, 0.8, 0.8, 1.0);
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

def test_fattori_diametro_range(db_path):
    fattori = get_fattori_diametro(db_path, 1, 10.0)
    assert math.isclose(fattori['k_vc'], 1.1)
    assert math.isclose(fattori['k_fz'], 1.1)
    assert math.isclose(fattori['k_ap'], 1.0)

    # Range non coperto
    fattori_out = get_fattori_diametro(db_path, 1, 20.0)
    assert math.isclose(fattori_out['k_vc'], 1.0)

def test_calcola_parametri_cascata(db_path):
    # Calcolo su NCTool 1, Materiale 1, 'sgrossatura'
    success = calcola_parametri_nctool(db_path, 1, 1, 'sgrossatura')
    assert success is True

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM ParametriTaglio WHERE nctool_id = 1")
        pt = cur.fetchone()

        assert pt is not None

        # Vc attesa: Vc_base(200) * K_diam(1.1) * K_ld(0.8) * K_holder(0.9) = 158.4
        expected_vc = 200.0 * 1.1 * 0.8 * 0.9
        assert math.isclose(pt['vc'], expected_vc, rel_tol=1e-5)

        # Fz atteso: Fz_base(0.1) * K_diam(1.1) * K_ld(0.8) * K_holder(0.9) = 0.0792
        expected_fz = 0.1 * 1.1 * 0.8 * 0.9
        assert math.isclose(pt['fz'], expected_fz, rel_tol=1e-5)

        # N_rpm atteso per vc = 158.4 e diametro = 10
        expected_n = calcola_n_rpm(expected_vc, 10.0)
        assert math.isclose(pt['n_rpm'], expected_n, rel_tol=1e-5)

def test_audit_trail(db_path):
    calcola_parametri_nctool(db_path, 1, 1, 'sgrossatura')
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT formula_usata, fattori_applicati, fonte FROM ParametriTaglio WHERE nctool_id = 1")
        pt = cur.fetchone()
        assert "Cascade" in pt['formula_usata']
        assert "k_vc:" in pt['fattori_applicati']
        assert pt['fonte'] == 'calcolato'

def test_dry_run(db_path):
    ricalcolati = calcola_tutti_nctool(db_path, dry_run=True)
    assert ricalcolati == 1

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ParametriTaglio")
        count = cur.fetchone()[0]
        # Nessun salvataggio effettivo perché dry_run
        assert count == 0
