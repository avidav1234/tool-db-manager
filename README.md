# Tool DB Manager

Database utensili centralizzato per Cimatron, hyperMILL e WorkNC.

## Obiettivo

Un unico database master (SQLite) che genera automaticamente i file di import
per i tre sistemi CAM presenti in azienda, eliminando la necessita di inserire
manualmente gli stessi utensili in tre sistemi diversi.

## Struttura del progetto

```
tool-db-manager/
├── README.md
├── requirements.txt
├── database/
│   ├── schema.sql           # Schema completo del DB master
│   └── tool_master.db       # File SQLite (generato al primo avvio)
├── exporters/
│   ├── export_cimatron.py   # Genera CSV pipe-separato per Cimatron
│   ├── export_hypermill.py  # Genera file per hyperMILL
│   └── export_worknc.py     # Genera file per WorkNC
├── importers/
│   └── import_from_excel.py # Migrazione da Excel/CSV esistenti
└── ui/
    └── app.py               # Interfaccia web locale (Flask)
```

## Requisiti

- Python 3.10+
- SQLite (incluso in Python, nessuna installazione separata)
- Dipendenze: vedi requirements.txt

## Installazione

```bash
git clone https://github.com/avidav1234/tool-db-manager.git
cd tool-db-manager
pip install -r requirements.txt
python ui/app.py
```

## Stato sviluppo

| Fase | Descrizione | Stato |
|------|-------------|-------|
| 1 | Schema database master | Completo |
| 2 | DB SQLite + script popolazione | In corso |
| 3 | Export Cimatron | In corso |
| 4 | Export hyperMILL | Attende info versione |
| 5 | Export WorkNC | Attende info versione |
| 6 | Interfaccia utente Flask | Pianificato |

## Standard di riferimento

- ISO 13399: rappresentazione e scambio dati utensili da taglio
- Formato CSV Cimatron: pipe-separato con ID colonne numerici
