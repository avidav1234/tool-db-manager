"""
orchestrator_agent.py
=====================
Agente multilivello per il learning di file CAM sconosciuti.

ARCHITETTURA:
  Livello 1 - Orchestratore (Sonnet): strategia, coordinamento, verifica finale
  Livello 2a - Analista struttura (Haiku): capisce il file nel suo insieme
  Livello 2b - Analista valori (Haiku): analizza ogni colonna singolarmente
  Livello 3 - Mapper (Haiku): produce il mapping in JSON strutturato
  Livello 4 - Verificatore (Sonnet): controllo logico, approva o corregge

RAZIONALE COSTI:
  - Haiku (L2/L3), task semplici, ripetitivi, ~20x piu economico di Sonnet
  - Sonnet (L1/L4), orchestrazione e verifica critica, usato il minimo indispensabile
  - Costo stimato per file, ~0.002-0.005 USD vs ~0.04 con solo Sonnet

RAZIONALE SICUREZZA:
  - Ogni livello produce output verificabile prima di procedere
  - L4 puo rifiutare e chiedere correzioni a L3
  - Tutto e tracciato nel log con timestamp
  - Decisioni motivate = audit trail
"""

import os
import sys
import json
import re
import urllib.request
import ssl
import time

_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, _BASE)

MODEL_ORCHESTRATORE = 'claude-sonnet-4-20250514'
MODEL_ANALISTA      = 'claude-haiku-4-5-20251001'
MODEL_MAPPERE = 'claude-haiku-4-5-20251001'
MODEL_VERIFICATORE  = 'claude-sonnet-4-20250514'

MASTER_FIELDS = {
    'codice_interno':       'Codice univoco utensile. Es: FRGSA-D10-R0.5-L75',
    'codice_catalogo':      'Codice catalogo fornitore',
    'descrizione':          'Testo descrittivo / commento',
    'num_magazzino':        'Posizione magazzino (intero)',
    'tipo':                 'FLAT/BALL/BULL/DRILL/TAP/REAM/SPOT',
    'tecnologia':          'Fresatura/Foratura/Speciale',
    'diametro_mm':          'Diametro tagliente mm (0.5-100)',
    'raggio_punta_mm':      'Raggio raccordo mm. 0=piatta, =diam/2=sferica',
    'angolo_punta_gradi':   'Angolo punta gradi (118-140 per punte)',
    'lunghezza_totale_mm':  'Lunghezza totale mm',
    'lunghezza_tagl_mm':    'Lunghezza utile/tagliente mm',
    'num_taglienti':        'Numero taglienti/flute (1-20, intero)',
    'nome_pinza':           'Nome portautensile. Es: HSK63A_D10',
    'lungh_presa_mm':       'Quanto utensile entra nella pinza mm',
    'fuori_pinza_mm':       'CRITCIOK: distanza punta->pinza mm. Per sicurezza lavorazione',
    'vc_default':           'Velocita taglio Vc m/min (10-2000)',
    'n_rpm':                'Velocita mandrino rpm (100-30000)',
    'fz_default':           'Avanzamento per dente mm/z (0.001-1.0, valori PICCOLI)',
    'vf_mm_min':            'Avanzamento tavola mm/min (50-10000, valori GRANDI)',
    'passo_z_default':      'Passata assiale ap mm',
    'passo_lat_default':    'Passata laterale ae mm',
    'vita_utensile':        'Vita utensile minuti/cicli',
    'dir_rotazione':        'CW=orario / CCW=antiorario',
    'refrigerante':         'OFF/Flood/Mist/Through/Air',
}


def _get_api_key(api_key=None):
    if api_key:
        return api_key
    k = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if k: return k
    for p in [os.path.join(_BASE, '.env'), os.path.join(os.path.dirname(__file__), '.env')]:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    for line in f:
                        if 'ANTHROPIC_API_KEY=' in line:
                            return line.split('=', 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    try:
        cfg = os.path.join(_BASE, 'config.json')
        if os.path.exists(cfg):
            with open(cfg) as f:
                return json.load(f).get('anthropic_api_key', '').strip()
    except Exception:
        pass
    return ''


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _chiama(prompt, model, api_key, max_tokens=1500, system=None):
    body = {'model': model, 'max_tokens': max_tokens,
            'messages': [{'role': 'user', 'content': prompt}]}
    if system: body['system'] = system
    payload = json.dumps(body).encode('utf-8')
    req = urllib.request.Request('https://api.anthropic.com/v1/messages',
        data=payload,
        headers={'Content-Type': 'application/json',
                 'x-api-key': api_key,
                 'anthropic-version': '2023-06-01'},
        method='POST')
    with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=45) as resp:
        return json.loads(resp.read())['content'][0]['text']


def _parse_json(testo):
    testo = re.sub(r'```[a-z]*\n?', '', testo.strip())
    testo = re.sub(r'```', '', testo).strip()
    try:
        return json.loads(testo)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', testo, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except Exception: pass
    return {}


# =====================================================================
# LIVELLO 2a - ANALISTA STRUTTURA (Haiku)
# =====================================================================

def _l2a_struttura(df, api_key, log) -> dict:
    log('L2a', 'Analisi struttura (%d colonne, %d righe)...' % (len(df.columns), len(df)))
    import pandas as pd
    info = {}
    for col in df.columns:
        serie = df[col].dropna()
        nums = pd.to_numeric(serie, errors='coerce').dropna()
        entry = {'n': len(serie), 'campioni': [str(v)[:20] for v in serie.head(3).tolist()]}
        if len(nums) / max(len(serie), 1) > 0.7:
            entry['tipo'] = 'num'
            entry['min'] = round(float(nums.min()), 3)
            entry['max'] = round(float(nums.max()), 3)
        elif serie.nunique() <= 12:
            entry['tipo'] = 'cat'
            entry['valori'] = [str(v) for v in serie.unique()[:10].tolist()]
        else:
            entry['tipo'] = 'txt'
        info[col] = entry
    fields_list = list(MASTER_FIELDS.keys())
    prompt = (
        'Sei un analista di file CAM. Analizza la struttura e rispondi SOLO in JSON valido.\n\n'
        'COLONNE:\n' + json.dumps(info, ensure_ascii=False) + '\n\n'
        'CAMPI MASTER: ' + str(fields_list) + '\n\n'
        'Rispondi SOLO con:\n'
        '{"software_cam":"nome","versione":"ver","lingua":"it/en/de",'
        '"tipo_contenuto":"utensili/portautensili/condizioni_taglio",'
        '"colonne_geometria":["col1"],"colonne_taglio":["col2"],'
        '"colonne_assemblaggio":["col3"],"colonne_da_ignorare":["col4"],'
        '"note":"osservazioni"}'
    )
    try:
        testo = _chiama(prompt, MODEL_ANALISTA, api_key, max_tokens=800)
        result = _parse_json(testo)
        log('L2a', 'Software: %s | Tipo: %s' % (result.get('software_cam', '?'), result.get('tipo_contenuto', '?')))
        return result
    except Exception as e:
        log('L2a', 'Errore: %s' % e)
        return {}


# =====================================================================
# LIVELLO 2b - ANALISTA VALORI (Haiku)
# =====================================================================

def _l2b_colonna(col_name, serie, contesto, api_key) -> dict:
    import pandas as pd
    nums = pd.to_numeric(serie, errors='coerce').dropna()
    campioni = [str(v) for v in serie.dropna().head(4).tolist()]
    stats = ''
    if len(nums) > 0:
        quasi_int = sum(1 for v in nums if abs(v - round(v)) < 0.0001)
        stats = 'min=%s max=%s media=%s quasi_interi=%s/%s' % (
            round(float(nums.min()), 3), round(float(nums.max()), 3),
            round(float(nums.mean()), 3), quasi_int, len(nums))
    fields_str = ', '.join(list(MASTER_FIELDS.keys()))
    prompt = (
        'File: %s\nColonna: "%s"\nValori: %s\n%s\n\n'
        'Campi disponibili: %s\n\n'
        'Rispondi SOLO con JSON:\n'
        '{"significato":"cosa rappresenta","campo_master_suggerito":"campo_o ignora",'
        '"confidenza":"alta/media/bassa","trasformazione":"nessuna/moltiplica_2/arrotonda/decodifica_tipo",'
        '"nota":"info importante"}'
    ) % (contesto.get('software_cam', 'CAM'), col_name, campioni, stats, fields_str)
    try:
        testo = _chiama(prompt, MODEL_ANALISTA, api_key, max_tokens=250)
        return _parse_json(testo)
    except Exception as e:
        return {'campo_master_suggerito': 'ignora', 'confidenza': 'bassa', 'nota': str(e)}


# =====================================================================
# LIVELLO 3 - MAPPER (Haiku)
# =====================================================================

def _l3_mapping(analisi, struttura, api_key, log) -> dict:
    """
    Mapping in batch da 15 colonne.
    Evita prompt enormi che causano JSON malformato.
    Con 100 colonne: 7 batch da 15 = 7 chiamate Haiku piccole e affidabili.
    """
    log('L3', 'Produzione mapping strutturato (batch da 15)...')
    fields_desc = '\n'.join('%s: %s' % (k, v) for k, v in MASTER_FIELDS.items())
    software = struttura.get('software_cam', 'sconosciuto')

    # Dividi le colonne in batch da 15
    colonne = list(analisi.keys())
    BATCH_SIZE = 15
    batches = [colonne[i:i+BATCH_SIZE] for i in range(0, len(colonne), BATCH_SIZE)]

    mapping_totale = {}
    campi_gia_mappati = set()  # evita duplicati tra batch
    ambigue = []
    warnings = []

    for idx_batch, batch in enumerate(batches):
        analisi_batch = {col: analisi[col] for col in batch}
        # Esclude campi gia mappati dai batch precedenti
        campi_disponibili = {k: v for k, v in MASTER_FIELDS.items() if k not in campi_gia_mappati}
        fields_batch = '\n'.join('%s: %s' % (k, v) for k, v in campi_disponibili.items())

        prompt = (
            'File: %s | Batch %d/%d (%d colonne)\n\n'
            'ANALISI COLONNE IN QUESTO BATCH:\n%s\n\n'
            'CAMPI MASTER ANCORA DISPONIBILI:\n%s\n\n'
            'Regole:\n'
            '- Ogni campo master mappato UNA sola volta in tutto il file\n'
            '- Colonna "Radius" senza Diameter = diametro_mm con moltiplica_2\n'
            '- Colonna "Gauge"/"Gauge Length" = fuori_pinza_mm\n'
            '- Se dubbio: ignora\n\n'
            'Rispondi SOLO con JSON (solo le colonne di questo batch):\n'
            '{"mapping":{"NomeCol":{"campo_master":"campo","confidenza":"alta/media/bassa",'
            '"trasformazione":"nessuna/moltiplica_2/arrotonda/decodifica_tipo","motivazione":"perche"}},'
            '"ambigue":["col"]}'
        ) % (software, idx_batch+1, len(batches),
             len(batch), json.dumps(analisi_batch, ensure_ascii=False),
             fields_batch)

        try:
            testo = _chiama(prompt, MODEL_MAPPER, api_key, max_tokens=1000)
            result = _parse_json(testo)
            batch_mapping = result.get('mapping', {})

            for col, info in batch_mapping.items():
                campo = info.get('campo_master', 'ignora')
                if campo == 'ignora' or campo in campi_gia_mappati:
                    continue
                mapping_totale[col] = info
                campi_gia_mappati.add(campo)

            ambigue.extend(result.get('ambigue', []))
        except Exception as e:
            log('L3', 'Batch %d/%d errore: %s' % (idx_batch+1, len(batches), e))

    n = sum(1 for v in mapping_totale.values() if v.get('campo_master','ignora') != 'ignora')
    log('L3', '%d colonne mappate su %d totali (%d batch)' % (n, len(colonne), len(batches)))

    return {'mapping': mapping_totale, 'colonne_ambigue': ambigue, 'warning': warnings}


# =====================================================================
# LIVELLO 4 - VERIFICATORE (Sonnet)
# =====================================================================

def _l4_verifica(mapping_raw, struttura, df, api_key, log) -> dict:
    log('L4', 'Verifica logica mapping...')
    import pandas as pd
    dettaglio = {}
    for col, info in mapping_raw.get('mapping', {}).items():
        if info.get('campo_master', 'ignora') == 'ignora': continue
        campioni = [str(v) for v in df[col].dropna().head(3).tolist()] if col in df.columns else []
        nums = pd.to_numeric(df[col].dropna(), errors='coerce').dropna() if col in df.columns else pd.Series()
        dettaglio[col] = {
            'campo_master': info.get('campo_master'),
            'confidenza': info.get('confidenza'),
            'trasformazione': info.get('trasformazione', 'nessuna'),
            'campioni': campioni,
            'min': round(float(nums.min()), 3) if len(nums) > 0 else None,
            'max': round(float(nums.max()), 3) if len(nums) > 0 else None,
        }
    prompt = (
        'Software: %s\n\nMAPPING DA VERIFICARE (con valori reali):\n%s\n\n'
        'RANGE DI RIFERIMENTO:\n'
        'diametro_mm: 0.5-100 | fuori_pinza_mm: 5-300 | fz_default: 0.001-0.5 (PICCOLI)\n'
        'vf_mm_min: 50-10000 (GRANDI) | vc_default: 10-1000 | n_rpm: 100-30000\n\n'
        'REGOLE SPECIALI (non sono errori):\n'
        '- "Radius" in WorkNC/hyperMILL = raggio utensile = diametro/2. '
        'SE non esiste colonna Diameter/Diametro separata, mappa Radius->diametro_mm con moltiplica_2. CORRETTO.\n'
        '- "Gauge" o "Gauge Length" = fuori_pinza_mm sempre. Non e critico se manca trasformazione.\n'
        '- "TipRadius" o "CornerRadius" = raggio_punta_mm. NON e diametro.\n\n'
        'VERIFICA SOLO: valori fuori range, Fz/Vf scambiati\n\n'
        'Rispondi SOLO con JSON:\n'
        '{"approvato":true,"score_confidenza":85,"errori_critici":[],'
        '"warning":[],"correzioni":{},"campi_mancanti_critici":[],"note_finali":"valutazione"}'
    ) % (struttura.get('software_cam', '?'), json.dumps(dettaglio, ensure_ascii=False))
    try:
        testo = _chiama(prompt, MODEL_VERIFICATORE, api_key, max_tokens=1500,
                         system='Sei un verificatore critico di mapping utensili CNC. Approva SOLO se logicamente corretto.')
        result = _parse_json(testo)
        stato = 'APPROVATO' if result.get('approvato') else 'RIFIUTATO'
        log('L4', '%s | Score: %s%% | Errori: %d | Warning: %d' % (
            stato, result.get('score_confidenza', 0),
            len(result.get('errori_critici', [])), len(result.get('warning', []))))
        for e in result.get('errori_critici', []):
            log('L4', '  ERRORE CRITICO: %s' % e)
        return result
    except Exception as e:
        log('L4', 'Errore verificatore: %s' % e)
        return {'approvato': False, 'errori_critici': [str(e)], 'score_confidenza': 0}


# =====================================================================
# LIVELLO 1 - ORCHESTRATORE
# =====================================================================

def orchestra_learning(df, api_key=None, nome_file='', log_callback=None, max_tentativi=2) -> dict:
    key = _get_api_key(api_key)
    if not key:
        return {'errore': 'API key non configurata', 'verificato': False, 'log': []}
    log_eventi = []
    token_stimati = 0
    def log(livello, msg):
        ts = time.strftime('%H:%M:%S')
        log_eventi.append({'ts': ts, 'livello': livello, 'msg': msg})
        if log_callback:
            log_callback(livello, msg)
        else:
            print('[%s][%s] %s' % (ts, livello, msg))
    log('L1', 'Inizio orchestrazione: %s (%d colonne, %d righe)' % (
        nome_file or livello, len(df.columns), len(df)))
    struttura = _l2a_struttura(df, key, log)
    token_stimati += 800
    log('L2b', 'Analisi valori in batch L2b (veloce)...')
    import pandas as _pd
    da_ignorare = set(struttura.get('colonne_da_ignorare', []))
    analisi = {}
    da_analizzare = []
    for col in df.columns:
        if col in da_ignorare:
            analisi[col] = {'campo_master_suggerito': 'ignora', 'confidenza': 'alta', 'nota': 'esclusa'}
        elif df[col].dropna().__len__() == 0:
            analisi[col] = {'campo_master_suggerito': 'ignora', 'confidenza': 'alta', 'nota': 'vuota'}
        else:
            da_analizzare.append(col)

    # Batch da 20 colonne - 5 chiamate invece di 100
    BATCH_L2B = 20
    fields_str = ', '.join(list(MASTER_FIELDS.keys()))
    for bi in range(0, len(da_analizzare), BATCH_L2B):
        batch = da_analizzare[bi:bi+BATCH_L2B]
        info_b = {}
        for col in batch:
            s = df[col].dropna()
            nums = _pd.to_numeric(s, errors='coerce').dropna()
            info_b[col] = {
                'campioni': [str(v)[:15] for v in s.head(3).tolist()],
                'tipo': 'num' if len(nums)/max(len(s),1)>0.7 else 'testo',
                'min': round(float(nums.min()),3) if len(nums)>0 else None,
                'max': round(float(nums.max()),3) if len(nums)>0 else None,
            }
        prompt = (
            'Software: %s. Analizza queste %d colonne e per ognuna indica il campo master.\n'
            'COLONNE:\n%s\n\nCAMPI: %s\n\n'
            'Rispondi SOLO JSON: {"analisi":{"Col":{"campo_master_suggerito":"campo","confidenza":"alta/media/bassa","trasformazione":"nessuna/moltiplica_2"}}}'
        ) % (struttura.get('software_cam','CAM'), len(info_b), json.dumps(info_b, ensure_ascii=False), fields_str)
        try:
            testo = _chiama(prompt, MODEL_ANALISTA, key, max_tokens=1000)
            res = _parse_json(testo)
            for col, inf in res.get('analisi', {}).items():
                if col in df.columns and inf:
                    analisi[col] = inf
        except Exception as e:
            for col in batch:
                analisi.setdefault(col, {'campo_master_suggerito':'ignora','confidenza':'bassa','nota':str(e)})
        token_stimati += 800
    for col in df.columns:
        analisi.setdefault(col, {'campo_master_suggerito':'ignora','confidenza':'bassa','nota':'no analisi'})
    log('L2b', 'Analisi completata: %d colonne' % len(analisi))
        return {'verificato': False, 'errore': 'Mapping non prodotto',
                'struttura': struttura, 'log': log_eventi, 'costo_stimato': token_stimati}
    verifica = None
    for tentativo in range(1, max_tentativi + 1):
        if verifica and verifica.get('correzioni'):
            log('L1', 'Applico %d correzioni dal tentativo %d' % (len(verifica['correzioni']), tentativo - 1))
            for col, corr in verifica['correzioni'].items():
                if col in mapping_raw['mapping']:
                    mapping_raw['mapping'][col].update(corr)
        verifica = _l4_verifica(mapping_raw, struttura, df, key, log)
        token_stimati += 2000
        if verifica.get('approvato'):
            log('L1', 'Mapping APPROVATO al tentativo %d' % tentativo)
            break
        elif tentativo < max_tentativi:
            log('L1', 'Tentativo %d fallito - preparo correzioni...' % tentativo)
        else:
            log('L1', 'Max tentativi - utilizzo mapping parziale')
    mapping_finale = dict(mapping_raw.get('mapping', {}))
    if verifica and verifica.get('correzioni'):
        for col, corr in verifica['correzioni'].items():
            if col in mapping_finale: mapping_finale[col].update(corr)
    profilo = {col: info for col, info in mapping_finale.items()
               if info.get('campo_master', 'ignora') != 'ignora'}
    log('L1', 'Profilo finale: %d colonne mappate | Token: ~%d | Costo: ~$%.4f' % (
        len(profilo), token_stimati, token_stimati / 1000 * 0.0025))
    return {'profilo': profilo, 'struttura': struttura, 'analisi_colonne': analisi,
            'verifica': verifica, 'verificato': verifica.get('approvato', False) if verifica else False,
            'score': verifica.get('score_confidenza', 0) if verifica else 0,
            'log': log_eventi, 'costo_stimato': token_stimati,
            'campi_mancanti': verifica.get('campi_mancanti_critici', []) if verifica else [],
            'warning': (mapping_raw.get('warning', []) + (verifica.get('warning', []) if verifica else []))}


def disponibile(api_key=None) -> bool:
    return bool(_get_api_key(api_key))


learning_multilivello = orchestra_learning


if __name__ == '__main__':
    import pandas as pd
    key = _get_api_key()
    if not key: print('API key non configurata.'); sys.exit(1)
    sample = os.path.join(_BASE, 'cam_samples', 'worknc_tools_sample.csv')
    if not os.path.exists(sample): print('File campione non trovato:', sample); sys.exit(1)
    print('Test agente multilivello - WorkNC sample')
    print('=' * 50)
    df = pd.read_csv(sample)
    r = orchestra_learning(df, key, 'worknc_tools_sample.csv')
    print('\nRISULTATO:')
    print('  Verificato: %s' % r['verificato'])
    print('  Score:      %s%%' % r['score'])
    print('  Mappati:    %d campi' % len(r.get('profilo', {})))
    print('  Token:      ~%d' % r['costo_stimato'])
    print('  Costo:      ~$%.4f' % (r['costo_stimato'] / 1000 * 0.0025))
    print('\nMAPPING:')
    for col, info in r.get('profilo', {}).items():
        print('  %-22s -> %-25s [%s] %s' % (
            col, info['campo_master'], info['confidenza'],
            info.get('trasformazione', 'nessuna')))
