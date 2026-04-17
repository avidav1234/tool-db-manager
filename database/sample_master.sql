-- Sample utensili master per test export
-- Esegui con: sqlite3 database/tool_master.db < database/sample_master.sql

INSERT OR IGNORE INTO utensile (
  codice_interno, alias, id_tipo, diametro_mm, raggio_punta_mm,
  fuori_pinza_mm, cam_sorgente, stato, famiglia_id, impiego
) VALUES
  ('SAMPLE-001', 'D10 R2',    (SELECT id FROM tipo_utensile WHERE codice='BULL'),
   10.0, 2.0, 60.0, 'HyperMill', 'master', 1, 'semifinitura,finitura'),
  ('SAMPLE-002', 'D16 R1',    (SELECT id FROM tipo_utensile WHERE codice='BULL'),
   16.0, 1.0, 75.0, 'HyperMill', 'master', 1, 'sgrossatura,semifinitura'),
  ('SAMPLE-003', 'D8R4 L30',  (SELECT id FROM tipo_utensile WHERE codice='BALL'),
   8.0, 4.0, 45.0, 'HyperMill', 'master', 2, 'finitura'),
  ('SAMPLE-004', 'D12 R0.5',  (SELECT id FROM tipo_utensile WHERE codice='FLAT'),
   12.0, 0.5, 55.0, 'HyperMill', 'master', 3, 'sgrossatura'),
  ('SAMPLE-005', 'P10 L45',   (SELECT id FROM tipo_utensile WHERE codice='DRILL'),
   10.0, 0.0, 80.0, 'HyperMill', 'master', 5, 'foratura');
