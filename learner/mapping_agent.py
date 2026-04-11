"""
mapping_agent.py
================
Agente Claude per il mapping automatico di colonne non identificate.

Quando il parser deterministico non riesce a identificare una colonna,
questo modulo chiama l'API Claude con il nome della colonna + campione di
valori reali, e ottiene una mappatura verso i campi master ISO 13399.

Configurazione API key (una delle seguenti):
  1. Variabile d'ambiente:  export ANTHROPIC_API_KEY=sk-ant-...
  2. File config.json:      { "anthropic_api_key": "sk-ant-..." }
  3. Parametro diretto:     suggerisci_mapping(..., api_key="sk-ant-...")

Senza API key l'agente e' disabilitato e il sistema usa solo il parser
deterministico — l'app continua a funzionare normalmente.
"""

import os
import json
import urllib.request
import re

# Campi master disponibili per il mapping
MASTER_FIELDS_DESC = {
    'codice_interno':      'Codice identificativo univoco utensile (nome, ID, numero)',
    'codice_catalogo':     'Codice catalogo del fornitore (numero articolo, SKU)',
    'descrizione':         'Descrizione testuale, commento, note sull utensile',
    'tipo':                'Tipo utensile (piatta, sferica, torica, punta, maschio, ecc.)',
    'diametro_mm':         'Diametro del tagliente in mm',
    'raggio_punta_mm':     'Raggio di raccordo/punta in mm (corner radius)',
    'angolo_punta_gradi':  'Angolo della punta in gradi (per punte, 118 gradi tipici)',
    'lunghezza_totale_mm': 'Lunghezza totale dell utensile in mm',
    'lunghezza_tagl_mm':   'Lunghezza della parte tagliente/utile in mm',
    'num_taglienti':       'Numero di taglienti/denti/flute (intero 2-8)',
    'angolo_elica_gradi':  'Angolo dell elica in gradi (20-45)',
    'materiale':           'Materiale del tagliente (HM=carbide, HSS, CBN, PCD)',
    'passo_mm':            'Passo della filettatura in mm',
    'vc_m_min':            'Velocita di taglio Vc in m/min (tipicamente 50-500)',
    'n_rpm':               'Velocita mandrino giri/min RPM (tipicamente 1000-20000)',
    'fz_mm':               'Avanzamento per dente Fz in mm/dente (tipicamente 0.01-0.5)',
    'vf_mm_min':           'Avanzamento tavola Vf in mm/min (tipicamente 100-5000)',
    'ap_mm':               'Profondita di passata assiale ap in mm',
    'ae_mm':               'Larghezza di passata radiale ae in mm',
    'materiale_pezzo':     'Materiale del pezzo da lavorare (es: 1.2311, Acciaio, Alluminio)',
}

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')


def _get_api_key(api_key: str = None) -> str:
    """
    Recupera la API key Anthropic in ordine di priorita':
    1. Parametro diretto
    2. Variabile d'ambiente ANTHROPIC_API_KEY
    3. config.json -> anthropic_api_key
    """
    if api_key:
        return api_key

    # Variabile d'ambiente
    env_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if env_key:
        return env_key

    # config.json
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH) as f:
                cfg = json.load(f)
            cfg_key = cfg.get('anthropic_api_key', '').strip()
            if cfg_key:
                return cfg_key
    except Exception:
        pass

    return ''


def agente_disponibile(api_key: str = None) -> bool:
    """Ritorna True se la API key e' configurata e l'agente puo' essere usato."""
    return bool(_get_api_key(api_key))


def suggerisci_mapping(colonne: list, df, api_key: str = None) -> dict:
    """
    Chiama l'API Claude per suggerire il mapping delle colonne non identificate.

    Args:
        colonne:  lista di nomi colonna non ancora mappati
        df:       DataFrame con i dati (usa le prime 5 righe come campione)
        api_key:  API key Anthropic (opzionale, vedi _get_api_key)

    Returns:
        dict: { nome_colonna -> { campo_master, confidenza, motivazione, da_agente } }
        dict vuoto se l'agente non e' disponibile o la chiamata fallisce
    """
    key = _get_api_key(api_key)
    if not key:
        print("[mapping_agent] API key non configurata - agente disabilitato")
        print("[mapping_agent] Per abilitarlo: export ANTHROPIC_API_KEY=sk-ant-...")
        print("[mapping_agent]   oppure aggiungi 'anthropic_api_key' in config.json")
        return {}

    if not colonne:
        return {}

    # Prepara campioni di valori per ogni colonna
    campioni = {}
    for col in colonne:
        if col in df.columns:
            valori = [str(v)[:25] for v in df[col].dropna().head(5).tolist()
                      if str(v).strip() not in ('', 'nan')]
            if valori:
                campioni[col] = valori

    if not campioni:
        return {}

    prompt = (
        "Sei un esperto di database utensili CNC e CAM.\n"
        "Ti fornisco colonne da un file export CAM con valori campione.\n"
        "Per ogni colonna, indica a quale campo del database master corrisponde.\n\n"
        "CAMPI MASTER DISPONIBILI:\n"
        + json.dumps(MASTER_FIELDS_DESC, indent=2, ensure_ascii=False)
        + "\n\nCOLONNE DA MAPPARE (nome: [valori campione]):\n"
        + json.dumps(campioni, indent=2, ensure_ascii=False)
        + '\n\nRispondi SOLO con JSON valido, nessun testo aggiuntivo.\n'
        'Formato:\n'
        '{\n'
        '  "nome_colonna": {\n'
        '    "campo_master": "nome_campo_o_ignora",\n'
        '    "confidenza": "alta|media|bassa",\n'
        '    "motivazione": "breve spiegazione in italiano"\n'
        '  }\n'
        '}\n\n'
        'Regole importanti:\n'
        '- Usa "ignora" se la colonna non e utile per il DB utensili\n'
        '- "Avanz." con valori >100 -> vf_mm_min\n'
        '- "Rotaz." con valori >1000 -> n_rpm\n'
        '- "Vt" o "Vc" -> vc_m_min\n'
        '- "Fz" con valori <1 -> fz_mm\n'
        '- "Passo in Z" -> ap_mm\n'
        '- "Passo Laterale" -> ae_mm\n'
        '- "Nome Materiale" con nomi acciaio/alluminio -> materiale_pezzo\n'
        '- Numero Ut./Magazine/Compensazione/Sito -> ignora\n'
    )

    try:
        print(f"[mapping_agent] Chiamo Claude per {len(campioni)} colonne non identificate...")
        testo = _chiama_claude(prompt, key)
        risultato = _parse_risposta(testo, list(campioni.keys()))
        print(f"[mapping_agent] Suggeriti {len(risultato)} mapping")
        return risultato
    except Exception as e:
        print(f"[mapping_agent] Errore chiamata API: {e}")
        return {}


def _chiama_claude(prompt: str, api_key: str) -> str:
    """Chiama l'API Anthropic con gli header corretti."""
    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=payload,
        headers={
            'Content-Type':      'application/json',
            'x-api-key':         api_key,
            'anthropic-version': '2023-06-01',
        },
        method='POST'
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        return data['content'][0]['text']


def _parse_risposta(testo: str, colonne_attese: list) -> dict:
    """Estrae e valida il JSON dalla risposta dell'agente."""
    testo = testo.strip()
    # Rimuovi eventuali blocchi markdown
    testo = re.sub(r'```[a-z]*\n?', '', testo)
    testo = re.sub(r'```', '', testo)

    try:
        data = json.loads(testo)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', testo, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except Exception:
                return {}
        else:
            return {}

    risultato = {}
    for col, info in data.items():
        if col not in colonne_attese or not isinstance(info, dict):
            continue
        campo = info.get('campo_master', 'ignora')
        if campo == 'ignora':
            continue
        risultato[col] = {
            'campo_master': campo,
            'confidenza':   info.get('confidenza', 'bassa'),
            'motivazione':  info.get('motivazione', ''),
            'da_agente':    True,
        }
    return risultato


def arricchisci_mapping(mapping_esistente: dict, colonne_non_mappate: list,
                         df, usa_agente: bool = True, api_key: str = None) -> dict:
    """
    Combina mapping deterministico + suggerimenti agente.
    Le colonne gia' mappate non vengono mai sovrascritte.
    Se l'agente non e' disponibile, ritorna il mapping esistente invariato.
    """
    if not usa_agente or not colonne_non_mappate:
        return mapping_esistente

    if not agente_disponibile(api_key):
        return mapping_esistente

    suggerimenti = suggerisci_mapping(colonne_non_mappate, df, api_key)
    mapping = dict(mapping_esistente)

    for col, info in suggerimenti.items():
        campo = info['campo_master']
        if campo not in mapping:  # Non sovrascrive mai i mapping deterministici
            mapping[campo] = {
                'colonna_file': col,
                'score':        5.0 if info['confidenza'] == 'alta' else 3.0,
                'tipo':         _inferisci_tipo(campo),
                'label':        col,
                'confidenza':   info['confidenza'],
                'motivazione':  info.get('motivazione', ''),
                'da_agente':    True,
            }
    return mapping


def _inferisci_tipo(campo: str) -> str:
    float_f = {'diametro_mm','raggio_punta_mm','angolo_punta_gradi','lunghezza_totale_mm',
               'lunghezza_tagl_mm','angolo_elica_gradi','passo_mm','vc_m_min','fz_mm',
               'vf_mm_min','ap_mm','ae_mm'}
    int_f   = {'num_taglienti','n_rpm'}
    cat_f   = {'tipo','materiale','materiale_pezzo'}
    if campo in float_f: return 'float'
    if campo in int_f:   return 'int'
    if campo in cat_f:   return 'categoria'
    return 'string'


# ---------------------------------------------------------------
# Test standalone
# ---------------------------------------------------------------
if __name__ == '__main__':
    import sys
    key = _get_api_key()
    if key:
        print(f"API key trovata: {key[:12]}...")
        print(f"Agente disponibile: SI")
    else:
        print("API key NON trovata.")
        print("Configura con:")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        print("  oppure aggiungi 'anthropic_api_key' in config.json")
