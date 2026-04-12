-- ============================================================
-- Tool DB Manager — schema v2.0
-- DB MASTER UNIVERSALE: hub tra tutti i software CAM
-- Logica: importa TUTTO da qualsiasi CAM,
--         esporta solo ciò che serve al CAM di destinazione.
-- L'alias è l'identificativo officina, indipendente dal CAM.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ── Dizionari ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tipo_utensile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codice      TEXT NOT NULL UNIQUE,   -- FLAT, BALL, BULL, DRILL, TAP, REAM, SPOT, TAPER, THREAD, FORM, LOLLIPOP
    descrizione TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materiale_utensile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codice      TEXT NOT NULL UNIQUE,   -- HM, HSS, CBN, PCD, Ceramica, Cermet
    descrizione TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fornitore (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL,
    sito    TEXT,
    note    TEXT
);

-- ── Portautensile ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS portautensile (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    codice_interno   TEXT NOT NULL UNIQUE,
    descrizione      TEXT,
    tipo_attacco     TEXT,       -- HSK-A63, BT40, ISO40, CAT40, Weldon, ER...
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
    lunghezza_mm     REAL,
    UNIQUE(id_portautensile, numero_segmento)
);

-- ── Tabella PRINCIPALE ──────────────────────────────────────────────────────
-- Hub universale: contiene TUTTI i dati importabili da qualsiasi CAM.
-- Ogni CAM sorgente popola i campi che conosce; gli altri restano NULL.
-- L'esportatore verso un CAM di destinazione legge solo i campi necessari.

CREATE TABLE IF NOT EXISTS utensile (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    -- ── Identificazione ───────────────────────────────────────────────────
    codice_interno          TEXT NOT NULL UNIQUE,
    -- alias = NOME OFFICINA, indipendente dal CAM
    -- Cimatron: campo "Commento" (ID 1102)
    -- Hypermill: field "Tool ID" / "User Ref"
    -- Mastercam: "Tool comment"
    -- Fusion 360: "Description"
    alias                   TEXT,
    codice_catalogo         TEXT,       -- codice fornitore/catalogo
    descrizione             TEXT,       -- descrizione tecnica libera
    sito_web                TEXT,       -- URL scheda tecnica
    num_magazzino           INTEGER,    -- posizione magazzino CNC

    -- ── Tracciabilità CAM sorgente ─────────────────────────────────────────
    cam_sorgente            TEXT,       -- 'Cimatron','Hypermill','Mastercam','Fusion360','WorkNC','NX'...
    id_originale_cam        TEXT,       -- ID/nome nel sistema CAM di origine

    -- ── Classificazione ───────────────────────────────────────────────────
    id_tipo                 INTEGER NOT NULL DEFAULT 1 REFERENCES tipo_utensile(id),
    id_materiale            INTEGER NOT NULL DEFAULT 1 REFERENCES materiale_utensile(id),
    id_fornitore            INTEGER REFERENCES fornitore(id),
    id_portautensile        INTEGER REFERENCES portautensile(id),
    tecnologia              TEXT,       -- Fresatura, Foratura, Filettatura, Alesatura, Tornitura

    -- ── Geometria corpo utensile ───────────────────────────────────────────
    diametro_mm             REAL NOT NULL DEFAULT 0,
    raggio_punta_mm         REAL NOT NULL DEFAULT 0,   -- corner radius (0=flat, =D/2 ball)
    angolo_punta_gradi      REAL,       -- angolo punta (punte: 118-140°, spot: 60-120°)
    lunghezza_totale_mm     REAL NOT NULL DEFAULT 0,
    lunghezza_tagl_mm       REAL NOT NULL DEFAULT 0,   -- lunghezza utile / clear length
    lunghezza_tagl2_mm      REAL,       -- lunghezza tagliente secondaria (cut length)
    num_taglienti           INTEGER,    -- numero di taglienti / flute count
    conico                  INTEGER DEFAULT 0,          -- flag: utensile conico
    angolo_conico_gradi     REAL,       -- angolo conicità / taper angle
    angolo_elica_gradi      REAL,       -- angolo elica / helix angle (Hypermill, Mastercam)
    raggio_raccordo_mm      REAL,       -- raggio raccordo base (fillet)
    passo_mm                REAL,       -- passo filetto (maschi/filiere)
    num_filetti             INTEGER,    -- numero filetti

    -- ── Stelo / Shank ─────────────────────────────────────────────────────
    tipo_attacco            TEXT,       -- HSK-A63, BT40, ISO40, Weldon, Cilindrico...
    classe_tolleranza       TEXT,       -- h6, h8, etc.
    diam_stelo_mm           REAL,       -- diametro principale stelo
    diam_stelo_sup_mm       REAL,       -- diametro superiore stelo (sezione conica)
    diam_stelo_inf_mm       REAL,       -- diametro inferiore stelo
    lungh_cono_stelo_mm     REAL,       -- lunghezza cono stelo
    lungh_libera_stelo_mm   REAL,       -- zona libera stelo (non a contatto con pinza)
    angolo_cono_stelo_gradi REAL,
    -- Stelo secondario (utensili a doppio stelo)
    diam_stelo2_sup_mm      REAL,
    diam_stelo2_inf_mm      REAL,
    lungh_cono_stelo2_mm    REAL,
    lungh_libera_stelo2_mm  REAL,
    angolo_cono_stelo2_gradi REAL,

    -- ── Portautensile / Holder ─────────────────────────────────────────────
    nome_pinza              TEXT,       -- codice holder (es. HSL_D10-NEW)
    lungh_presa_mm          REAL,       -- lunghezza presa in pinza
    fuori_pinza_mm          REAL,       -- *** DATO CRITICO: distanza punta → inizio pinza ***
                                        -- usato da tutti i CAM per sicurezza in macchina
    lungh_libera_prolunga_mm REAL,      -- lunghezza libera con eventuale prolunga

    -- ── Parametri di taglio DEFAULT ────────────────────────────────────────
    -- Valori generici dell'utensile (non legati al materiale pezzo).
    -- I valori per materiale specifico sono in condizioni_taglio.
    avanzamento_default     REAL,       -- Vf mm/min (Cimatron: 4101)
    rotazione_default       REAL,       -- RPM       (Cimatron: 4102)
    vc_default              REAL,       -- Vc m/min  (Cimatron: 4103)
    fz_default              REAL,       -- Fz mm/z   (Cimatron: 4104)
    passo_z_default         REAL,       -- ap mm     (Cimatron: 5101)
    passo_lat_default       REAL,       -- ae mm     (Cimatron: 5102)
    tolleranza_default      REAL,       -- tolleranza lavorazione mm (Cimatron: 5106)
    vita_utensile           INTEGER,    -- vita utensile min/colpi (Cimatron: 4202)

    -- ── Macchina / Ciclo ──────────────────────────────────────────────────
    dir_rotazione           TEXT,       -- CW / CCW  (Cimatron: 4203)
    refrigerante            TEXT,       -- OFF/Flood/Mist/Through/Air (Cimatron: 4204)
    distanza_pivot          REAL,       -- distanza pivot (Cimatron: 4205)

    -- ── Dati specifici altri CAM ───────────────────────────────────────────
    -- Hypermill
    hm_tool_number          INTEGER,    -- numero utensile Hypermill
    hm_tool_type_id         TEXT,       -- ID tipo interno Hypermill
    hm_coolant_type         TEXT,       -- tipo refrigerante Hypermill
    -- Mastercam
    mc_tool_number          INTEGER,
    mc_offset_number        INTEGER,
    mc_holder_id            TEXT,
    -- Fusion 360
    f360_library            TEXT,       -- libreria Fusion 360
    f360_product_id         TEXT,
    -- WorkNC
    wnc_tool_id             TEXT,
    -- NX / Siemens
    nx_tool_number          INTEGER,
    nx_adjust_register      INTEGER,

    -- ── Note e stato ──────────────────────────────────────────────────────
    note                    TEXT,
    attivo                  INTEGER NOT NULL DEFAULT 1,
    data_inserimento        TEXT NOT NULL DEFAULT (datetime('now')),
    data_modifica           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Condizioni di taglio per materiale ────────────────────────────────────
-- Parametri taglio specifici per combinazione utensile + materiale pezzo.
-- Cimatron: file Material.csv (ID 8xxx). Altri CAM hanno strutture simili.

CREATE TABLE IF NOT EXISTS condizioni_taglio (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_utensile         INTEGER NOT NULL REFERENCES utensile(id) ON DELETE CASCADE,
    materiale_pezzo     TEXT NOT NULL,  -- es. '1.2311', 'Alluminio', 'Acciaio'
    applicazione        TEXT,           -- es. 'Sgrossatura', 'Finitura'
    cam_sorgente        TEXT,           -- da quale CAM viene questo set di parametri
    -- Parametri (nomi allineati alla tabella utensile)
    vc_m_min            REAL,           -- velocità taglio [m/min]     (Cimatron: 8103)
    rotazione_rpm       REAL,           -- velocità mandrino [giri/min] (Cimatron: 8102)
    fz_mm_z             REAL,           -- avanzamento per dente [mm/z] (Cimatron: 8104)
    avanzamento_mm_min  REAL,           -- avanzamento tavola [mm/min]  (Cimatron: 8101)
    ap_mm               REAL,           -- passo in Z [mm]              (Cimatron: 8201)
    ae_mm               REAL,           -- passo laterale [mm]          (Cimatron: 8202)
    rompitruciolo       REAL,           -- parametro rompitruciolo      (Cimatron: 8301)
    decrementa          REAL,           -- decremento                   (Cimatron: 8302)
    refrigerante        TEXT,           -- tipo refrigerante             (Cimatron: 8401)
    note                TEXT,
    UNIQUE(id_utensile, materiale_pezzo, applicazione)
);

-- ── Profilo sagomato ──────────────────────────────────────────────────────
-- Geometria dettagliata per utensili speciali (lollipop, forma, sagomati)

CREATE TABLE IF NOT EXISTS profilo_sagomato (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    id_utensile     INTEGER NOT NULL REFERENCES utensile(id) ON DELETE CASCADE,
    sequenza        INTEGER NOT NULL,
    tipo_segmento   TEXT,   -- LINE, ARC, BEZIER
    x1_mm REAL, y1_mm REAL,
    x2_mm REAL, y2_mm REAL,
    raggio_mm REAL,
    UNIQUE(id_utensile, sequenza)
);

-- ── Log export verso CAM ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS log_export (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cam_destinazione TEXT NOT NULL,  -- 'Cimatron','Hypermill','Mastercam','GCode'...
    formato         TEXT,
    num_utensili    INTEGER,
    data_export     TEXT NOT NULL DEFAULT (datetime('now')),
    filepath        TEXT,
    note            TEXT
);

-- ── Trigger: aggiorna data_modifica ───────────────────────────────────────

CREATE TRIGGER IF NOT EXISTS utensile_upd
    AFTER UPDATE ON utensile
BEGIN
    UPDATE utensile SET data_modifica = datetime('now') WHERE id = NEW.id;
END;

-- ── Indici ────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_utensile_codice    ON utensile(codice_interno);
CREATE INDEX IF NOT EXISTS idx_utensile_alias     ON utensile(alias);
CREATE INDEX IF NOT EXISTS idx_utensile_tipo      ON utensile(id_tipo);
CREATE INDEX IF NOT EXISTS idx_utensile_cam       ON utensile(cam_sorgente);
CREATE INDEX IF NOT EXISTS idx_condizioni_ut      ON condizioni_taglio(id_utensile);

-- ── Dati default dizionari ─────────────────────────────────────────────────

INSERT OR IGNORE INTO tipo_utensile(codice, descrizione) VALUES
    ('FLAT',    'Fresa piatta / End Mill'),
    ('BALL',    'Fresa sferica / Ball Mill'),
    ('BULL',    'Fresa torica / Bull Nose'),
    ('DRILL',   'Punta / Drill'),
    ('TAP',     'Maschio / Tap'),
    ('REAM',    'Alesatore / Reamer'),
    ('SPOT',    'Centratore / Spot Drill'),
    ('TAPER',   'Fresa conica / Taper'),
    ('THREAD',  'Pettine filettatore / Thread Mill'),
    ('FORM',    'Utensile sagomato / Form Tool'),
    ('LOLLIPOP','Fresa a T / Lollipop'),
    ('BORING',  'Barra di alesatura / Boring Bar'),
    ('TURN',    'Inserto tornitura / Turning Insert'),
    ('UNKNOWN', 'Tipo non definito');

INSERT OR IGNORE INTO materiale_utensile(codice, descrizione) VALUES
    ('HM',       'Metallo duro / Carbide'),
    ('HSS',      'Acciaio rapido / High Speed Steel'),
    ('HSS-E',    'Acciaio rapido cobalto'),
    ('CBN',      'Nitruro di boro cubico'),
    ('PCD',      'Diamante policristallino'),
    ('CERAMICA', 'Ceramica'),
    ('CERMET',   'Cermet'),
    ('UNKNOWN',  'Materiale non definito');
