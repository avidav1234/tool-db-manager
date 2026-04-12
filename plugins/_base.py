"""
plugins/_base.py — Contratto astratto per tutti i plugin CAM.
NON modificare questo file.
"""
import os, sqlite3

class PluginCAM:
    software   = ''
    versione   = ''
    estensioni = []
    descrizione = ''
    autore      = 'agent'
    note        = ''
    FIRMA       = {}

    def rileva(self, filepath: str) -> float:
        raise NotImplementedError

    def analizza(self, filepath: str) -> dict:
        raise NotImplementedError

    def importa(self, filepath: str, db_path: str, dry_run: bool = False) -> dict:
        raise NotImplementedError

    def _conn(self, db_path):
        con = sqlite3.connect(db_path); con.row_factory = sqlite3.Row; return con

    def _get_tipo_id(self, conn, codice):
        r = conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (codice,)).fetchone()
        if r: return r['id']
        conn.execute("INSERT OR IGNORE INTO tipo_utensile (codice,descrizione) VALUES (?,?)", (codice,codice))
        return conn.execute("SELECT id FROM tipo_utensile WHERE codice=?", (codice,)).fetchone()['id']

    def _get_mat_id(self, conn, codice):
        r = conn.execute("SELECT id FROM materiale_utensile WHERE codice=?", (codice,)).fetchone()
        if r: return r['id']
        conn.execute("INSERT OR IGNORE INTO materiale_utensile (codice,descrizione) VALUES (?,?)", (codice,codice))
        return conn.execute("SELECT id FROM materiale_utensile WHERE codice=?", (codice,)).fetchone()['id']

    @staticmethod
    def _to_float(v, default=None):
        if v is None or str(v).strip() in ('','nan','None'): return default
        try: return round(float(str(v).replace(',','.').replace('E-0','e-0')), 6)
        except: return default

    @staticmethod
    def _to_int(v, default=None):
        if v is None or str(v).strip() in ('','nan','None'): return default
        try: return int(float(str(v)))
        except: return default

    @staticmethod
    def _to_str(v, default=None):
        if v is None or str(v).strip() in ('','nan','None',''): return default
        s = str(v).strip(); return s if s else default

    def __repr__(self): return f'<Plugin {self.software} {self.versione}>'
