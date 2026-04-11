-- ============================================================
-- schema.sql - Tool DB Manager - Schema completo
-- Aggiornato con analisi file Cimatron 2025 SP5
-- ============================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------
-- TABELLE DI LOOKUP
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tipo_utensile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codice      TEXT    NOT NULL UNIQUE,
    descrizione TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS materiale_utensile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codice      TEXT    NOT NULL UNIQUE,
    descrizione TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS fornitore (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT    NOT NULL,
    sito    TEXT,
    note    TEXT
);

-- ---------------------------------------------------------------
-- PORTAUTENSILI (da Holders_*.csv)
-- Un portautensile ha fino a 20 segmenti cilindrici/conici
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portautensile (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    codice_interno   TEXT    NOT NULL UNIQUE,
    descrizione      TEXT,
    tipo_adattatore  TEXT,               -- HSK-A63, BT40, ISO40, ...
    num_segmenti     INTEGER DEFAULT 0,
    num_seg_mandrino INTEGER DEFAULT 0,
    tipo_visualiz    INTEGER DEFAULT 0,
    attivo           INTEGER NOT NULL DEFAULT 1,
    data_inserimento TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Segmenti geometria portautensile (max 20 per Cimatron)
CREATE TABLE IF NOT EXISTS portautensile_segmento (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_portautensile    INTEGER NOT NULL REFERENCES portautensile(id) ON DELETE CASCADE,
    numero_segmento     INTEGER NOT NULL,  -- 1..20
    diametro_inf_mm     REAL,
    diametro_sup_mm     REAL,
    altezza_cono_mm     REAL,
    altezza_totale_mm   REAL,
    UNIQUE(id_portautensile, numero_segmento)
);

-- ---------------------------------------------------------------
-- UTENSILI PRINCIPALI (da Cutters_*.csv)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS utensile (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identificazione
    codice_interno      TEXT    NOT NULL UNIQUE,
    codice_catalogo     TEXT,
    descrizione         TEXT,
    sito_web            TEXT,
    -- Classificazione
    id_tipo             INTEGER NOT NULL REFERENCES tipo_utensile(id),
    id_materiale        INTEGER NOT NULL REFERENCES materiale_utensile(id),
    id_fornitore        INTEGER REFERENCES fornitore(id),
    id_portautensile    INTEGER REFERENCES portautensile(id),
    tecnologia          TEXT,               -- Fresatura / Foratura / Speciale
    -- Geometria corpo
    diametro_mm         REAL    NOT NULL DEFAULT 0,
    raggio_punta_mm     REAL    NOT NULL DEFAULT 0,
    angolo_punta_gradi  REAL,
    lunghezza_totale_mm REAL    NOT NULL DEFAULT 0,
    lunghezza_tagl_mm   REAL    NOT NULL DEFAULT 0,   -- lunghezza utile
    lunghezza_tagl2_mm  REAL,                          -- lunghezza tagliente (cut length)
    num_taglienti       INTEGER NOT NULL DEFAULT 2,
    angolo_elica_gradi  REAL,
    conico              INTEGER DEFAULT 0,
    angolo_conico_gradi REAL,
    -- Geometria stelo principale
    diam_stelo_mm       REAL,
    diam_stelo_inf_mm   REAL,
    lungh_cono_stelo_mm REAL,
    lungh_libera_stelo_mm REAL,
    angolo_cono_stelo_gradi REAL,
    usa_angolo_cono_stelo INTEGER DEFAULT 0,
    -- Geometria stelo2
    diam_stelo2_mm      REAL,
    diam_stelo2_inf_mm  REAL,
    lungh_cono_stelo2_mm REAL,
    lungh_libera_stelo2_mm REAL,
    angolo_cono_stelo2_gradi REAL,
    -- Pinza inline (da Cutters)
    nome_pinza          TEXT,
    lungh_presa_mm      REAL,
    lungh_libera_pinza_mm REAL,
    -- Parametri taglio di default (utensile singolo, non per materiale)
    avanzamento_default REAL,
    rotazione_default   REAL,
    vc_default          REAL,
    fz_default          REAL,
    passo_z_default     REAL,
    passo_lat_default   REAL,
    num_magazzino       INTEGER,
    vita_utensile       INTEGER,
    -- Parametri macchina
    dir_rotazione       TEXT,
    refrigerante        TEXT,
    -- Filettatura
    passo_mm            REAL,
    -- Note e stato
    note                TEXT,
    attivo              INTEGER NOT NULL DEFAULT 1,
    data_inserimento    TEXT    NOT NULL DEFAULT (datetime('now')),
    data_modifica       TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- CONDIZIONI DI TAGLIO PER MATERIALE (da Material_*.csv)
-- 287 combinazioni utensile x materiale nell'export aziendale
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS condizioni_taglio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_utensile     INTEGER NOT NULL REFERENCES utensile(id) ON DELETE CASCADE,
    materiale_pezzo TEXT    NOT NULL,
    applicazione    TEXT,
    -- Parametri di taglio
    vc_m_min        REAL,    -- Velocita di taglio [m/min]
    n_rpm           REAL,    -- Velocita mandrino [giri/min]
    fz_mm           REAL,    -- Avanzamento per dente [mm/z]
    vf_mm_min       REAL,    -- Avanzamento tavola [mm/min]
    ap_mm           REAL,    -- Passo in Z [mm]
    ae_mm           REAL,    -- Passo laterale [mm]
    rompitruciolo   REAL,
    decrementa      REAL,
    refrigerante    TEXT,
    note            TEXT,
    UNIQUE(id_utensile, materiale_pezzo, applicazione)
);

-- ---------------------------------------------------------------
-- PROFILI SAGOMATI (da Contour_*.csv)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profilo_sagomato (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_utensile INTEGER NOT NULL REFERENCES utensile(id) ON DELETE CASCADE,
    tipo        TEXT,       -- 900201=L, ecc.
    dati_json   TEXT,       -- coordinate profilo in JSON
    data_inserimento TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- LOG EXPORT
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS log_export (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cam          TEXT    NOT NULL,
    num_utensili INTEGER NOT NULL DEFAULT 0,
    file_output  TEXT,
    timestamp    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- VIEW PRINCIPALE (compatibile con codice esistente + nuovi campi)
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS utensile_completo;
CREATE VIEW utensile_completo AS
SELECT
    u.id,
    u.codice_interno,
    u.codice_catalogo,
    u.descrizione,
    u.sito_web,
    t.codice                AS tipo,
    t.descrizione           AS tipo_descrizione,
    m.codice                AS materiale,
    m.descrizione           AS materiale_descrizione,
    f.nome                  AS fornitore,
    p.codice_interno        AS portautensile,
    p.tipo_adattatore       AS adattatore,
    u.tecnologia,
    u.diametro_mm,
    u.raggio_punta_mm,
    u.angolo_punta_gradi,
    u.lunghezza_totale_mm,
    u.lunghezza_tagl_mm,
    u.lunghezza_tagl2_mm,
    u.num_taglienti,
    u.angolo_elica_gradi,
    u.conico,
    u.angolo_conico_gradi,
    u.diam_stelo_mm,
    u.diam_stelo_inf_mm,
    u.lungh_cono_stelo_mm,
    u.lungh_libera_stelo_mm,
    u.nome_pinza,
    u.lungh_presa_mm,
    u.lungh_libera_pinza_mm,
    u.avanzamento_default,
    u.rotazione_default,
    u.vc_default,
    u.fz_default,
    u.passo_z_default,
    u.passo_lat_default,
    u.num_magazzino,
    u.vita_utensile,
    u.dir_rotazione,
    u.refrigerante,
    u.passo_mm,
    u.note,
    u.attivo,
    u.data_inserimento,
    u.data_modifica
FROM utensile u
JOIN tipo_utensile t      ON u.id_tipo = t.id
JOIN materiale_utensile m ON u.id_materiale = m.id
LEFT JOIN fornitore f     ON u.id_fornitore = f.id
LEFT JOIN portautensile p ON u.id_portautensile = p.id;

-- ---------------------------------------------------------------
-- DATI DI DEFAULT
-- ---------------------------------------------------------------
INSERT OR IGNORE INTO tipo_utensile (codice, descrizione) VALUES
    ('FLAT',   'Fresa piatta'),
    ('BALL',   'Fresa sferica'),
    ('BULL',   'Fresa torica (bull nose)'),
    ('DRILL',  'Punta da foratura'),
    ('TAP',    'Maschio filettatore'),
    ('REAM',   'Alesatore'),
    ('SPOT',   'Punta da centratura'),
    ('TAPER',  'Utensile conico'),
    ('THREAD', 'Fresa per filettatura'),
    ('PROBE',  'Tastatore');

INSERT OR IGNORE INTO materiale_utensile (codice, descrizione) VALUES
    ('HM',    'Metallo duro (carbide)'),
    ('HSS',   'Acciaio rapido'),
    ('HSCo',  'Acciaio rapido al cobalto'),
    ('CBN',   'Nitruro di boro cubico'),
    ('PCD',   'Diamante policristallino'),
    ('CER',   'Ceramica');

-- ---------------------------------------------------------------
-- TRIGGER aggiorna data_modifica
-- ---------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS utensile_modifica
AFTER UPDATE ON utensile
BEGIN
    UPDATE utensile SET data_modifica = datetime('now') WHERE id = NEW.id;
END;
