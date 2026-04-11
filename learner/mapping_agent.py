"""
mapping_agent.py
================
Agente Claude per l'analisi e mapping automatico di file CAM sconosciuti.

L'agente riceve una analisi completa del file (struttura, valori campione,
statistiche) e risponde con:
  - Mappatura colonne -> campi master
  - Trasformazioni necessarie (arrotondamento, decodifica ID, normalizzazione)
  - Rilevamento software CAM
  - Note e avvertenze sui dati

La differenza rispetto a un mapping euristico:
  - Capisce il CONTESTO (es. valori 1.9999999997 = errore floating point = 2.0)
  - Capisce la SEMANTICA (es. colonna 'Avanz.' con valori >1000 = Vf mm/min)
  - Capisce le RELAZIONI (es. 3103 = fuori pinza = dato critico per programmatori CAM)
  - Funziona in QUALSIASI LINGUA (italiano, inglese, tedesco, francese...)

Configurazione API key:
  1. export ANTHROPIC_API_KEY=sk-ant-...
  2. .env nella cartella progetto: ANTHROPIC_API_KEY=sk-ant-...
  3. config.json: { "anthropic_api_key": "sk-ant-..." }
"""

import os
import json
import re
import urllib.request
import ssl

_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
_CONFIG_PATH = os.path.join(_BASE, 'config.json')

# Campi del DB master con descrizioni dettagliate per il prompt
MASTER_FIELDS = {
    # Identificazione
    'codice_interno':       'Codice identificativo univoco utensile. Es: FRESA-FIN-D10-R0.5',
    'codice_catalogo':      'Codice catalogo del fornitore. Es: R216.34-10030-AC10G',
    'descrizione':          'Descrizione testuale, commento. Es: FF6R0.5L18F20G1',
    'sito_web':             'URL sito web fornitore o scheda tecnica',
    'num_magazzino':        'Numero posizione nel magazzino utensili della macchina (intero)',
    # Tipo
    'tipo':                 'Tipo utensile: FLAT=piatta, BALL=sferica, BULL=torica/bullnose, DRILL=punta, TAP=maschio, REAM=alesatore, SPOT=centratura, TAPER=conico',
    'tecnologia':           'Tecnologia: Fresatura, Foratura, Speciale',
    # Geometria
    'diametro_mm':          'Diametro tagliente in mm. Valori tipici: 1-100mm',
    'raggio_punta_mm':      'Raggio di raccordo/corner radius in mm. 0=piatta, =diam/2=sferica',
    'angolo_punta_gradi':   'Angolo punta in gradi. Per punte: tipicamente 118-140 gradi',
    'lunghezza_totale_mm':  'Lunghezza totale utensile in mm',
    'lunghezza_tagl_mm':    'Lunghezza utile/tagliente in mm (clear length)',
    'lunghezza_tagl2_mm':   'Lunghezza tagliente effettiva (cut length)',
    'num_taglienti':        'Numero di taglienti/denti/flute. Intero, tipicamente 2-8',
    'conico':               'Utensile conico: 0=no, 1=si',
    'angolo_conico_gradi':  'Angolo conicita in gradi',
    # Assemblaggio pinza - CAMPO CRITICO
    'nome_pinza':           'Nome/codice del portautensile o pinza. Es: HSL_D6-NEW, H80',
    'lungh_presa_mm':       'Lunghezza inserimento nella pinza in mm (quanto utensile entra)',
    'fuori_pinza_mm':       'DATO CRITICO: distanza dalla punta utensile all inizio della pinza in mm. Usato dai programmatori CAM per verificare raggiungibilita',
    # Stelo
    'diam_stelo_sup_mm':    'Diametro superiore stelo in mm',
    'diam_stelo_inf_mm':    'Diametro inferiore stelo in mm',
    'lungh_libera_stelo_mm':'Lunghezza zona libera dello stelo (non a contatto con pinza)',
    # Parametri taglio di default
    'vc_default':           'Velocita di taglio Vc di default in m/min (50-500)',
    'n_rpm':                'Velocita mandrino N in giri/min (1000-20000). Nota: nel file puo chiamarsi Rotaz.',
    'fz_default':           'Avanzamento per dente Fz in mm/dente (0.01-0.5). Valori piccoli <1',
    'vf_mm_min':            'Avanzamento tavola Vf in mm/min (100-5000). Nota: nel file puo chiamarsi Avanz.',
    'passo_z_default':      'Profondita passata assiale ap in mm',
    'passo_lat_default':    'Larghezza passata radiale ae in mm',
    'vita_utensile':        'Vita utensile in minuti o cicli (intero)',
    'dir_rotazione':        'Direzione rotazione: CW=orario, CCW=antiorario',
    'refrigerante':         'Tipo refrigerante: OFF, Flood, Mist, Through, Air',
    # Condizioni taglio per materiale (tabella separata)
    'vc_m_min':             'Velocita taglio Vc per materiale specifico in m/min',
    'n_rpm_mat':            'RPM per materiale specifico',
    'fz_mm':                'Fz per materiale specifico in mm/z',
    'vf_mm_min_mat':        'Vf per materiale specifico in mm/min',
    'ap_mm':                'Passata assiale ap per materiale specifico in mm',
    'ae_mm':                'Passata laterale ae per materiale specifico in mm',
    'materiale_pezzo':      'Nome materiale pezzo da lavorare. Es: 1.2311, Acciaio, Alluminio',
}


def _get_api_key(api_key=None):
    if api_key: return api_key
    k = os.environ.get('ANTHROPIC_API_KEY','').strip()
    if k: return k
    for env_path in [os.path.join(_BASE, '.env'), os.path.join(os.path.dirname(__file__), '.env')]:
        if os.path.exists(env_path):
            try:
                with open(env_path) as f:
                    for line in f:
                        if line.strip().startswith('ANTHROPIC_API_KEY='):
                            return line.split('=',1)[1].strip().strip('"').strip("'")
            except Exception: pass
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH) as f:
                return json.load(f).get('anthropic_api_key','').strip()
    except Exception: pass
    return ''


def agente_disponibile(api_key=None):
    return bool(_get_api_key(api_key))


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _chiama_claude(prompt, api_key, model='claude-sonnet-4-20250514', max_tokens=2000):
    payload = json.dumps({
        'model': model,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': prompt}]
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
    with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=30) as resp:
        return json.loads(resp.read())['content'][0]['text']


def _parse_json(testo):
    testo = testo.strip()
    testo = re.sub(r'```[a-z]*\n?', '', testo)
    testo = re.sub(r'```', '', testo).strip()
    try:
        return json.loads(testo)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', testo, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return {}


# ---------------------------------------------------------------
# ANALISI COMPLETA FILE
# ---------------------------------------------------------------

def analizza_struttura(df) -> dict:
    """
    Costruisce un'analisi dettagliata del DataFrame per il prompt dell'agente.
    Include statistiche, pattern, valori anomali.
    """
    analisi = {}
    for col in df.columns:
        serie = df[col].dropna()
        if len(serie) == 0:
            continue

        info = {
            'campioni': [str(v)[:30] for v in serie.head(5).tolist()],
            'non_nulli': len(serie),
            'unici': serie.nunique(),
        }

        # Analisi numerica
        import pandas as pd
        nums = pd.to_numeric(serie, errors='coerce').dropna()
        if len(nums) / max(len(serie), 1) > 0.7:
            info['tipo_rilevato'] = 'numerico'
            info['min']  = round(float(nums.min()), 4)
            info['max']  = round(float(nums.max()), 4)
            info['media']= round(float(nums.mean()), 4)
            # Rileva errori floating point (valori quasi-interi)
            quasi_interi = sum(1 for v in nums if abs(v - round(v)) < 0.0001)
            if quasi_interi > len(nums) * 0.8:
                info['nota'] = 'ATTENZIONE: molti valori quasi-interi - possibile errore floating point Cimatron'
                info['valori_reali_stimati'] = [round(v,1) for v in nums.head(3).tolist()]
        elif serie.nunique() <= 15 and serie.nunique() < len(serie) * 0.5:
            info['tipo_rilevato'] = 'categorico'
            info['valori_distinti'] = series_unique = [str(v) for v in serie.unique().tolist()[:15]]
        else:
            info['tipo_rilevato'] = 'testo'

        analisi[col] = info

    return analisi


def suggerisci_mapping_completo(df, software_hint='', versione_hint='', api_key=None) -> dict:
    """
    Analisi completa del file con l'agente Claude.

    A differenza del mapping semplice che guarda solo i nomi delle colonne,
    questa funzione fornisce all'agente:
      - Struttura completa con statistiche
      - Valori campione reali
      - Pattern numerici e anomalie
      - Contesto del software CAM (se noto)

    Ritorna un dict completo con mappatura, trasformazioni e note.
    """
    key = _get_api_key(api_key)
    if not key:
        print('[mapping_agent] API key non configurata')
        return {}

    analisi = analizza_struttura(df)

    prompt = f"""Sei un esperto di database utensili CNC e sistemi CAM.
Hai una conoscenza approfondita di:
- Geometria utensili (frese, punte, maschi, alesatori)
- Sistemi CAM (Cimatron, hyperMILL, WorkNC, Mastercam, NX, Siemens)
- Parametri di taglio (Vc, Fz, ap, ae, N, Vf)
- Portautensili e assemblaggio (HSK, BT, ISO, portapinze)
- Codifiche numeriche di software CAM (es. 210201=FLAT, 210202=BALL in Cimatron)

CONTESTO FILE:
Software rilevato: {software_hint or 'sconosciuto'}
Versione: {versione_hint or 'sconosciuta'}
Numero righe dati: {len(df)}
Numero colonne: {len(df.columns)}

ANALISI STRUTTURA FILE:
{json.dumps(analisi, indent=2, ensure_ascii=False)}

CAMPI DEL DATABASE MASTER (TARGET):
{json.dumps(MASTER_FIELDS, indent=2, ensure_ascii=False)}

COMPITO:
Analizza ogni colonna del file e determina:
1. A quale campo master corrisponde (o "ignora" se non rilevante)
2. Se serve una trasformazione (es. arrotondamento, decodifica ID)
3. La tua confidenza (alta/media/bassa)
4. Una motivazione breve

Linee guida specifiche:
- Valori quasi-interi (1.9999997, 3.9999998) -> arrotonda, sono errori float di Cimatron
- Valori numerici molto piccoli <0.5 con molti decimali -> probabilmente Fz (mm/dente)
- Valori numerici alti 1000-20000 -> probabilmente RPM (N)
- Valori numerici 100-5000 -> probabilmente Vf (mm/min) o N (rpm)
- Valori 50-500 -> probabilmente Vc (m/min)
- ID come 210201/210202/210203 -> tipo Cimatron: FLAT/BALL/BULL
- Colonne con 'Libera' o 'Free' + valori 10-200mm -> fuori_pinza_mm (DATO CRITICO)
- Colonne con 'Presa' o 'Grip' + valori 10-100mm -> lungh_presa_mm
- Colonne con nome portautensile (HSL_, H80, W65_, CB_) -> nome_pinza

Rispondi SOLO con JSON valido:
{{
  "software_rilevato": "nome software se lo riconosci",
  "versione_rilevata": "versione se riconoscibile",
  "note_generali": "osservazioni importanti sui dati",
  "mappatura": {{
    "nome_colonna_file": {{
      "campo_master": "campo_target_o_ignora",
      "confidenza": "alta|media|bassa",
      "motivazione": "spiegazione",
      "trasformazione": "nessuna|arrotonda|decodifica_id_cimatron|uppercase|...",
      "da_agente": true
    }}
  }}
}}
"""

    try:
        print(f'[mapping_agent] Analisi completa: {len(df.columns)} colonne, {len(df)} righe...')
        testo = _chiama_claude(prompt, key, max_tokens=3000)
        data  = _parse_json(testo)

        if not data or 'mappatura' not in data:
            print('[mapping_agent] Risposta non valida dall agente')
            return {}

        print(f'[mapping_agent] Mappatura completata: {len(data.get("mappatura",{}))} colonne')
        if data.get('note_generali'):
            print(f'[mapping_agent] Note: {data["note_generali"]}')

        return data

    except Exception as e:
        print(f'[mapping_agent] Errore: {e}')
        return {}


def arricchisci_mapping(mapping_esistente, colonne_non_mappate, df,
                         usa_agente=True, api_key=None, software='', versione=''):
    """
    Arricchisce un mapping deterministico con i suggerimenti dell'agente.
    Versione migliorata: passa la struttura completa del file.
    """
    if not usa_agente or not colonne_non_mappate:
        return mapping_esistente

    if not agente_disponibile(api_key):
        print('[mapping_agent] API key non configurata - mapping AI disabilitato')
        return mapping_esistente

    # Passa solo le colonne non ancora mappate per efficienza
    df_sub = df[[c for c in colonne_non_mappate if c in df.columns]]
    if df_sub.empty:
        return mapping_esistente

    result = suggerisci_mapping_completo(df_sub, software, versione, api_key)
    if not result or 'mappatura' not in result:
        return mapping_esistente

    mapping = dict(mapping_esistente)
    for col, info in result['mappatura'].items():
        campo = info.get('campo_master','ignora')
        if campo == 'ignora' or campo in mapping:
            continue

        import pandas as pd
        tipo = 'float'
        if any(k in campo for k in ['num_','_int','_n','taglienti','magazzino']):
            tipo = 'int'
        elif any(k in campo for k in ['tipo','materiale','tecnologia','dir_','refrigerante','pinza','nome','codice','descrizione','sito']):
            tipo = 'string' if 'nome' in campo or 'codice' in campo or 'descrizione' in campo or 'sito' in campo else 'categoria'

        mapping[campo] = {
            'colonna_file':   col,
            'score':          8.0 if info['confidenza'] == 'alta' else 5.0 if info['confidenza'] == 'media' else 3.0,
            'tipo':           tipo,
            'label':          col,
            'confidenza':     info['confidenza'],
            'motivazione':    info.get('motivazione',''),
            'trasformazione': info.get('trasformazione','nessuna'),
            'da_agente':      True,
        }

    return mapping


# ---------------------------------------------------------------
# TEST STANDALONE
# ---------------------------------------------------------------
if __name__ == '__main__':
    key = _get_api_key()
    if not key:
        print('API key non trovata.')
        print('Configura: export ANTHROPIC_API_KEY=sk-ant-...')
    else:
        print(f'API key: {key[:16]}...')
        print('Agente disponibile: SI')
        print()
        print('Test con dati campione...')
        import pandas as pd
        df_test = pd.DataFrame([
            {'Nome Utensile':'FRESA-D10','Commento':'FF10','Diametro':10.0,'Raggio Base':0.5,
             'Punta/Tipo':'210203','Denti':4,'Lunghezza Totale Ut.':75.0,'Lunghezza Utile':22.0,
             'Avanz.':1426.732,'Rotaz.':7589,'Vt':143.068,'Fz':0.047,
             'Nome Pinza':'HSL_D10-NEW','Lunghezza Presa':40.0,'Lungh. Libera':35.0},
        ])
        result = suggerisci_mapping_completo(df_test, 'Cimatron', '2025')
        if result:
            print('Note:', result.get('note_generali',''))
            print('Mappatura:')
            for col, info in result.get('mappatura',{}).items():
                if info['campo_master'] != 'ignora':
                    print(f'  {col:25} -> {info["campo_master"]:25} [{info["confidenza"]}] {info.get("trasformazione","")}')
        else:
            print('Nessun risultato')
