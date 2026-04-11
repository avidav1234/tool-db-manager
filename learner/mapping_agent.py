"""
mapping_agent.py
================
Agente Claude per il mapping automatico di colonne non identificate.

Quando il parser deterministico non riesce a identificare una colonna,
questo modulo chiama l'API Claude con il nome della colonna + campione di
valori reali, e ottiene una mappatura verso i campi master ISO 13399.

Vantaggi rispetto all'euristica pura:
  - Capisce qualsiasi lingua (italiano, inglese, tedesco, francese...)
  - Capisce abbreviazioni e nomi non standard
  - Capisce il contesto (es. "Avanz." + valori alti -> vf_mm_min)
  - Nessuna API key separata: usa la stessa sessione browser tramite
    l'endpoint /api/agent nel Format Learner
"""

import json
import urllib.request
import re

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
    'n_rpm':               'Velocita mandrino giri/min - RPM (tipicamente 1000-20000)',
    'fz_mm':               'Avanzamento per dente Fz in mm/dente (tipicamente 0.01-0.5)',
    'vf_mm_min':           'Avanzamento tavola Vf in mm/min (tipicamente 100-5000)',
    'ap_mm':               'Profondita di passata assiale ap in mm',
    'ae_mm':               'Larghezza di passata radiale ae in mm',
    'materiale_pezzo':     'Materiale del pezzo da lavorare (es: 1.2311, Acciaio, Alluminio)',
}


def suggerisci_mapping(colonne: list, df) -> dict:
    """
    Chiama l'API Claude per suggerire il mapping delle colonne non identificate.
    Ritorna: { nome_colonna -> { campo_master, confidenza, motivazione, da_agente } }
    """
    if not colonne:
        return {}

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
        '- "Nome Materiale" con nomi acciaio -> materiale_pezzo\n'
        '- Numero Ut./Magazine/Compensazione -> ignora\n'
    )

    try:
        testo = _chiama_claude(prompt)
        return _parse_risposta(testo, list(campioni.keys()))
    except Exception as e:
        print(f"[mapping_agent] Errore API: {e}")
        return {}


def _chiama_claude(prompt: str) -> str:
    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        return data['content'][0]['text']


def _parse_risposta(testo: str, colonne_attese: list) -> dict:
    testo = testo.strip()
    testo = re.sub(r'```json\s*', '', testo)
    testo = re.sub(r'```\s*', '', testo)

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
                         df, usa_agente: bool = True) -> dict:
    """
    Combina mapping deterministico + suggerimenti agente.
    Le colonne gia' mappate non vengono mai sovrascritte.
    """
    if not usa_agente or not colonne_non_mappate:
        return mapping_esistente

    print(f"[mapping_agent] Analizzo {len(colonne_non_mappate)} colonne non identificate...")
    suggerimenti = suggerisci_mapping(colonne_non_mappate, df)
    print(f"[mapping_agent] Suggeriti {len(suggerimenti)} mapping aggiuntivi")

    mapping = dict(mapping_esistente)
    for col, info in suggerimenti.items():
        campo = info['campo_master']
        if campo not in mapping:
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
