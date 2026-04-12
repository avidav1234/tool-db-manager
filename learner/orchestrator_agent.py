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
MODEL_ANALISTAE = 'claude-haiku-4-5-20251001'
MODEL_VERIFICATORE  = 'claude-sonnet-4-20250514'

MASTER_FIELDS = {
    # Identificazione
    'alias':                    'NOME OFFICINA - indipendente dal CAM (Cimatron=Commento, Hypermill=Tool ID)',
    'codice_interno':           'Codice univoco utensile (obbligatorio)',
    'descrizione':              'Descrizione tecnica libera',
    'sito_web':                 'URL scheda tecnica fornitore',
    'num_magazzino':            'Posizione magazzino utensili',
    'codice_catalogo':          'Codice catalogo fornitore',
    # Classificazione
    'tipo':                     'FLAT/BALL/BULL/DRILL/TAP/REAM/SPOT/TAPER/THREAD',
    'tecnologia':               'Fresatura/Foratura/Filettatura/Alesatura/Tornitura',
    # Geometria principale
    'diametro_mm':              'Diametro tagliente mm (obbligatorio)',
    'raggio_punta_mm':          'Raggio raccordo / corner radius mm',
    'angolo_punta_gradi':       'Angolo punta gradi',
    'lunghezza_totale_mm':      'Lunghezza totale utensile mm',
    'lunghezza_tagl_mm':        'Lunghezza utile / tagliente mm',
    'lunghezza_tagl2_mm':       'Lunghezza tagliente secondaria mm',
    'num_taglienti':            'Numero taglienti / flute',
    'conico':                   'Flag conico 0/1',
    'angolo_conico_gradi':      'Angolo conicita gradi',
    # Stelo
    'diam_stelo_mm':            'Diametro gambo / stelo mm',
    'diam_stelo_sup_mm':        'Diametro superiore stelo mm',
    'diam_stelo_inf_mm':        'Diametro inferiore stelo mm',
    'lungh_cono_stelo_mm':      'Lunghezza cono stelo mm',
    'lungh_libera_stelo_mm':    'Lunghezza libera stelo mm',
    'angolo_cono_stelo_gradi':  'Angolo cono stelo gradi',
    # Portautensile
    'nome_pinza':               'Codice portautensile / holder',
    'lungh_presa_mm':           'Lunghezza presa in pinza mm',
    'fuori_pinza_mm':           'Distanza punta-pinza mm (gauge length)',
    # Parametri taglio
    'avanzamento_default':      'Avanzamento Vf mm/min (tipico 500-8000)',
    'rotazione_default':        'Rotazione mandrino RPM',
    'vc_default':               'Velocita taglio Vc m/min',
    'fz_default':               'Avanzamento per dente Fz mm/z (0.001-5.0)',
    'passo_z_default':          'Passo assiale ap mm',
    'passo_lat_default':        'Passo laterale ae mm',
    'tolleranza_default':       'Tolleranza lavorazione mm',
    'vita_utensile':            'Vita utensile minuti/colpi',
    'dir_rotazione':            'Direzione rotazione CW/CCW',
    'refrigerante':             'Tipo refrigerante OFF/FLOOD/MIST/AIR/THROUGH',
    # --- Filettatura
    'passo_mm':              'Passo filetto mm',
    'num_filetti':           'Numero filetti/starts',
    # --- Profilo avanzato
    'diam_libero_mm':        'Diametro libero / stylus mm',
    'altezza_cilindro_mm':   'Altezza cilindro mm',
    'diam_base_piatta_mm':   'Diametro base piatta mm',
    'raggio_punta2_mm':      'Raggio punta tip mm',
    'raggio_superiore_mm':   'Raggio superiore mm',
    'raggio_profilo_mm':     'Raggio profilo sagomato mm',
    'lunghezza_conica_mm':   'Lunghezza zona conica mm',
    'centro_arco_y_mm':      'Centro arco Y profilo mm',
    'altezza_raggio_sup_mm': 'Altezza raggio superiore mm',
    # --- Stelo gambo
    'diam_gambo1_mm':        'Diametro gambo mm',
    'diam_gambo_top_mm':     'Diametro gambo top mm',
    'diam_gambo_bot_mm':     'Diametro gambo bottom mm',
    'lunghezza_gambo_mm':    'Lunghezza cono gambo mm',
    # --- Portautensile/magazzino
    'nome_portautensile':    'Nome porta utensile / holder',
    'nome_materiale_pu':     'Materiale porta utensile',
    'numero_magazzino':      'Numero magazzino CNC',
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


def _chiama(prompt, model, api_key, max_tokens=1500, system=None, _retry=4):
    import time
    body = {'model': model, 'max_tokens': max_tokens,
            'messages': [{'role': 'user', 'content': prompt}]}
    if system: body['system'] = system
    payload = json.dumps(body).encode('utf-8')
    for attempt in range(_retry):
        try:
            req = urllib.request.Request('https://api.anthropic.com/v1/messages',
                data=payload,
                headers={'Content-Type': 'application/json',
                         'x-api-key': api_key,
                         'anthropic-version': '2023-06-01'},
                method='POST')
            with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=60) as resp:
                return json.loads(resp.read())['content'][0]['text']
        except Exception as e:
            if '429' in str(e) and attempt < _retry - 1:
                wait = 20 * (attempt + 1)
                print(f'    [429 rate limit] attendo {wait}s (tentativo {attempt+1}/{_retry})...', flush=True)
                time.sleep(wait)
            else:
                raise


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
            '- "Avanz." con valori >100 = avanzamento_default (Vf mm/min), NON fz_default\n'
            '- "Fz" con valori 0.001-5.0 = fz_default (mm/dente), valori corretti\n'
            '- "Lungh. Libera" nella sezione pinza (3103) = fuori_pinza_mm\n'
            '- "Lungh. Libera Stelo" (2207) = lungh_libera_stelo_mm (diverso da fuori_pinza)\n'
            '- Codici 420301/CW = dir_rotazione, codici 420401-420405 = refrigerante\n'
            '- Due colonne con valori identici (es. Lunghezza Utile e Lungh. Tagliente) vanno a campi diversi\n'
            '- Se dubbio: ignora\n\n'
            'Rispondi SOLO con JSON (solo le colonne di questo batch):\n'
            '{"mapping":{"NomeCol":{"campo_master":"campo","confidenza":"alta/media/bassa",'
            '"trasformazione":"nessuna/moltiplica_2/arrotonda/decodifica_tipo","motivazione":"perche"}},'
            '"ambigue":["col"]}'
        ) % (software, idx_batch+1, len(batches),
             len(batch), json.dumps(analisi_batch, ensure_ascii=False),
             fields_batch)

        try:
            testo = _chiama(prompt, MODEL_ANALISTA, api_key, max_tokens=1000)
            result = _parse_json(testo)
            batch_mapping = result.get('mapping', {})

            if not batch_mapping:
                log('L3', 'Batch %d/%d: mapping vuoto dalla risposta del modello' % (idx_batch+1, len(batches)))
                log('L3', 'Risposta ricevuta: %s' % str(testo)[:200])
            else:
                log('L3', 'Batch %d/%d: %d colonne ricevute' % (idx_batch+1, len(batches), len(batch_mapping)))

            for col, info in batch_mapping.items():
                campo = info.get('campo_master', 'ignora')
                if campo == 'ignora' or campo not in MASTER_FIELDS:
                    continue
                if campo in campi_gia_mappati:
                    continue
                col_norm = col.strip().lower()
                analisi_keys_norm = {k.strip().lower(): k for k in analisi.keys()}
                if col_norm not in analisi_keys_norm:
                    continue
                mapping_totale[col] = info
                campi_gia_mappati.add(campo)

            ambigue.extend(result.get('ambigue', []))
        except Exception as e:
            log('L3', 'Batch %d/%d errore CRITICO: %s' % (idx_batch+1, len(batches), str(e)))
            log('L3', 'Testo ricevuto dal modello: %s' % str(testo)[:300] if 'testo' in dir() else 'N/A')

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
        }
    prompt = (
        'Software: %s\n\nMAPPING DA VERIFICARE (con valori reali):\n%s\n\n'
        'RANGE DI RIFERIMENTO:\n'
        'diametro_mm: 0.5-100 | fuori_pinza_mm: 5-300 | fz_default: 0.001-5.0 (anche >1 e normale)\n'
        'vf_mm_min: 50-10000 (GRANDI) | vc_default: 10-1000 | n_rpm: 100-30000\n'
        'ATTENZIONE: i "campioni" sono VALORI DAL FILE, non range di validazione.\n'
        'fz tra 0.001 e 5.0 e SEMPRE VALIDO (fz puo essere anche 1 o maggiore per frese grandi). NON segnalare mai come errore.\n'
        'Segnala SOLO se fz > 10.0 (impossibile fisicamente) o vf < 1.\n\n'
        'REGOLE SPECIALI (non sono errori):\n'
        '- "Radius" in WorkNC/hyperMILL = raggio utensile = diametro/2. '
        'SE non esiste colonna Diameter/Diametro separata, mappa Radius->diametro_mm con moltiplica_2. CORRETTO.\n'
        '- "Gauge" o "Gauge Length" = fuori_pinza_mm sempre. Non e critico se manca trasformazione.\n'
        '- "TipRadius" o "CornerRadius" = raggio_punta_mm. NON e diametro.\n\n'
        'REGOLA duplicazione: piu colonne possono avere valori identici e mappare allo stesso campo: NON e errore critico, e normale nelle librerie CAM.\n'
        'VERIFICA SOLO: valori palesemente impossibili, Fz/Vf con fattore 1000x di differenza\n\n'
        'Rispondi SOLO con JSON:\n'
        '{"approvato":true,"score_confidenza":85,"errori_critici":[],'
        '"warning":[],"correzioni":{},"campi_mancanti_critici":[],"note_finali":"valutazione"}'
    ) % (struttura.get('software_cam', '?'), json.dumps(dettaglio, ensure_ascii=False))
    try:
        testo = _chiama(prompt, MODEL_VERIFICATORE, api_key, max_tokens=1500,
                         system=('Sei un verificatore di mapping utensili CNC. '
                          'Approva se il mapping e logicamente ragionevole. '
                          'fz compreso tra 0.001 e 1.2 e SEMPRE valido per frese standard: non e mai un errore. '
                          'Segnala errore solo per valori palesemente impossibili (es. fz>5, diametro>500).'))
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



# ===== WORKNC FAST PATH (deterministico, 0 token) =====
_WORKNC_MAP = {
    'name':         ('codice_interno', None),
    'type':         ('tipo', None),
    'radius':       ('diametro_mm', 'moltiplica_2'),
    'diameter':     ('diametro_mm', 'float'),
    'tipradius':    ('raggio_punta_mm', 'float'),
    'cornerradius': ('raggio_punta_mm', 'float'),
    'length':       ('lunghezza_totale_mm', 'float'),
    'usefullength': ('lunghezza_tagl_mm', 'float'),
    'teeth':        ('num_taglienti', 'int'),
    'flutes':       ('num_taglienti', 'int'),
    'material':     ('materiale', None),
    'vc':           ('vc_default', 'float'),
    'fz':           ('fz_default', 'float'),
    'rpm':          ('rotazione_default', 'float'),
    'feed':         ('avanzamento_default', 'float'),
    'vf':           ('avanzamento_default', 'float'),
    'ap':           ('passo_z_default', 'float'),
    'ae':           ('passo_lat_default', 'float'),
    'gauge':        ('fuori_pinza_mm', 'float'),
    'gaugelength':  ('fuori_pinza_mm', 'float'),
    'holderref':    ('nome_pinza', None),
    'holder':       ('nome_pinza', None),
    'notes':        ('descrizione', None),
    'comment':      ('descrizione', None),
}

def _worknc_fast_path(df, nome_file, log):
    cols_low = {str(c).strip().lower() for c in df.columns}
    WORKNC_SIGNATURE = {'name', 'radius', 'length', 'teeth', 'fz', 'rpm', 'gauge'}
    match = len(WORKNC_SIGNATURE & cols_low)
    if match < 3:
        return None
    log('L1', 'Rilevato WorkNC (match=%d) - fast path deterministico' % match)

    def _cast(v, t):
        if v is None or str(v).strip() in ('', 'nan', 'None'): return None
        if t in ('float', 'moltiplica_2'):
            try:
                val = float(str(v).replace(',', '.'))
                return round(val * 2, 6) if t == 'moltiplica_2' else val
            except: return None
        if t == 'int':
            try: return int(round(float(str(v).replace(',', '.'))))
            except: return None
        return str(v).strip() or None

    cols_map = {str(c).strip().lower(): str(c).strip() for c in df.columns}
    mapping_result = {}
    for col_low, col_orig in cols_map.items():
        if col_low in _WORKNC_MAP:
            campo, tipo = _WORKNC_MAP[col_low]
            mapping_result[col_orig] = {
                'campo_master': campo,
                'confidenza': 'alta',
                'trasformazione': tipo or 'nessuna',
                'motivazione': 'WorkNC fast path deterministico'
            }

    records = []
    for _, row in df.iterrows():
        rec = {}
        for col_low, col_orig in cols_map.items():
            if col_low not in _WORKNC_MAP: continue
            campo, tipo = _WORKNC_MAP[col_low]
            v = _cast(row.get(col_orig), tipo)
            if v is not None: rec[campo] = v
        if rec.get('codice_interno'): records.append(rec)

    log('L1', 'WorkNC: %d colonne mappate, %d utensili' % (len(mapping_result), len(records)))
    return {
        'mapping': mapping_result, 'records': records,
        'colonne_ambigue': [], 'warning': [], 'metodo': 'worknc_fast_path'
    }

# ===== CIMATRON FAST PATH (deterministico, 0 token) =====
_CIMA_MAP = {
    '1101':('codice_interno',None),'1102':('descrizione',None),'1103':('sito_web',None),
    '1201':('num_magazzino',None),'2103':('codice_catalogo',None),
    '2105':('diametro_mm','float'),'2106':('raggio_punta_mm','float'),
    '2108':('lunghezza_totale_mm','float'),'2109':('lunghezza_tagl_mm','float'),
    '2110':('lunghezza_tagl2_mm','float'),'2111':('conico','int'),
    '2112':('angolo_conico_gradi','float'),'2113':('angolo_punta_gradi','float'),
    '2118':('diam_stelo_mm','float'),'2202':('diam_stelo_sup_mm','float'),
    '2203':('diam_stelo_inf_mm','float'),'2205':('angolo_cono_stelo_gradi','float'),
    '2206':('lungh_cono_stelo_mm','float'),'2207':('lungh_libera_stelo_mm','float'),
    '3101':('nome_pinza',None),'3102':('lungh_presa_mm','float'),
    '3103':('fuori_pinza_mm','float'),'4101':('avanzamento_default','float'),
    '4102':('rotazione_default','float'),'4103':('vc_default','float'),
    '4104':('fz_default','float'),'4106':('num_taglienti','int'),
    '4202':('vita_utensile','int'),'4203':('dir_rotazione',None),
    '4204':('refrigerante',None),'5101':('passo_z_default','float'),
    '5102':('passo_lat_default','float'),'5106':('tolleranza_default','float'),
}
_CIMA_TECNOLOGIA={'210101':'Fresatura','210102':'Foratura','210103':'Filettatura',
    '210104':'Alesatura','210105':'Barenatura','210106':'Tornitura'}
_CIMA_TIPO={'210201':'FLAT','210202':'BALL','210203':'BULL','210204':'DRILL',
    '210205':'TAP','210206':'REAM','210207':'SPOT','210208':'THREAD',
    '210209':'TAPER','210210':'FORM','210211':'LOLLIPOP'}
_CIMA_DIR={'420301':'CW','420302':'CCW'}
_CIMA_REFR={'420401':'OFF','420402':'FLOOD','420403':'MIST','420404':'AIR','420405':'THROUGH'}

def _cimatron_fast_path(df, nome_file, log):
    # Rilevamento da ID numerici O nomi italiani
    cols_set = set(str(c).strip() for c in df.columns)
    id_match = len(set(['1101','2105','3103','4101','4104','4104','4102','2109','3101']) & cols_set)
    CIMA_NOMI = {'Nome Utensile','Diametro','Raggio Base','Lunghezza Totale Ut.',
                 'Lunghezza Utile','Lungh. Tagliente','Nome Pinza','Lungh. Libera',
                 'Avanz.','Rotaz.','Fz','Vt','Denti','Tecnologia','Punta/Tipo'}
    nome_match = len(CIMA_NOMI & cols_set)
    if id_match < 5 and nome_match < 4:
        return None
    log('L1', f'Rilevato Cimatron (id_match={id_match}, nome_match={nome_match}) - fast path deterministico')
    cols = cols_set  # per compatibilita con il codice successivo
    def _cast(v, t):
        if v is None or str(v).strip() in ('','nan','None'): return None
        if t == 'float':
            try: return float(str(v).replace(',','.'))
            except: return None
        if t == 'int':
            try: return int(round(float(str(v).replace(',','.'))))
            except: return None
        return str(v).strip() or None
    records = []
    for _, row in df.iterrows():
        rec = {}
        for cid,(campo,tipo) in _CIMA_MAP.items():
            if cid not in cols: continue
            v = row.get(cid)
            sv = str(v).strip() if v is not None else ''
            if cid == '2101': v = _CIMA_TECNOLOGIA.get(sv, sv) or None
            elif cid == '2102': v = _CIMA_TIPO.get(sv, sv) or None
            elif cid == '4203': v = _CIMA_DIR.get(sv, sv) or None
            elif cid == '4204': v = _CIMA_REFR.get(sv, sv) or None
            else: v = _cast(v, tipo)
            if v is not None: rec[campo] = v
        if rec.get('codice_interno'): records.append(rec)
    # Se nessun record trovato con ID, prova con nomi italiani
    if not records and nome_match >= 4:
        NOMI_MAP = {
            # Nomi CORTI (riga 7 CSV Cimatron, versione italiana abbreviata)
            'Nome Utensile':           'codice_interno',
            'Commento':                'alias',            # Commento Cimatron = NOME OFFICINA
            'Sito':                    'sito_web',
            'Sito web':                'sito_web',
            'Numero Ut.':              'num_magazzino',
            'Numero Magazzino':        'num_magazzino',
            'N. Mag.':                 'num_magazzino',
            'Nome Catalogo':           'codice_catalogo',
            # Classificazione
            'Tecnologia':              'tecnologia',
            'Punta/Tipo':              'tipo',
            # Geometria
            'Diametro':                'diametro_mm',
            'Raggio Base':             'raggio_punta_mm',
            'Angolo Punta':            'angolo_punta_gradi',
            'Lunghezza Totale Ut.':    'lunghezza_totale_mm',
            'Lunghezza Utile':         'lunghezza_tagl_mm',
            'Lungh. Tagliente':        'lunghezza_tagl2_mm',
            'Lunghezza Taglio secondaria': 'lunghezza_tagl2_mm',
            'Conico':                  'conico',
            # Angolo conicita con e senza accento
            'Angolo Conicit\u00e0':   'angolo_conico_gradi',
            'Angolo Conicita':         'angolo_conico_gradi',
            # Stelo
            'Diametro Gambo':          'diam_stelo_mm',
            'Diametro Gambo/Stelo':    'diam_stelo_mm',
            'Dia. Superiore Stelo':    'diam_stelo_sup_mm',
            'Diametro Stelo Sup':      'diam_stelo_sup_mm',
            'Dia. Inferiore Stelo':    'diam_stelo_inf_mm',
            'Diametro Stelo Inf':      'diam_stelo_inf_mm',
            'Lungh. Cono Stelo':       'lungh_cono_stelo_mm',
            'Lunghezza Cono Stelo':    'lungh_cono_stelo_mm',
            'Lungh. Libera Stelo':     'lungh_libera_stelo_mm',
            'Lunghezza Libera Stelo':  'lungh_libera_stelo_mm',
            'Angolo Cono Stelo':       'angolo_cono_stelo_gradi',
            # Portautensile
            'Nome Pinza':              'nome_pinza',
            'Nome Porta Utensile':     'nome_pinza',
            'Lunghezza Presa':         'lungh_presa_mm',
            'Lungh. Presa':            'lungh_presa_mm',
            'Lungh. Libera':           'fuori_pinza_mm',
            'Lunghezza Libera':        'fuori_pinza_mm',
            # Parametri taglio - nomi CORTI (parser manuale)
            'Avanz.':                  'avanzamento_default',
            'Rotaz.':                  'rotazione_default',
            'Vt':                      'vc_default',
            'Fz':                      'fz_default',
            'Denti':                   'num_taglienti',
            'Vita Utensile':           'vita_utensile',
            'Dir Rotaz.':              'dir_rotazione',
            'Refrigerante':            'refrigerante',
            'Passo in Z':              'passo_z_default',
            'Passo Laterale':          'passo_lat_default',
            'Tolleranza':              'tolleranza_default',
            # Parametri taglio - nomi ESTESI (cimatron_parser.leggi_cimatron_zip)
            'Avanzamento Vf mm/min':   'avanzamento_default',
            'Rotazione RPM':           'rotazione_default',
            'Velocita taglio Vc m/min':'vc_default',
            'Avanzamento per dente Fz mm/z': 'fz_default',
            'Numero denti/taglienti':  'num_taglienti',
            'Vita utensile':           'vita_utensile',
            'Direzione mandrino':      'dir_rotazione',
            'Tipo refrigerante':       'refrigerante',
            'Passo laterale':          'passo_lat_default',
            # Filettatura
            'Passo':                   'passo_mm',
            'Numero Filetti':          'num_filetti',
            # Numero magazzino
            'Numero Magazzino':        'numero_magazzino',
            'Numero Ut.':              'numero_magazzino',
            # Profilo geometrico avanzato
            'Diametro Stelo Libero':   'diam_libero_mm',
            'Altezza Cilindro':        'altezza_cilindro_mm',
            'Diametro Piatto Inferiore':'diam_base_piatta_mm',
            'Centro Y Arco Profilo':   'centro_arco_y_mm',
            'Raggio Punta':            'raggio_punta2_mm',
            'Raggio Superiore':        'raggio_superiore_mm',
            'Lunghezza Sformo':        'lunghezza_conica_mm',
            'Altezza Raggio Superiore':'altezza_raggio_sup_mm',
            'Raggio Profilo':          'raggio_profilo_mm',
            # Stelo gambo
            'Stelo':                   'diam_gambo1_mm',
            'Diametro Gambo Top':      'diam_gambo_top_mm',
            'Diametro Gambo Bottom':   'diam_gambo_bot_mm',
            'Lunghezza Cono Gambo':    'lunghezza_gambo_mm',
            # Portautensile
            'Nome Porta Utensile':     'nome_portautensile',
            'Nome Materiale':          'nome_materiale_pu',
        }
        TIPO_N = {
                  'diametro_mm':'float','raggio_punta_mm':'float','angolo_punta_gradi':'float',
                  'lunghezza_totale_mm':'float','lunghezza_tagl2_mm':'float',
                  'angolo_conico_gradi':'float','diam_stelo_sup_mm':'float','diam_stelo_inf_mm':'float',
                  'lungh_cono_stelo_mm':'float','lungh_libera_stelo_mm':'float',
                  'angolo_cono_stelo_gradi':'float','lungh_presa_mm':'float',
                  'avanzamento_default':'float','rotazione_default':'float','vc_default':'float',
                  'fz_default':'float','tolleranza_default':'float','passo_lat_default':'float',
                  'vita_utensile':'int','num_taglienti':'int','conico':'int','num_magazzino':'int',
                  'lunghezza_totale_mm':'float',
                  'lunghezza_tagl_mm':'float','lunghezza_tagl2_mm':'float','conico':'int',
                  'diam_stelo_mm':'float','lungh_presa_mm':'float','fuori_pinza_mm':'float',
                  'avanzamento_default':'float','rotazione_default':'float','vc_default':'float',
                  'fz_default':'float','num_taglienti':'int','passo_z_default':'float',
                  'passo_lat_default':'float'}
        for _, row in df.iterrows():
            rec = {}
            for nome, campo in NOMI_MAP.items():
                if nome not in cols_set: continue
                v = row.get(nome)
                if v is None or str(v).strip() in ('','nan','None'): continue
                t = TIPO_N.get(campo,'string')
                cv = _cast(v, t)
                if cv is not None: rec[campo] = cv
            if rec.get('codice_interno') or rec.get('diametro_mm'):
                records.append(rec)
    log('L1', 'Fast path: %d utensili x campi | Token: 0 | Costo: $0.0000' % len(records))
    # Costruisce mapping con le colonne REALI del DataFrame come chiavi
    if id_match >= 5:
        # Colonne sono ID numerici: usa _CIMA_MAP
        mapping = {cid: {'campo_master': cm, 'confidenza': 'alta', 'trasformazione': 'nessuna'}
                   for cid, (cm, _) in _CIMA_MAP.items() if cid in set(str(c) for c in df.columns)}
    else:
        # Colonne sono nomi italiani: usa NOMI_MAP
        mapping = {nome: {'campo_master': campo, 'confidenza': 'alta', 'trasformazione': 'nessuna'}
                   for nome, campo in NOMI_MAP.items() if nome in set(str(c) for c in df.columns)}
    n_campi = len(mapping)
    score = min(100, int(n_campi / 32 * 100))
    log('L1', 'Fast path: %d utensili, %d campi mappati, score=%d%%' % (len(records), n_campi, score))
    return {'verificato': True, 'software_cam': 'Cimatron', 'records': records,
            'mapping': {'mapping': mapping}, 'log': [], 'costo_stimato': 0,
            'score': score, 'metodo': 'deterministico', 'n_campi': n_campi}


# =====================================================================
# SINGLE-SHOT MAPPING (Sonnet) - sostituisce L2+L3+L4
# =====================================================================

def _sonnet_mapping_singleshot(df, nome_file, api_key, log, profili_dir=None):
    """
    Mapping completo in una singola chiamata Sonnet.
    Vede valori reali delle colonne + few-shot dai profili salvati.
    """
    import pandas as _pd, os as _os, json as _json

    log('L2', 'Analisi single-shot Sonnet (%d colonne, %d righe)...' % (len(df.columns), len(df)))

    # Profilo colonne con valori reali
    col_profiles = {}
    has_diameter = any(c.lower() in ('diameter','diametro') for c in df.columns)
    for col in df.columns:
        serie = df[col].dropna()
        if len(serie) == 0:
            col_profiles[col] = {'tipo': 'vuota', 'campioni': []}
            continue
        campioni = [str(v) for v in serie.head(5).tolist()]
        nums = _pd.to_numeric(serie, errors='coerce').dropna()
        col_profiles[col] = {
            'campioni': campioni,
            'tipo': 'numerico' if len(nums) > len(serie) * 0.7 else 'testo',
            'min': round(float(nums.min()), 4) if len(nums) > 0 else None,
            'max': round(float(nums.max()), 4) if len(nums) > 0 else None,
        }

    # Few-shot dai profili salvati
    few_shot = ''
    try:
        pdir = profili_dir or _os.path.join(_os.path.dirname(__file__), '..', 'profili')
        if _os.path.exists(pdir):
            pfiles = sorted(_os.listdir(pdir))[:3]
            esempi = []
            for pf in pfiles:
                if not pf.endswith('.json'): continue
                with open(_os.path.join(pdir, pf)) as fp:
                    p = _json.load(fp)
                m = p.get('mapping', {})
                if not m: continue
                ex = ['Profilo %s (%s):' % (p.get('nome','?'), p.get('software','?'))]
                for c, info in list(m.items())[:10]:
                    campo = info.get('campo_master','ignora') if isinstance(info,dict) else str(info)
                    if campo != 'ignora':
                        ex.append('  %s -> %s' % (c, campo))
                esempi.append('\n'.join(ex))
            if esempi:
                few_shot = '\n\nMAPPING GIA VALIDATI (usa come riferimento):\n' + '\n\n'.join(esempi)
    except Exception:
        pass

    fields_desc = '\n'.join('  %s: %s' % (k, v) for k, v in MASTER_FIELDS.items())
    radius_note = 'NOTA: il file HA una colonna Diameter separata -> Radius e raggio_punta_mm' if has_diameter else 'NOTA: il file NON ha colonna Diameter -> Radius/Raggio e diametro_mm con moltiplica_2'

    prompt = """Sei esperto di database utensili CNC. Mappa le colonne di questo file CAM.

FILE: %s
%s

COLONNE (con valori reali):
%s

CAMPI DB MASTER:
%s
%s

REGOLE:
- Valori 1000-30000 interi = rotazione_default (RPM)
- Valori 50-10000 grandi = avanzamento_default (Feed mm/min)
- Valori 0.001-5.0 piccoli float = fz_default (mm/dente)
- Valori 10-500 = vc_default (m/min)
- Nome/codice utensile = codice_interno
- Alias officina/commento libero = alias
- Gauge/Gauge Length/Lungh.Libera portautensile = fuori_pinza_mm
- Dubbio: ignora

Rispondi SOLO JSON:
{"software_rilevato":"nome","mapping":{"NomeColonna":{"campo_master":"campo","confidenza":"alta/media/bassa","trasformazione":"nessuna/moltiplica_2/float/int","motivazione":"..."}},"colonne_ignorate":["c1"]}""" % (
        nome_file or 'file', radius_note,
        _json.dumps(col_profiles, ensure_ascii=False),
        fields_desc, few_shot
    )

    try:
        testo = _chiama(prompt, 'claude-sonnet-4-5', api_key, max_tokens=4096,
                        system='Esperto CNC. Rispondi SOLO JSON valido, nessun testo extra.')
        result = _parse_json(testo)
        mapping = result.get('mapping', {})
        mapping_valido = {
            col: info for col, info in mapping.items()
            if isinstance(info, dict)
            and info.get('campo_master','ignora') != 'ignora'
            and info.get('campo_master') in MASTER_FIELDS
            and col in list(df.columns)
        }
        sw = result.get('software_rilevato', 'sconosciuto')
        tok_est = len(prompt) // 4 + 1000
        log('L1', 'Software: %s | %d/%d colonne | Token: ~%d | Costo: ~$%.4f' % (
            sw, len(mapping_valido), len(df.columns), tok_est, tok_est * 0.000015))
        return {
            'mapping': mapping_valido,
            'software_cam': sw,
            'colonne_ambigue': result.get('colonne_ignorate', []),
            'warning': [], 'metodo': 'sonnet_singleshot',
            'approvato': True, 'score_confidenza': 88,
        }
    except Exception as e:
        log('L2', 'Errore single-shot: %s' % str(e))
        return {'mapping': {}, 'colonne_ambigue': [], 'warning': [str(e)], 'approvato': False}

def orchestra_learning(df, api_key=None, nome_file='', log_callback=None, max_tentativi=2) -> dict:
    key = _get_api_key(api_key)
    if not key:
        return {'errore': 'API key non configurata', 'verificato': False, 'log': []}
    log_eventi = []
    token_stimati = 0
    def log(livello, msg):
        ts = time.strftime('%H:%M:%S')
        log_eventi.append({'ts': ts, 'livello': livello, 'msg': msg})
        if log_callback: log_callback(livello, msg)
        else: print('[%s][%s] %s' % (ts, livello, msg))

    log('L1', 'Inizio: %s (%d colonne, %d righe)' % (nome_file or 'file', len(df.columns), len(df)))

    # Fast path WorkNC (deterministico, 0 token)
    _worknc_result = _worknc_fast_path(df, nome_file, log)
    if _worknc_result is not None:
        return _worknc_result

    # Fast path Cimatron (deterministico, 0 token)
    _cima_result = _cimatron_fast_path(df, nome_file, log)
    if _cima_result is not None:
        return _cima_result

    # Single-shot Sonnet: sostituisce L2a + L2b + L3 + L4
    profili_dir = os.path.join(os.path.dirname(__file__), '..', 'profili')
    ss_result = _sonnet_mapping_singleshot(df, nome_file, key, log, profili_dir)

    if not ss_result.get('mapping'):
        return {'verificato': False, 'errore': 'Mapping non prodotto',
                'struttura': {}, 'log': log_eventi, 'costo_stimato': 0}

    mapping_finale = ss_result['mapping']
    profilo = {col: info for col, info in mapping_finale.items()
               if info.get('campo_master', 'ignora') != 'ignora'}

    log('L1', 'Profilo finale: %d campi' % len(profilo))

    return {
        'profilo':         profilo,
        'struttura':       {'software_cam': ss_result.get('software_cam', 'sconosciuto')},
        'analisi_colonne': {},
        'verifica':        {'approvato': True, 'score_confidenza': ss_result.get('score_confidenza', 85)},
        'verificato':      ss_result.get('approvato', False),
        'score':           ss_result.get('score_confidenza', 85),
        'log':             log_eventi,
        'costo_stimato':   0,
        'campi_mancanti':  [],
        'warning':         ss_result.get('warning', []),
        'mapping':         mapping_finale,
    }



def disponibile(api_key=None) -> bool:
    return bool(_get_api_key(api_key))


learning_multilivello = orchestra_learning


if __name__ == '__main__':
    import pandas as pd
    key = _get_api_key()
    if not key: print('API key non configurata.'); sys.exit(1)
    sample = os.path.join(_BASE, 'cam_samples', 'worknc_tools_sample.csv')
    if not os.path.exists(sample): print('File non trovato:', sample); sys.exit(1)
    print('Test agente multilivello - WorkNC sample')
    df = pd.read_csv(sample)
    r = orchestra_learning(df, key, 'worknc_tools_sample.csv')
    print('Verificato:', r['verificato'], '| Score:', r['score'], '%')
    print('Campi mappati:', len(r.get('profilo', {})))
    for col, info in r.get('profilo', {}).items():
        print(' ', col, '->', info['campo_master'], '['+info['confidenza']+']')
