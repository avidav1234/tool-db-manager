-- Inserimento materiali Vetimec
INSERT OR IGNORE INTO Materiali (nome_master, durezza_hrc, note) VALUES
('Dievar_Superior', 52.0, 'Materiale speciale Vetimec'),
('Bohler_W350', 50.0, 'Materiale Vetimec'),
('Acciaio_Normale', 30.0, 'Materiale standard'),
('HP1_1.2343', 48.0, 'Materiale stampi Vetimec');

-- Inserimento famiglie utensile Vetimec
INSERT OR IGNORE INTO FamiglieUtensile (nome, tipo, materiale_tagliente, n_taglienti_default, note) VALUES
('Torico_HM_4Z', 'BULL', 'HM', 4, 'Fresa torica 4 taglienti Metallo Duro'),
('Sferico_HM_2Z', 'BALL', 'HM', 2, 'Fresa sferica 2 taglienti Metallo Duro'),
('Piatta_HM_4Z', 'FLAT', 'HM', 4, 'Fresa piatta 4 taglienti Metallo Duro'),
('Trocoidale_HM_4Z', 'FLAT', 'HM', 4, 'Fresa trocoidale 4 taglienti Metallo Duro'),
('Punta_HM', 'DRILL', 'HM', 2, 'Punta Metallo Duro'),
('Lollipop_HM_2Z', 'LOLLIPOP', 'HM', 2, 'Fresa a T 2 taglienti Metallo Duro'),
('Alesatore_HM', 'REAM', 'HM', 6, 'Alesatore Metallo Duro');
