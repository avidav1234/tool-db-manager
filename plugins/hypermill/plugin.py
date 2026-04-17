"""
plugins/hypermill/plugin.py
Plugin Hypermill per import database SQLite nel DB master.
Analizza tool_geometry e cutting_data, mappagli campi secondo documentazione OPEN MIND.
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from plugins._base import PluginCAM

class HypermillPlugin(PluginCAM):
    software = 'Hypermill'
    versione = '2023+'
    estensioni = ['.db']
    autore = 'human'
    note = 'Import database Hypermill SQLite - tool_geometry, cutting_data, tool_carrier'
    
    FIRMA = {
        'header_contiene': ['tool_geometry', 'cutting_data', 'tool_holder'],
        'estensione': '.db',
        'struttura': 'sqlite3'
    }
    
    # Mappatura campi Hypermill -> DB master
    FIELD_MAP = {
        'tool_geometry': {
            'tool_name': 'alias',
            'tool_id': 'codice_interno',
            'tool_type': '_tipo',
            'tool_diameter': 'diametro_mm',
            'tool_length': 'lunghezza_totale_mm',
            'cutting_length': 'lunghezza_tagl_mm',
            'corner_radius': 'raggio_raccordo_mm',
            'point_angle': 'angolo_punta_gradi',
            'number_of_flutes': 'num_taglienti',
            'helix_angle': 'angolo_elica_gradi',
        },
        'cutting_data': {
            'cutting_speed': 'vc_default',
            'feed_per_tooth': 'avanzamento_default',
            'spindle_speed': 'velocita_mandrino_rpm',
        },
        'tool_holder': {
            'holder_name': 'nome_pinza',
            'holder_length': 'lungh_presa_mm',
        }
    }
    
    def rileva(self, filepath):
        """Verifica se è un database Hypermill SQLite."""
        if not filepath.endswith('.db'):
            return 0.0
        
        try:
            conn = sqlite3.connect(filepath)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
            
            # Verifica tabelle caratteristiche Hypermill
            se = {'tool_geometry', 'cutting_data'}
            if se.issubset(tables):
                return 1.0
            if 'tool_geometry' in tables:
                return 0.8
            return 0.0
        except:
            return 0.0
    
    def analizza(self, filepath):
        """Estrae utensili dal database Hypermill."""
        try:
            conn = sqlite3.connect(filepath)
            cursor = conn.cursor()
            
            # Leggi tool_geometry
            cursor.execute("PRAGMA table_info(tool_geometry)")
            colonne = {row[1]: row[2] for row in cursor.fetchall()}
            
            cursor.execute("SELECT * FROM tool_geometry LIMIT 100")
            rows = cursor.fetchall()
            
            utensili = []
            for row in rows:
                utensile = dict(zip(colonne.keys(), row))
                utensili.append(utensile)
            
            conn.close()
            
            return {
                'software': self.software,
                'versione': self.versione,
                'utensili_trovati': len(utensili),
                'colonne': list(colonne.keys()),
                'campioni': utensili[:5] if utensili else []
            }
        except Exception as e:
            return {'errore': str(e)}
