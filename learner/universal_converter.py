"""
universal_converter.py
======================
Motore di conversione universale tra formati CAM.

Flusso:
  file_sorgente + profilo_sorgente -> DB master neutro -> profilo_target -> file_output

Uso:
  python universal_converter.py \\
      --input export_hypermill.csv \\
      --profilo-input hypermill_2024 \\
      --profilo-output cimatron_v26 \\
      --output output/per_cimatron.csv
"""

import os
import pandas as pd
import zipfile
from profile_manager import carica_profilo

DEFAULTS = {
    'codice_interno':      lambda i: f'TOOL_{i:04d}',
    'descrizione':         lambda _: 'Utensile importato',
    'tipo':                lambda _: 'FLAT',
    'diametro_mm':         lambda _: 0.0,
    'raggio_punta_mm':     lambda _: 0.0,
    'lunghezza_totale_mm': lambda _: 0.0,
    'lunghezza_tagl_mm':   lambda _: 0.0,
    'num_taglienti':       lambda _: 2,
    'materiale':           lambda _: 'HM',
}


def _leggi_zip(filepath, sep, enc):
    with zipfile.ZipFile(filepath, 'r') as z:
        csv_files = [f for f in z.namelist() if f.lower().endswith('.csv')]
        if not csv_files:
            raise ValueError("Nessun CSV nel ZIP")
        target = next((f for f in csv_files if 'cutter' in f.lower()), csv_files[0])
        with z.open(target) as f:
            content = f.read().decode(enc, errors='replace')
    sep2 = '|' if content.count('|') > content.count(',') else sep
    lines = [l for l in content.splitlines() if not l.startswith('//')]
    from io import StringIO
    return pd.read_csv(StringIO('\n'.join(lines)), sep=sep2, on_bad_lines='skip')


def file_to_master(filepath: str, profilo: dict) -> pd.DataFrame:
    sep = profilo.get('separatore', ',')
    enc = profilo.get('encoding', 'utf-8')
    ext = os.path.splitext(filepath)[1].lower()

    if ext in ('.csv', '.txt'):
        if zipfile.is_zipfile(filepath):
            df = _leggi_zip(filepath, sep, enc)
        else:
            with open(filepath, 'r', encoding=enc, errors='replace') as f:
                raw = f.read()
            sep2 = '|' if raw.count('|') > raw.count(',') else sep
            lines = [l for l in raw.splitlines() if not l.startswith('//')]
            from io import StringIO
            df = pd.read_csv(StringIO('\n'.join(lines)), sep=sep2, on_bad_lines='skip')
    elif ext == '.zip':
        df = _leggi_zip(filepath, sep, enc)
    elif ext in ('.xls', '.xlsx'):
        df = pd.read_excel(filepath)
    else:
        raise ValueError(f"Formato non supportato: {ext}")

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how='all').reset_index(drop=True)
    col_map = profilo.get('colonne', {})
    master_rows = []

    for i, row in df.iterrows():
        record = {}
        for col_file, meta in col_map.items():
            if col_file not in df.columns:
                continue
            campo = meta['campo_master']
            tipo  = meta.get('tipo', 'string')
            val   = row.get(col_file)
            if pd.isna(val) or str(val).strip() == '':
                continue
            if tipo == 'float':
                try: record[campo] = float(str(val).replace(',', '.'))
                except: pass
            elif tipo == 'int':
                try: record[campo] = int(float(str(val)))
                except: pass
            elif tipo == 'categoria':
                record[campo] = meta.get('valori', {}).get(str(val).strip(), str(val).strip())
            else:
                record[campo] = str(val).strip()
        for campo, default_fn in DEFAULTS.items():
            if campo not in record or record[campo] in (None, ''):
                record[campo] = default_fn(i)
        master_rows.append(record)

    return pd.DataFrame(master_rows)


def master_to_file(df_master: pd.DataFrame, profilo: dict, output_path: str):
    col_map = profilo.get('colonne', {})
    inverso = {}
    for col_file, meta in col_map.items():
        campo = meta['campo_master']
        valori_inv = {v: k for k, v in meta.get('valori', {}).items()}
        inverso[campo] = {'col_file': col_file, 'tipo': meta.get('tipo', 'string'), 'valori_inv': valori_inv}

    rows_out = []
    for _, row in df_master.iterrows():
        record = {}
        for campo, info in inverso.items():
            val = row.get(campo)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                record[info['col_file']] = ''
                continue
            if info['tipo'] == 'categoria':
                record[info['col_file']] = info['valori_inv'].get(str(val), str(val))
            else:
                record[info['col_file']] = val
        rows_out.append(record)

    df_out = pd.DataFrame(rows_out)
    col_order = [m['col_file'] for m in inverso.values() if m['col_file'] in df_out.columns]
    df_out = df_out[[c for c in col_order if c in df_out.columns]]
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    sep = profilo.get('separatore', ',')
    ext = os.path.splitext(output_path)[1].lower()
    if ext in ('.xls', '.xlsx'):
        df_out.to_excel(output_path, index=False)
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            if sep == '|':
                f.write('//CimatronE26.00\n')
                f.write(f'//Cutters count={len(df_out)}\n')
            df_out.to_csv(f, sep=sep, index=False)
    print(f"Output: {output_path} ({len(df_out)} utensili)")
    return output_path


def converti(input_path, nome_profilo_input, nome_profilo_output, output_path) -> str:
    profilo_in  = carica_profilo(nome_profilo_input)
    profilo_out = carica_profilo(nome_profilo_output)
    df_master   = file_to_master(input_path, profilo_in)
    print(f"{len(df_master)} utensili nel formato master")
    master_to_file(df_master, profilo_out, output_path)
    return output_path


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',          required=True)
    parser.add_argument('--profilo-input',  required=True)
    parser.add_argument('--profilo-output', required=True)
    parser.add_argument('--output',         required=True)
    args = parser.parse_args()
    converti(args.input, args.profilo_input, args.profilo_output, args.output)
