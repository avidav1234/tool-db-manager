"""
hypermill_importer.py  —  v2.0
Importa utensili da database Hypermill (.db SQLite) nel DB master Tool DB Manager.
Mappatura verificata empiricamente su Database_Vetimec_2025.db — 468/468 NCTools (100%)

Tipi supportati:
  1 = Ballmill      /HM02  -> BALL
  2 = Endmill       /HM01  -> FLAT
  3 = Radiusmill    /HM03  -> BULL
  4 = Drilltool     /HM04  -> DRILL
  5 = Lollipop      /HM05  -> BALL  (collo lungo, stesso schema geometrico)
  6 = Woodruff      /HM06  -> FORM  (disco T-slot)
  9 = ChamferedCutter/HM11 -> FORM  (smusso)
 15 = ThreadMill    /HM09  -> THREAD
 16 = Reamer        /HM14  -> REAM
"""
import sqlite3, os, sys, re

TIPO_MAP = {1:'BALL',2:'FLAT',3:'BULL',4:'DRILL',5:'BALL',6:'FORM',9:'FORM',15:'THREAD',16:'REAM'}

def is_hypermill_db(path):
    try:
        con = sqlite3.connect(path)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        return {'NCTools','Tools','GeometryClasses','Holders','Materials'}.issubset(tables)
    except Exception: return False

def _arr(v, dec=3):
    if v is None: return None
    try:
        f=float(v)
        if f==0.0: return None
        return round(f,1) if abs(f-round(f))<0.0001 else round(f,dec)
    except Exception: return None

def estrai_geometria(tool, nc):
    def p(i): return _arr(tool.get(f'dbl_param{i}'))
    def ip(i): return tool.get(f'int_param{i}')
    typ=tool['tool_type_id']
    geo={'diametro_mm':p(4),'diametro_stelo_mm':p(2),'lunghezza_totale_mm':_arr(tool.get('total_length')),'numero_taglienti':ip(1) or None,'fuori_pinza_mm':_arr(nc.get('tool_length')),'lungh_assemblaggio_mm':_arr(nc.get('gage_length'))}
    if typ in (1,5):
        geo['raggio_punta_mm']=round(float(p(4) or 0)/2,4) if p(4) else None
        if p(8) and p(8)!=p(4): geo['diam_scarico_mm']=p(8)
        if typ==5: geo['lung_collo_mm']=p(3)
    elif typ==2:
        geo['raggio_punta_mm']=0.0
        geo['lunghezza_tagl_mm']=p(13) or _arr(nc.get('tool_length'))
    elif typ==3:
        geo['raggio_punta_mm']=p(8)
        geo['lunghezza_tagl_mm']=p(13) or _arr(nc.get('tool_length'))
    elif typ==4:
        geo['angolo_punta_gradi']=p(7)
        geo['lunghezza_tagl_mm']=p(5) or _arr(nc.get('tool_length'))
    elif typ==6:
        geo['raggio_punta_mm']=p(7)
        geo['spessore_disco_mm']=p(5)
        geo['diam_foro_mm']=p(8)
    elif typ==9:
        geo['angolo_conico_gradi']=p(8)
        geo['lung_tagl_chamfer_mm']=p(7)
    elif typ==15:
        geo['passo_mm']=p(9)
        geo['diam_nucleo_mm']=p(4)
    elif typ==16:
        geo['diam_pilota_mm']=p(9)
        geo['angolo_entrata_gradi']=p(10)
        geo['lunghezza_tagl_mm']=_arr(nc.get('tool_length'))
    return {k:v for k,v in geo.items() if v is not None}

def _ensure_columns(con):
    extra=[('origine','TEXT'),('diam_scarico_mm','REAL'),('lung_collo_mm','REAL'),('spessore_disco_mm','REAL'),('diam_foro_mm','REAL'),('lung_tagl_chamfer_mm','REAL'),('diam_nucleo_mm','REAL'),('diam_pilota_mm','REAL'),('angolo_entrata_gradi','REAL'),('lungh_assemblaggio_mm','REAL')]
    existing={r[1] for r in con.execute("PRAGMA table_info(utensile)")}
    for col,typ in extra:
        if col not in existing:
            try: con.execute(f"ALTER TABLE utensile ADD COLUMN {col} {typ}")
            except Exception: pass

def _upsert_utensile(con, rec):
    existing=con.execute("SELECT id FROM utensile WHERE codice_interno=?",(rec['codice_interno'],)).fetchone()
    cols=list(rec.keys()); vals=[rec[c] for c in cols]
    if existing:
        set_clause=', '.join(f"{c}=?" for c in cols if c!='codice_interno')
        set_vals=[rec[c] for c in cols if c!='codice_interno']
        con.execute(f"UPDATE utensile SET {set_clause} WHERE codice_interno=?",set_vals+[rec['codice_interno']])
    else:
        con.execute(f"INSERT INTO utensile ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",vals)

def importa_hypermill_db(hm_path, master_path, dry_run=False, log_fn=None):
    def log(msg):
        if log_fn: log_fn(msg)
    if not is_hypermill_db(hm_path): raise ValueError(f"Non e un DB Hypermill: {hm_path}")
    con_hm=sqlite3.connect(hm_path); con_hm.row_factory=sqlite3.Row
    con_m=sqlite3.connect(master_path); con_m.row_factory=sqlite3.Row
    _ensure_columns(con_m)
    stats={'importati':0,'skippati':0,'errori':0,'dettaglio':[]}
    nc_rows=con_hm.execute("""
        SELECT n.id AS nc_id, n.nc_name, n.nc_number_str AS nc_number,
               n.tool_length, n.gage_length, t.*,
               h.name AS holder_name, gc.name AS tipo_nome,
               mfr.name AS manufacturer_name
        FROM NCTools n
        JOIN Tools t ON n.tool_id=t.id
        JOIN GeometryClasses gc ON t.tool_type_id=gc.id
        LEFT JOIN Holders h ON n.holder_id=h.id
        LEFT JOIN Manufacturers mfr ON t.manufacturer_id=mfr.manufacturer_id
        ORDER BY t.tool_type_id, t.dbl_param4
    """).fetchall()
    log(f"Trovati {len(nc_rows)} NCTools")
    for row in nc_rows:
        nc=dict(row); typ=nc['tool_type_id']; tipo_master=TIPO_MAP.get(typ)
        if not tipo_master:
            stats['skippati']+=1; stats['dettaglio'].append({'nc_id':nc['nc_id'],'esito':'skip_tipo','nc_name':nc['nc_name']}); continue
        if not nc.get('dbl_param4'):
            stats['skippati']+=1; stats['dettaglio'].append({'nc_id':nc['nc_id'],'esito':'skip_no_D','nc_name':nc['nc_name']}); continue
        try:
            geo=estrai_geometria(nc,nc)
            codice=(nc.get('nc_number') or nc.get('nc_name') or '').strip() or f"HM_{nc['nc_id']}"
            record={'codice_interno':codice,'descrizione':nc.get('name') or nc.get('nc_name') or '','tipo':tipo_master,'nome_pinza':nc.get('holder_name') or '','produttore':nc.get('manufacturer_name') or '','codice_catalogo':nc.get('ordering_code') or '','origine':'hypermill_import','attivo':1,**geo}
            if not dry_run: _upsert_utensile(con_m,record)
            stats['importati']+=1; stats['dettaglio'].append({'nc_id':nc['nc_id'],'esito':'ok','nc_name':nc['nc_name'],'tipo':tipo_master,'D':geo.get('diametro_mm')})
            log(f"  OK  [{tipo_master:6s}] D={geo.get('diametro_mm'):<6}  {codice}")
        except Exception as e:
            stats['errori']+=1; stats['dettaglio'].append({'nc_id':nc['nc_id'],'esito':'errore','nc_name':nc['nc_name'],'err':str(e)}); log(f"  ERR {nc['nc_name']}: {e}")
    if not dry_run: con_m.commit()
    con_hm.close(); con_m.close()
    log(f"Risultato: {stats['importati']} importati, {stats['skippati']} skippati, {stats['errori']} errori")
    return stats

if __name__=='__main__':
    if len(sys.argv)<3:
        print("Uso: python3 hypermill_importer.py <hypermill.db> <master.db> [--dry-run]"); sys.exit(1)
    hm_path=sys.argv[1]; master_path=sys.argv[2]; dry='--dry-run' in sys.argv
    print(f"{'[DRY RUN] ' if dry else ''}Import: {hm_path} -> {master_path}")
    stats=importa_hypermill_db(hm_path,master_path,dry_run=dry,log_fn=print)
    print(f"Fine. Importati={stats['importati']} Skippati={stats['skippati']} Errori={stats['errori']}")
