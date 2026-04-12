"""
plugins/_loader.py — Motore di caricamento plugin.
Scansiona plugins/, carica dinamicamente ogni plugin.py,
trova quello con confidenza piu alta per un dato file.
"""
import os, sys, importlib.util

_PLUGINS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PLUGINS_DIR)
if _ROOT not in sys.path: sys.path.insert(0, _ROOT)

_cache = None

def _scan_plugin_files():
    found = []
    for root, dirs, files in os.walk(_PLUGINS_DIR):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        if root == _PLUGINS_DIR: continue
        if 'plugin.py' in files:
            found.append(os.path.join(root, 'plugin.py'))
    return found

def _carica_plugin(plugin_path):
    try:
        rel = os.path.relpath(plugin_path, _ROOT)
        mod_name = rel.replace(os.sep,'.').replace('/','.')
        if mod_name.endswith('.py'): mod_name = mod_name[:-3]
        spec = importlib.util.spec_from_file_location(mod_name, plugin_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        from plugins._base import PluginCAM
        for name in dir(mod):
            obj = getattr(mod, name)
            try:
                if (isinstance(obj, type) and issubclass(obj, PluginCAM)
                        and obj is not PluginCAM
                        and getattr(obj,'versione','') not in ('','core')
                        and getattr(obj,'software','') != ''):
                    return obj()
            except: continue
    except Exception as e:
        print(f'[loader] Errore {plugin_path}: {e}')
    return None

def tutti_plugin(force_reload=False):
    global _cache
    if _cache is not None and not force_reload: return _cache
    plugins = [p for p in (_carica_plugin(f) for f in _scan_plugin_files()) if p]
    plugins.sort(key=lambda p: (p.software, p.versione))
    _cache = plugins
    return plugins

def trova_plugin(filepath, soglia=0.5):
    best, best_conf = None, 0.0
    for p in tutti_plugin():
        try: conf = p.rileva(filepath)
        except: conf = 0.0
        if conf > best_conf: best_conf=conf; best=p
    return (best, best_conf) if best_conf >= soglia else (None, 0.0)

def importa_con_plugin(filepath, db_path, dry_run=False):
    plugin, conf = trova_plugin(filepath)
    if not plugin:
        return {'errore': 'Nessun plugin trovato. Usa l agente per generarne uno.',
                'filepath': filepath}
    result = plugin.importa(filepath, db_path, dry_run=dry_run)
    result['plugin_usato'] = repr(plugin)
    result['confidenza'] = round(conf, 2)
    return result

def lista_plugin():
    return [{'software':p.software,'versione':p.versione,'estensioni':p.estensioni,
             'autore':p.autore,'note':p.note,'firma':p.FIRMA}
            for p in tutti_plugin()]
