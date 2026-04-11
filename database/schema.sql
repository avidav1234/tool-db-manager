-- ============================================================
-- schema.sql - Tool DB Manager
-- Analisi completa file Cimatron 2025 SP5
-- Tutti i campi verificati su dati reali
-- ============================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tipo_utensile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codice      TEXT NOT NULL UNIQUE,
    descrizione TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materiale_utensile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codice      TEXT NOT NULL UNIQUE,
    descrizione TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fornitore (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL,
    sito    TEXT,
    note    TEXT
);

-- ---------------------------------------------------------------
-- PORTAUTENSILI (da Holders_*.csv - 23 nel file aziendale)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portautensile (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    codice_interno   TEXT NOT NULL UNIQUE,
    descrizione      TEXT,
    tipo_adattatore  TEXT,       -- HSK-A63, BT40, ISO40, ...
    num_segmenti     INTEGER DEFAULT 0,
    num_seg_mandrino INTEGER DEFAULT 0,
    tipo_visualiz    INTEGER DEFAULT 0,
    attivo           INTEGER NOT NULL DEFAULT 1,
    data_inserimento TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portautensile_segmento (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    id_portautensile INTEGER NOT NULL REFERENCES portautensile(id) ON DELETE CASCADE,
    numero_segmento  INTEGER NOT NULL,
    diametro_inf_mm  REAL,
    diametro_sup_mm  REAL,
    altezza_cono_mm  REAL,
    altezza_totale_mm REAL,
    UNIQUE(id_portautensile, numero_segmento)
);

-- ---------------------------------------------------------------
-- UTENSILI (da Cutters_*.csv - 96 nel file aziendale)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS utensile (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identificazione
    codice_interno          TEXT NOT NULL UNIQUE,
    codice_catalogo         TEXT,
    descrizione             TEXT,
    sito_web                TEXT,
    num_magazzino           INTEGER,

    -- Classificazione
    id_tipo                 INTEGER NOT NULL REFERENCES tipo_utensile(id),
    id_materiale            INTEGER NOT NULL REFERENCES materiale_utensile(id),
    id_fornitore            INTEGER REFERENCES fornitore(id),
    id_portautensile        INTEGER REFERENCES portautensile(id),
    tecnologia              TEXT,

    -- Geometria corpo utensile
    diametro_mm             REAL NOT NULL DEFAULT 0,
    raggio_punta_mm         REAL NOT NULL DEFAULT 0,
    angolo_punta_gradi      REAL,
    lunghezza_totale_mm     REAL NOT NULL DEFAULT 0,
    lunghezza_tagl_mm       REAL NOT NULL DEFAULT 0,   -- lunghezza utile (2109)
    lunghezza_tagl2_mm      REAL,                       -- lunghezza tagliente (2110)
    num_taglienti           INTEGER NOT NULL DEFAULT 2,
    conico                  INTEGER DEFAULT 0,
    angolo_conico_gradi     REAL,

    -- Assemblaggio con pinza (dati inline dal file Cimatron)
    -- Questi dati descrivono come l'utensile e' montato nella pinza
    nome_pinza              TEXT,       -- (3101) nome portautensile/pinza usato
    lungh_presa_mm          REAL,       -- (3102) quanto utensile e' inserito nella pinza
    fuori_pinza_mm          REAL,       -- (3103) DISTANZA PUNTA-INIZIO PINZA = dato critico per programmatori CAM
    lungh_libera_prolunga_mm REAL,      -- (3105) lunghezza libera con prolunga

    -- Stelo principale (2201-2207)
    diam_stelo_sup_mm       REAL,       -- (2202) diametro superiore stelo
    diam_stelo_inf_mm       REAL,       -- (2203) diametro inferiore stelo
    lungh_cono_stelo_mm     REAL,       -- (2206) lunghezza cono stelo
    lungh_libera_stelo_mm   REAL,       -- (2207) zona libera stelo (non a contatto con pinza)
    angolo_cono_stelo_gradi REAL,       -- (2205)
    usa_angolo_cono_stelo   INTEGER DEFAULT 0,

    -- Stelo secondario (2208-2213) - usato per utensili con doppio stelo
    diam_stelo2_sup_mm      REAL,       -- (2209)
    diam_stelo2_inf_mm      REAL,       -- (2210)
    lungh_cono_stelo2_mm    REAL,       -- (2212)
    lungh_libera_stelo2_mm  REAL,       -- (2213)
    angolo_cono_stelo2_gradi REAL,      -- (2211)

    -- Parametri di taglio di default (dal profilo utensile, NON per materiale)
    avanzamento_default     REAL,       -- (4101) Vf mm/min
    rotazione_default       REAL,       -- (4102) N rpm
    vc_default              REAL,       -- (4103) Vc m/min
    fz_default              REAL,       -- (4104) Fz mm/z
    passo_z_default         REAL,       -- (5101) ap mm
    passo_lat_default       REAL,       -- (5102) ae mm
    tolleranza_default      REAL,       -- (5106)
    vita_utensile           INTEGER,    -- (4202) in minuti o cicli

    -- Macchina
    dir_rotazione           TEXT,       -- (4203) CW/CCW
    refrigerante            TEXT,       -- (4204) OFF/Flood/Mist/Through/Air
    distanza_pivot          REAL,       -- (4205)

    -- Filettatura
    passo_mm                REAL,       -- (2123)

    -- Note e stato
    note                    TEXT,
    attivo                  INTEGER NOT NULL DEFAULT 1,
    data_inserimento        TEXT NOT NULL DEFAULT (datetime('now')),
    data_modifica           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- CONDIZIONI DI TAGLIO PER MATERIALE (da Material_*.csv)
-- 287 combinazioni utensile x materiale nel file aziendale
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS condizioni_taglio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_utensile     INTEGER NOT NULL REFERENCES utensile(id) ON DELETE CASCADE,
    materiale_pezzo TEXT NOT NULL,
    applicazione    TEXT,
    -- Parametri Cimatron (ID 8xxx)
    vc_m_min        REAL,    -- (8103) velocita taglio [m/min]
    n_rpm           REAL,    -- (8102) velocita mandrino [giri/min]
    fz_mm           REAL,    -- (8104) avanzamento per dente [mm/z]
    vf_mm_min       REAL,    -- (8101) avanzamento tavola [mm/min]
    ap_mm           REAL,    -- (8201) passo in Z [mm]
    ae_mm           REAL,    -- (8202) passo laterale [mm]
    rompitruciolo   REAL,    -- (8301)
    decrementa      REAL,    -- (8302)
    refrigerante    TEXT,    -- (8401)
    note            TEXT,
    UNIQUE(id_utensile, materiale_pezzo, applicazione)
);

-- ---------------------------------------------------------------
-- PROFILI SAGOMATI (da Contour_*.csv - 17 nel file aziendale)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profilo_sagomato (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_utensile     INTEGER NOT NULL REFERENCES utensile(id) ON DELETE CASCADE,
    dati_json       TEXT,
    data_inserimento TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- LOG EXPORT
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS log_export (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cam          TEXT NOT NULL,
    num_utensili INTEGER NOT NULL DEFAULT 0,
    file_output  TEXT,
    timestamp    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- VIEW PRINCIPALE
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS utensile_completo;
CREATE VIEW utensile_completo AS
SELECT
    u.id, u.codice_interno, u.codice_catalogo, u.descrizione, u.sito_web,
    u.num_magazzino,
    t.codice                AS tipo,
    t.descrizione           AS tipo_descrizione,
    m.codice                AS materiale,
    m.descrizione           AS materiale_descrizione,
    f.nome                  AS fornitore,
    p.codice_interno        AS portautensile,
    p.tipo_adattatore       AS adattatore,
    u.tecnologia,
    -- Geometria
    u.diametro_mm, u.raggio_punta_mm, u.angolo_punta_gradi,
    u.lunghezza_totale_mm, u.lunghezza_tagl_mm, u.lunghezza_tagl2_mm,
    u.num_taglienti, u.conico, u.angolo_conico_gradi,
    -- Assemblaggio pinza - dati critici per programmatori CAM
    u.nome_pinza,
    u.lungh_presa_mm,
    u.fuori_pinza_mm,        -- DISTANZA PUNTA -> INIZIO PINZA
    u.lungh_libera_prolunga_mm,
    -- Stelo
    u.diam_stelo_sup_mm, u.diam_stelo_inf_mm,
    u.lungh_cono_stelo_mm, u.lungh_libera_stelo_mm,
    u.diam_stelo2_sup_mm, u.diam_stelo2_inf_mm,
    u.lungh_cono_stelo2_mm, u.lungh_libera_stelo2_mm,
    -- Parametri taglio default
    u.avanzamento_default, u.rotazione_default, u.vc_default, u.fz_default,
    u.passo_z_default, u.passo_lat_default, u.vita_utensile,
    u.dir_rotazione, u.refrigerante,
    u.passo_mm, u.note, u.attivo,
    u.data_inserimento, u.data_modifica
FROM utensile u
JOIN tipo_utensile t      ON u.id_tipo = t.id
JOIN materiale_utensile m ON u.id_materiale = m.id
LEFT JOIN fornitore f     ON u.id_fornitore = f.id
LEFT JOIN portautensile p ON u.id_portautensile = p.id;

-- ---------------------------------------------------------------
-- DATI DI DEFAULT
-- ---------------------------------------------------------------
INSERT OR IGNORE INTO tipo_utensile (codice, descrizione) VALUES
    ('FLAT','Fresa piatta'),('BALL','Fresa sferica'),('BULL','Fresa torica'),
    ('DRILL','Punta'),('TAP','Maschio'),('REAM','Alesatore'),
    ('SPOT','Centratura'),('TAPER','Conico'),('THREAD','Fresa filetto'),('PROBE','Tastatore');

INSERT OR IGNORE INTO materiale_utensile (codice, descrizione) VALUES
    ('HM','Metallo duro'),('HSS','Acciaio rapido'),('HSCo','Acciaio rapido cobalto'),
    ('CBN','Nitruro boro cubico'),('PCD','Diamante policristallino'),('CER','Ceramica');

-- Trigger data_modifica
CREATE TRIGGER IF NOT EXISTS utensile_modifica
AFTER UPDATE ON utensile
BEGIN
    UPDATE utensile SET data_modifica = datetime('now') WHERE id = NEW.id;
END;
