"""
WorkNC Database Plugin v1.0
Rileva e importa database di utensili da WorkNC (formato JS con CSV semicolon-delimited)
"""

import os, sys, re, csv
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from plugins._base import PluginCAM


class WorkNCPlugin(PluginCAM):
    """Plugin per lettura database WorkNC formato .js"""

    software = "WorkNC"
    versione = "1.0"
    estensioni = [".js"]
    descrizione = "Database utensili WorkNC in formato JavaScript CSV"
    autore = "agent"

    FIRMA = {
        "const rawData": 0.9,
        "Alias Utensile": 0.8,
        "Diametro": 0.8,
    }

    def rileva(self, filepath: str) -> float:
        """Rileva confidenza se è un database WorkNC"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                header = f.read(1000)

            score = 0.0
            for sig, weight in self.FIRMA.items():
                if sig in header:
                    score = max(score, weight)

            return score
        except:
            return 0.0

    def analizza(self, filepath: str) -> dict:
        """Estrae metadata dal database WorkNC"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Estrai la sezione backtick tra const rawData = ` e `;
            match = re.search(r'const rawData = `([^`]+)`', content, re.DOTALL)
            if not match:
                return {"errore": "const rawData non trovato"}

            csv_content = match.group(1)
            lines = csv_content.strip().split('\n')

            if not lines:
                return {"errore": "CSV vuoto"}

            # Parse header
            header_line = lines[0].strip()
            headers = [h.strip() for h in header_line.split(';')]

            # Parse righe dati
            reader = csv.reader(StringIO('\n'.join(lines[1:])), delimiter=';')
            rows = list(reader)

            return {
                "software": "WorkNC",
                "formato": "javascript_csv_semicolon",
                "intestazioni": headers,
                "num_righe": len(rows),
                "num_colonne": len(headers),
                "campioni": rows[:3] if rows else []
            }
        except Exception as e:
            return {"errore": str(e)}

    def importa(self, filepath: str, db_path: str, dry_run: bool = False) -> dict:
        """Importa utensili WorkNC nel database master"""
        try:
            headers, rows = self._estrai_csv(filepath)

            conn = self._conn(db_path)
            cur = conn.cursor()

            mapping = {
                "Numero": "numero",
                "Alias Utensile": "alias_utensile",
                "Nome Utensile": "nome_utensile",
                "Tipo": "tipo_utensile",
                "Diametro": "diam_tagl1_mm",
                "Raggio": "raggio_tagl1_mm",
                "Denti(Z)": "num_denti_z",
                "Vel di taglio (Vc)": "vc_m_min",
                "F/dente (fz)": "fz_mm_dente",
                "F/foratura(f)": "f_mm_giro",
            }

            inseriti = 0
            errori = []

            for idx, row in enumerate(rows):
                try:
                    alias = self._to_str(row.get("Alias Utensile", ""))
                    if not alias:
                        continue

                    nome = self._to_str(row.get("Nome Utensile", alias))
                    tipo = self._to_str(row.get("Tipo", "UNKNOWN"))
                    diam = self._to_float(row.get("Diametro", None))
                    raggio = self._to_float(row.get("Raggio", None))
                    denti = self._to_int(row.get("Denti(Z)", None))
                    vc = self._to_float(row.get("Vel di taglio (Vc)", None))
                    fz = self._to_float(row.get("F/dente (fz)", None))
                    f = self._to_float(row.get("F/foratura(f)", None))

                    tipo_id = self._get_tipo_id(conn, tipo)

                    if not dry_run:
                        cur.execute("""
                            INSERT OR REPLACE INTO utensile (
                                alias_utensile, nome_utensile, tipo_id,
                                diam_tagl1_mm, raggio_tagl1_mm, num_denti_z,
                                vc_m_min, fz_mm_dente, f_mm_giro
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (alias, nome, tipo_id, diam, raggio, denti, vc, fz, f))
                        inseriti += 1
                    else:
                        inseriti += 1

                except Exception as e:
                    errori.append(f"Riga {idx}: {str(e)}")

            if not dry_run:
                conn.commit()
            conn.close()

            return {
                "ok": True,
                "inseriti": inseriti,
                "errori": errori,
                "dry_run": dry_run
            }

        except Exception as e:
            return {"ok": False, "errore": str(e)}

    def _estrai_csv(self, filepath):
        """Estrae il CSV dal file .js WorkNC e ritorna intestazioni e righe"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        match = re.search(r'const rawData = `([^`]+)`', content, re.DOTALL)
        if not match:
            raise ValueError("Formato WorkNC non riconosciuto: const rawData non trovato")

        csv_content = match.group(1)
        lines = csv_content.strip().split('\n')

        header_line = lines[0].strip()
        headers = [h.strip() for h in header_line.split(';')]

        reader = csv.DictReader(
            StringIO('\n'.join(lines[1:])),
            fieldnames=headers,
            delimiter=';'
        )
        rows = list(reader)

        return headers, rows


# Export per il loader
plugin_class = WorkNCPlugin
