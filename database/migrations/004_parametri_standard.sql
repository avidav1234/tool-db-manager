-- Migrazione 004: Parametri standard industriale con cascata sottofamiglie

CREATE TABLE IF NOT EXISTS SottoFamiglie (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    famiglia_id INTEGER NOT NULL REFERENCES FamiglieUtensile(id),
    codice TEXT NOT NULL,
    produttore TEXT,
    descrizione TEXT,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(famiglia_id, codice)
);

CREATE TABLE IF NOT EXISTS ParametriBase_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    famiglia_id INTEGER NOT NULL REFERENCES FamiglieUtensile(id),
    materiale_id INTEGER NOT NULL REFERENCES Materiali(id),
    vc_base REAL NOT NULL,
    fz_D_ratio REAL NOT NULL,
    ap_D_ratio REAL NOT NULL DEFAULT 0.5,
    ae_D_ratio REAL NOT NULL DEFAULT 0.3,
    fonte TEXT DEFAULT 'manuale',
    approvato INTEGER DEFAULT 0,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(famiglia_id, materiale_id)
);

CREATE TABLE IF NOT EXISTS ParametriSottoFamiglia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sottofamiglia_id INTEGER NOT NULL REFERENCES SottoFamiglie(id),
    materiale_id INTEGER NOT NULL REFERENCES Materiali(id),
    vc_base REAL,
    fz_D_ratio REAL,
    ap_D_ratio REAL,
    ae_D_ratio REAL,
    fonte TEXT DEFAULT 'catalogo',
    approvato INTEGER DEFAULT 0,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(sottofamiglia_id, materiale_id)
);

CREATE TABLE IF NOT EXISTS Lavorazioni_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    scopo TEXT NOT NULL,
    k_vc REAL NOT NULL DEFAULT 1.0,
    k_fz REAL NOT NULL DEFAULT 1.0,
    k_ap REAL NOT NULL DEFAULT 1.0,
    k_ae REAL NOT NULL DEFAULT 1.0,
    note TEXT
);

CREATE TABLE IF NOT EXISTS FattoriCorrezione_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    famiglia_id INTEGER REFERENCES FamiglieUtensile(id),
    tipo_fattore TEXT NOT NULL,
    nome TEXT,
    range_min REAL,
    range_max REAL,
    k_vc REAL NOT NULL DEFAULT 1.0,
    k_fz REAL NOT NULL DEFAULT 1.0,
    k_ap REAL NOT NULL DEFAULT 1.0,
    k_ae REAL NOT NULL DEFAULT 1.0,
    note TEXT
);
