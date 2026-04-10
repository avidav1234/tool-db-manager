"""
profile_manager.py
==================
Gestisce salvataggio, caricamento e aggiornamento dei profili di formato.
Ogni profilo e un file JSON in learner/profiles/
"""

import os
import json
from datetime import datetime

PROFILES_DIR = os.path.join(os.path.dirname(__file__), 'profiles')
os.makedirs(PROFILES_DIR, exist_ok=True)


def _profile_path(nome: str) -> str:
    safe = nome.replace(' ', '_').replace('/', '_').lower()
    if not safe.endswith('.json'):
        safe += '.json'
    return os.path.join(PROFILES_DIR, safe)


def salva_profilo(nome, software, versione, mapping, valori_categoria,
                  separatore=',', encoding='utf-8', righe_header=1, note='') -> str:
    profilo = {
        'nome': nome, 'software': software.lower(), 'versione': versione,
        'creato_il': datetime.now().isoformat(),
        'separatore': separatore, 'encoding': encoding,
        'righe_header': righe_header, 'note': note, 'colonne': {}
    }
    for campo_master, info in mapping.items():
        entry = {'campo_master': campo_master, 'tipo': info['tipo']}
        if info['tipo'] == 'categoria' and campo_master in valori_categoria:
            entry['valori'] = valori_categoria[campo_master]
        profilo['colonne'][info['colonna_file']] = entry
    path = _profile_path(nome)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(profilo, f, indent=2, ensure_ascii=False)
    print(f"Profilo salvato: {path}")
    return path


def carica_profilo(nome: str) -> dict:
    path = _profile_path(nome)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Profilo non trovato: {nome}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def lista_profili() -> list:
    profili = []
    for fname in sorted(os.listdir(PROFILES_DIR)):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(PROFILES_DIR, fname), 'r', encoding='utf-8') as f:
                p = json.load(f)
            profili.append({
                'file': fname, 'nome': p.get('nome', fname),
                'software': p.get('software', '?'), 'versione': p.get('versione', '?'),
                'creato_il': p.get('creato_il', '?'),
                'num_colonne': len(p.get('colonne', {})), 'note': p.get('note', ''),
            })
        except Exception:
            pass
    return profili


def elimina_profilo(nome: str) -> bool:
    path = _profile_path(nome)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def aggiorna_mapping(nome, mapping_aggiornato, valori_categoria) -> str:
    profilo = carica_profilo(nome)
    profilo['colonne'] = {}
    for campo_master, info in mapping_aggiornato.items():
        entry = {'campo_master': campo_master, 'tipo': info['tipo']}
        if info['tipo'] == 'categoria' and campo_master in valori_categoria:
            entry['valori'] = valori_categoria[campo_master]
        profilo['colonne'][info['colonna_file']] = entry
    profilo['aggiornato_il'] = datetime.now().isoformat()
    path = _profile_path(nome)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(profilo, f, indent=2, ensure_ascii=False)
    return path
