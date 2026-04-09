-- ============================================================
-- Tool DB Manager - Schema Database Master
-- Versione: 1.0  |  Standard: ISO 13399
-- Compatibile con: Cimatron, hyperMILL, WorkNC
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ------------------------------------------------------------
-- TABELLA: tipo_utensile
-- Classificazione degli utensili supportati
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tipo_utensile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codice      TEXT NOT NULL UNIQUE,   -- es. FLAT, BALL, BULL, DRILL, TAP, REAM
    descrizione TEXT NOT NULL
);

INSERT OR IGNORE INTO tipo_utensile (codice, descrizione) VALUES
    ('FLAT',  'Fresa piatta'),
    ('BALL',  'Fresa sferica'),
    ('BULL',  'Fresa torica (bull nose)'),
    ('TAPER', 'Fresa conica'),
    ('DRILL', 'Punta'),
    ('TAP',   'Maschio'),
    ('REAM',  'Alesatore'),
    ('THREAD','Fresa per filettature'),
    ('SPOT',  'Punta a centrare'),
    ('FORM',  'Utensile sagomato');

-- ------------------------------------------------------------
-- TABELLA: materiale_utensile
-- Materiale del tagliente
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS materiale_utensile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codice      TEXT NOT NULL UNIQUE,   -- es. HM, HSS, CBN, PCD
    descrizione TEXT NOT NULL
);

INSERT OR IGNORE INTO materiale_utensile (codice, descrizione) VALUES
    ('HM',  'Metallo duro (carbide)'),
    ('HSS', 'Acciaio rapido'),
    ('HSCo','Acciaio rapido al cobalto'),
    ('CBN', 'Nitruro di boro cubico'),
    ('PCD', 'Diamante policristallino'),
    ('CER', 'Ceramica');

-- ------------------------------------------------------------
-- TABELLA: fornitore
-- Produttori/fornitori degli utensili
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fornitore (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    codice      TEXT UNIQUE,
    sito_web    TEXT,
    note        TEXT
);

-- ------------------------------------------------------------
-- TABELLA: portautensile
-- Holder / portautensili
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portautensile (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codice_interno  TEXT NOT NULL UNIQUE,  -- ID univoco aziendale
    codice_catalogo TEXT,                  -- codice del fornitore
    descrizione     TEXT NOT NULL,
    tipo_attacco    TEXT,                  -- es. HSK-A63, SK40, BT40, ISO40
    diam_attacco_mm REAL,
    lunghezza_mm    REAL,
    sbalzo_max_mm   REAL,
    id_fornitore    INTEGER REFERENCES fornitore(id),
    note            TEXT,
    attivo          INTEGER NOT NULL DEFAULT 1  -- 1=attivo, 0=dismesso
);

-- ------------------------------------------------------------
-- TABELLA: utensile
-- Tabella principale - ogni riga e un utensile fisico
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS utensile (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identificazione
    codice_interno      TEXT NOT NULL UNIQUE,  -- ID master univoco aziendale
    codice_catalogo     TEXT,                   -- codice del fornitore
    descrizione         TEXT NOT NULL,

    -- Classificazione
    id_tipo             INTEGER NOT NULL REFERENCES tipo_utensile(id),
    id_materiale        INTEGER NOT NULL REFERENCES materiale_utensile(id),
    id_fornitore        INTEGER REFERENCES fornitore(id),

    -- Geometria principale (mm) - ISO 13399
    diametro_mm         REAL NOT NULL,
    raggio_punta_mm     REAL NOT NULL DEFAULT 0,  -- 0 = piatto, >0 = torica/sferica
    angolo_punta_gradi  REAL,                     -- per punte: tipicamente 118 o 135
    lunghezza_totale_mm REAL NOT NULL,
    lunghezza_tagl_mm   REAL NOT NULL,            -- lunghezza parte tagliente
    num_taglienti       INTEGER NOT NULL DEFAULT 2,
    angolo_elica_gradi  REAL,

    -- Dati filettatura (solo per maschi e frese filetto)
    passo_mm            REAL,
    profilo_filetto     TEXT,   -- es. M, G, UN, TR

    -- Portautensile predefinito
    id_portautensile    INTEGER REFERENCES portautensile(id),

    -- Metadati
    note                TEXT,
    attivo              INTEGER NOT NULL DEFAULT 1,
    data_inserimento    TEXT NOT NULL DEFAULT (datetime('now')),
    data_modifica       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Trigger aggiornamento data_modifica
CREATE TRIGGER IF NOT EXISTS utensile_modifica
AFTER UPDATE ON utensile
BEGIN
    UPDATE utensile SET data_modifica = datetime('now') WHERE id = NEW.id;
END;

-- ------------------------------------------------------------
-- TABELLA: condizioni_taglio
-- Parametri di taglio per combinazione utensile + materiale pezzo
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS condizioni_taglio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_utensile     INTEGER NOT NULL REFERENCES utensile(id) ON DELETE CASCADE,
    materiale_pezzo TEXT NOT NULL,   -- es. Acciaio, Alluminio, Ghisa, Titanio
    applicazione    TEXT,            -- es. sgrossatura, finitura, spianatura

    -- Parametri di taglio
    vc_m_min        REAL,   -- velocita di taglio [m/min]
    n_rpm           REAL,   -- velocita mandrino [giri/min]
    fz_mm           REAL,   -- avanzamento per dente [mm/dente]
    vf_mm_min       REAL,   -- avanzamento tavola [mm/min]
    ap_mm           REAL,   -- profondita assiale [mm]
    ae_mm           REAL,   -- larghezza radiale [mm]

    note            TEXT,
    UNIQUE(id_utensile, materiale_pezzo, applicazione)
);

-- ------------------------------------------------------------
-- TABELLA: log_export
-- Traccia ogni export verso i CAM
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS log_export (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cam         TEXT NOT NULL,   -- CIMATRON | HYPERMILL | WORKNC
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    num_utensili INTEGER,
    file_output TEXT,
    note        TEXT
);

-- ------------------------------------------------------------
-- VIEW: utensile_completo
-- Vista denormalizzata comoda per gli export
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS utensile_completo AS
SELECT
    u.id,
    u.codice_interno,
    u.codice_catalogo,
    u.descrizione,
    t.codice      AS tipo,
    m.codice      AS materiale,
    f.nome        AS fornitore,
    u.diametro_mm,
    u.raggio_punta_mm,
    u.angolo_punta_gradi,
    u.lunghezza_totale_mm,
    u.lunghezza_tagl_mm,
    u.num_taglienti,
    u.angolo_elica_gradi,
    u.passo_mm,
    u.profilo_filetto,
    p.codice_interno  AS portautensile,
    p.tipo_attacco,
    u.note,
    u.attivo
FROM utensile u
JOIN tipo_utensile t      ON u.id_tipo      = t.id
JOIN materiale_utensile m ON u.id_materiale  = m.id
LEFT JOIN fornitore f     ON u.id_fornitore  = f.id
LEFT JOIN portautensile p ON u.id_portautensile = p.id;
