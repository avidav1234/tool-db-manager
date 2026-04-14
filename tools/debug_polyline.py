"""
debug_polyline.py — Dump completo polyline holder Hypermill

Estrae tutti i valori numerici plausibili a step 104-byte dall'offset 128
per confrontarli con i modelli CAD (STEP/DXF) come ground truth.

Uso:
  python3 tools/debug_polyline.py [TSF|SLSA|Weldon|all]
"""
import sqlite3, struct, math, sys, os

DB_DEFAULT = os.path.join(os.path.dirname(__file__), '..', 'database', 'tool_master.db')


def dump_holder(poly, name, hid):
    print(f"\n{'='*70}")
    print(f"Holder: {name}  (id={hid}, {len(poly)} bytes)")
    print(f"{'Offset':>8}  {'r (mm)':>12}  {'z (mm)':>12}  {'Note':>20}")
    print(f"{'-'*56}")

    # Dump sistematico ogni 104 byte da 128
    for base in range(128, len(poly) - 15, 104):
        try:
            r = struct.unpack('>d', poly[base:base+8])[0]
            z = struct.unpack('>d', poly[base+8:base+16])[0]
            if math.isnan(r) or math.isnan(z) or math.isinf(r) or math.isinf(z):
                continue
            valid = 0 < r < 500 and 0 < z < 2000
            note = '' if valid else 'SCARTATO'
            if valid or True:  # stampa sempre per debug
                note_str = f' ← {note}' if note else ''
                if valid:
                    print(f"  [{base:>4}]  {r:>12.4f}  {z:>12.4f}{note_str}")
        except Exception as e:
            pass

    # z_tot a offset 552
    if len(poly) >= 560:
        try:
            z_tot = struct.unpack('>d', poly[552:560])[0]
            if 0 < z_tot < 2000:
                print(f"  [ 552]  z_tot      = {z_tot:>12.4f}")
        except Exception:
            pass

    # Dump anche gli offset "strani" (header, flag, fattori)
    print(f"\n  Header fields (possibili fattori/flag):")
    for off in (0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120):
        if off + 8 > len(poly):
            break
        try:
            v = struct.unpack('>d', poly[off:off+8])[0]
            if math.isnan(v) or math.isinf(v):
                continue
            if abs(v) < 1e6:  # valori "ragionevoli"
                print(f"    [{off:>4}]  {v:>14.4f}")
        except Exception:
            pass


def main():
    db_path = DB_DEFAULT
    filter_type = sys.argv[1] if len(sys.argv) > 1 else 'TSF'

    if filter_type.lower() == 'all':
        where = "profilo_polyline_raw IS NOT NULL"
        order = "codice_interno"
    else:
        where = f"codice_interno LIKE '{filter_type}%' AND profilo_polyline_raw IS NOT NULL"
        order = "codice_interno"

    con = sqlite3.connect(db_path)
    cur = con.execute(f"""
        SELECT id, codice_interno, profilo_polyline_raw
        FROM portautensile
        WHERE {where}
        ORDER BY {order}
        LIMIT 20
    """)

    rows = cur.fetchall()
    print(f"Trovati {len(rows)} holder tipo '{filter_type}'\n")

    for hid, name, poly in rows:
        if poly:
            dump_holder(poly, name, hid)

    con.close()


if __name__ == '__main__':
    main()
