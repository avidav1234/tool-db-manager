# Format Learner — Modulo standalone

Modulo autonomo per l'apprendimento e la conversione universale di formati utensili CAM.

## Concetto

Ogni CAM usa un formato diverso per esportare/importare utensili.
Questo modulo **impara la struttura da un file reale** e salva la mappatura
come profilo JSON riutilizzabile.

Una volta che hai due profili, puoi convertire qualsiasi file da un formato all'altro
passando per il formato neutro ISO 13399.

```
File CAM A  ->  (profilo A)  ->  Master neutro  ->  (profilo B)  ->  File CAM B
```

## Struttura

```
learner/
├── format_learner.py      # Analisi automatica struttura file
├── profile_manager.py     # Salvataggio/caricamento profili JSON
├── universal_converter.py # Motore di conversione
├── app_learner.py         # Interfaccia web standalone (porta 5001)
├── profiles/
│   ├── cimatron_v26.json  # Profilo predefinito Cimatron
│   └── ...                # Profili appresi
└── README.md
```

## Avvio rapido

```bash
cd learner
pip install flask pandas openpyxl
python app_learner.py
# Apri http://localhost:5001
```

## Uso da riga di comando

```bash
# Analizza un file
python format_learner.py --file export_hypermill.csv

# Converti tra formati
python universal_converter.py \\
    --input export_hypermill.csv \\
    --profilo-input hypermill_2024 \\
    --profilo-output cimatron_v26 \\
    --output output/per_cimatron.csv
```

## Come aggiungere un nuovo CAM

1. Esporta gli utensili dal CAM (CSV, XLS, ZIP)
2. Apri `http://localhost:5001`
3. Carica il file -> mappatura proposta automaticamente
4. Correggi eventuali errori
5. Salva il profilo con nome software e versione
6. Disponibile subito per import/export verso qualsiasi altro CAM noto

## Profili predefiniti

| Profilo | Software | Separatore |
|---------|----------|-----------|
| cimatron_v26 | Cimatron 26 | pipe `|` |

## Integrazione futura

Progettato per integrarsi con il modulo principale quando necessario.
`universal_converter.py` potra scrivere direttamente in `database/tool_master.db`.
