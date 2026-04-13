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
    u.data_inserimento, u.data_modifica,
  u.d1_serraggio_mm,
  u.d3_corpo_mm,
  u.d_hsk_mm,
  u.nl_serraggio_mm,
  u.z_fine_cono_mm,
  u.a_lungh_holder_mm,
  u.tipo_attacco
FROM utensile u
JOIN tipo_utensile t      ON u.id_tipo = t.id
JOIN materiale_utensile m ON u.id_materiale = m.id
LEFT JOIN fornitore f     ON u.id_fornitore = f.id
LEFT JOIN portautensile p ON u.id_portautensile = p.id;
