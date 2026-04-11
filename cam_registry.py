"""
cam_registry.py
===============
Registry centrale di tutti i formati CAM supportati.

Ogni CAM registra:
  - come si DECODIFICA (decode): file campione -> DB master
  - come si GENERA (generate): DB master -> file per il CAM
  - stato decoder e generator
  - formati file accettati

Aggiungere un nuovo CAM = aggiungere una entry in CAM_REGISTRY.
Il resto del sistema (UI, scheduler, export) lo riconosce automaticamente.
"""

import os
import sys

_BASE    = os.path.join(os.path.dirname(__file__))
_LEARNER = os.path.join(_BASE, 'learner')
sys.path.insert(0, _LEARNER)
sys.path.insert(0, _BASE)


# ---------------------------------------------------------------
# REGISTRY — un entry per ogni CAM
# ---------------------------------------------------------------
CAM_REGISTRY = {

    'cimatron': {
        'nome':        'Cimatron',
        'versioni':    ['E24', '2024', '2025'],
        'logo_colore': '#1a6e35',

        # DECODER
        'decoder': {
            'stato':      'completo',
            'formati':    ['.zip', '.csv', '.xls'],
            'descrizione': 'ZIP (Cutters+Material), CSV UTF-16 pipe-separato, XLS nativo',
            'fn':          'cimatron_decoder',
        },

        # GENERATOR
        'generator': {
            'stato':      'completo',
            'formati':    ['.csv'],
            'descrizione': 'CSV UTF-16 pipe-separato, importabile direttamente in Cimatron',
            'fn':          'cimatron_generator',
        },
    },

    'hypermill': {
        'nome':        'hyperMILL',
        'versioni':    ['2023', '2024', '2025'],
        'logo_colore': '#0055cc',

        'decoder': {
            'stato':      'in_attesa',
            'formati':    ['.xml', '.csv', '.mdb'],
            'descrizione': 'In attesa di file campione export da hyperMILL',
            'fn':          'hypermill_decoder',
        },

        'generator': {
            'stato':      'in_attesa',
            'formati':    ['.xml', '.csv'],
            'descrizione': 'In attesa di specifiche formato import hyperMILL',
            'fn':          'hypermill_generator',
        },
    },

    'worknc': {
        'nome':        'WorkNC',
        'versioni':    ['V29', 'V30', '2025'],
        'logo_colore': '#7c3aed',

        'decoder': {
            'stato':      'in_attesa',
            'formati':    ['.csv', '.xml', '.wtl'],
            'descrizione': 'In attesa di file campione export da WorkNC',
            'fn':          'worknc_decoder',
        },

        'generator': {
            'stato':      'in_attesa',
            'formati':    ['.csv', '.xml'],
            'descrizione': 'In attesa di specifiche formato import WorkNC',
            'fn':          'worknc_generator',
        },
    },

    'mastercam': {
        'nome':        'Mastercam',
        'versioni':    ['2023', '2024', '2025'],
        'logo_colore': '#b91c1c',

        'decoder': {
            'stato':      'agente',
            'formati':    ['.csv', '.xlsx', '.xml'],
            'descrizione': 'Usa agente AI per mappatura automatica',
            'fn':          'generico_decoder',
        },

        'generator': {
            'stato':      'in_attesa',
            'formati':    ['.csv'],
            'descrizione': 'In attesa di file campione',
            'fn':          'generico_generator',
        },
    },

    'generico': {
        'nome':        'CAM generico',
        'versioni':    ['qualsiasi'],
        'logo_colore': '#6b7280',

        'decoder': {
            'stato':      'agente',
            'formati':    ['.csv', '.xlsx', '.xls', '.xml', '.zip'],
            'descrizione': 'Parser euristico + agente AI per colonne non riconosciute',
            'fn':          'generico_decoder',
        },

        'generator': {
            'stato':      'parziale',
            'formati':    ['.csv', '.xlsx'],
            'descrizione': 'Export CSV/Excel generico dal DB master',
            'fn':          'generico_generator',
        },
    },
}

STATI_LABEL = {
    'completo':   ('Completo',   '#166534', '#dcfce7'),
    'parziale':   ('Parziale',   '#854d0e', '#fef9c3'),
    'agente':     ('Via AI',     '#1d4ed8', '#eff6ff'),
    'in_attesa':  ('In attesa',  '#6b7280', '#f1f0ee'),
}


# ---------------------------------------------------------------
# DECODER FUNCTIONS
# ---------------------------------------------------------------

def cimatron_decoder(filepath: str, usa_agente: bool = True) -> dict:
    """Decodifica qualsiasi formato Cimatron -> dizionario con df utensili + df materiali."""
    from cimatron_parser import is_cimatron_file, leggi_cimatron_csv, leggi_cimatron_xls, leggi_cimatron_zip
    import zipfile

    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.zip' and is_cimatron_file(filepath):
        return leggi_cimatron_zip(filepath)
    if ext == '.xls' and is_cimatron_file(filepath):
        return leggi_cimatron_xls(filepath)
    if ext == '.csv' and is_cimatron_file(filepath):
        return leggi_cimatron_csv(filepath)
    raise ValueError(f"File non riconosciuto come formato Cimatron: {filepath}")


def generico_decoder(filepath: str, usa_agente: bool = True) -> dict:
    """Decoder universale con agente AI per CAM non nativi."""
    from format_learner import analizza_file
    return analizza_file(filepath, usa_agente=usa_agente)


def hypermill_decoder(filepath: str, usa_agente: bool = True) -> dict:
    raise NotImplementedError(
        "Decoder hyperMILL non ancora implementato.\n"
        "Carica un file export da hyperMILL nel Format Learner per iniziare."
    )


def worknc_decoder(filepath: str, usa_agente: bool = True) -> dict:
    raise NotImplementedError(
        "Decoder WorkNC non ancora implementato.\n"
        "Carica un file export da WorkNC nel Format Learner per iniziare."
    )


# ---------------------------------------------------------------
# GENERATOR FUNCTIONS
# ---------------------------------------------------------------

def cimatron_generator(output_path: str, conn) -> str:
    """Genera file CSV Cimatron dal DB master."""
    from exporters.export_cimatron import export_cutters
    export_cutters(output_path, conn=conn)
    return output_path


def generico_generator(output_path: str, conn) -> str:
    """Genera CSV/Excel generico dal DB master."""
    import pandas as pd
    import sqlite3
    rows = conn.execute("SELECT * FROM utensile_completo WHERE attivo=1").fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    ext = os.path.splitext(output_path)[1].lower()
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    if ext in ('.xlsx', '.xls'):
        df.to_excel(output_path, index=False)
    else:
        df.to_csv(output_path, index=False)
    return output_path


def hypermill_generator(output_path: str, conn) -> str:
    raise NotImplementedError("Generator hyperMILL non ancora implementato.")


def worknc_generator(output_path: str, conn) -> str:
    raise NotImplementedError("Generator WorkNC non ancora implementato.")


# ---------------------------------------------------------------
# FUNZIONI PUBBLICHE
# ---------------------------------------------------------------

def rileva_cam(filepath: str) -> str:
    """
    Rileva automaticamente il CAM dal file.
    Ritorna la chiave CAM_REGISTRY ('cimatron', 'hypermill', ecc.)
    o 'generico' se non riconosciuto.
    """
    ext = os.path.splitext(filepath)[1].lower()
    try:
        from cimatron_parser import is_cimatron_file
        if is_cimatron_file(filepath):
            return 'cimatron'
    except Exception:
        pass
    # TODO: aggiungere rilevamento hyperMILL, WorkNC quando si hanno file campione
    return 'generico'


def decodifica(filepath: str, cam: str = None, usa_agente: bool = True) -> dict:
    """
    Decodifica un file CAM -> struttura dati compatibile con DB master.

    Args:
        filepath:   percorso del file
        cam:        forza il CAM ('cimatron', 'hypermill', ecc.) — se None, autorileva
        usa_agente: usa l'agente AI per colonne non riconosciute

    Returns:
        dict con df (utensili), mapping, valori_categoria, ecc.
    """
    cam_key = cam or rileva_cam(filepath)
    if cam_key not in CAM_REGISTRY:
        cam_key = 'generico'

    fn_name = CAM_REGISTRY[cam_key]['decoder']['fn']
    fn_map  = {
        'cimatron_decoder':  cimatron_decoder,
        'hypermill_decoder': hypermill_decoder,
        'worknc_decoder':    worknc_decoder,
        'generico_decoder':  generico_decoder,
    }
    fn = fn_map.get(fn_name, generico_decoder)
    risultato = fn(filepath, usa_agente=usa_agente)
    risultato['cam_rilevato'] = cam_key
    return risultato


def genera(cam: str, output_path: str, conn) -> str:
    """
    Genera un file nel formato del CAM specificato dal DB master.

    Args:
        cam:         chiave CAM ('cimatron', 'hypermill', ecc.)
        output_path: percorso file di output
        conn:        connessione SQLite al DB master

    Returns:
        percorso del file generato
    """
    if cam not in CAM_REGISTRY:
        raise ValueError(f"CAM non registrato: {cam}")

    fn_name = CAM_REGISTRY[cam]['generator']['fn']
    fn_map  = {
        'cimatron_generator':  cimatron_generator,
        'hypermill_generator': hypermill_generator,
        'worknc_generator':    worknc_generator,
        'generico_generator':  generico_generator,
    }
    fn = fn_map.get(fn_name, generico_generator)
    return fn(output_path, conn)


def stato_sistema() -> list:
    """Ritorna lo stato di tutti i CAM registrati per la UI."""
    risultati = []
    for key, cam in CAM_REGISTRY.items():
        dec_stato = cam['decoder']['stato']
        gen_stato = cam['generator']['stato']
        dec_label, dec_color, dec_bg = STATI_LABEL.get(dec_stato, ('?','#000','#fff'))
        gen_label, gen_color, gen_bg = STATI_LABEL.get(gen_stato, ('?','#000','#fff'))
        risultati.append({
            'key':           key,
            'nome':          cam['nome'],
            'versioni':      ', '.join(cam['versioni']),
            'colore':        cam.get('logo_colore', '#666'),
            'decoder_stato': dec_stato,
            'decoder_label': dec_label,
            'decoder_color': dec_color,
            'decoder_bg':    dec_bg,
            'decoder_desc':  cam['decoder']['descrizione'],
            'decoder_fmt':   ', '.join(cam['decoder']['formati']),
            'generator_stato': gen_stato,
            'generator_label': gen_label,
            'generator_color': gen_color,
            'generator_bg':    gen_bg,
            'generator_desc':  cam['generator']['descrizione'],
            'generator_fmt':   ', '.join(cam['generator']['formati']),
        })
    return risultati
