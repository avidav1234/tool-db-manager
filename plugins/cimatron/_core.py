"""
plugins/cimatron/_core.py — Logica comune a tutte le versioni Cimatron.
NON modificare le MAP consolidate senza test su file reali.
"""
import os, sys, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from plugins._base import PluginCAM

TIPO_MAP = {
    '210201':'FLAT','210202':'BALL','210203':'BULL','210204':'DRILL',
    '210205':'TAP','210206':'REAM','210207':'SPOT','210208':'THREAD',
    '210209':'TAPER','210210':'LOLLIPOP',
}
TECNOLOGIA_MAP = {'210101':'Fresatura','210102':'Foratura','210103':'Tornitura'}
DIR_ROT_MAP = {'420301':'CW','420302':'CCW','420303':'CW'}
REFRIG_MAP = {
    '420401':'OFF','420402':'FLOOD','420403':'MIST','420404':'AIR','420405':'THROUGH',
    'OFF':'OFF','FLOOD':'FLOOD','MIST':'MIST','AIR':'AIR','THROUGH':'THROUGH',
}
CUTTERS_MAP = {
    '1101':'codice_interno','1102':'alias','1103':'sito_web','1201':'num_magazzino',
    '2101':'_tecnologia','2102':'_tipo','2103':'codice_catalogo',
    '2111':'diametro_mm','2112':'raggio_punta_mm','2113':'angolo_punta_gradi',
    '2114':'lunghezza_totale_mm','2115':'lunghezza_tagl_mm','2116':'num_taglienti',
    '2117':'angolo_elica_gradi','2118':'raggio_raccordo_mm','2119':'passo_mm',
    '2121':'diam_libero_mm','2122':'diam_gambo1_mm','2123':'passo_mm',
    '4101':'nome_pinza','4102':'lungh_presa_mm','4103':'fuori_pinza_mm',
    '4201':'vc_default','4202':'vita_utensile',
    '4203':'_dir_rotazione','4204':'_refrigerante','4205':'distanza_pivot',
    '5101':'passo_z_default','5102':'passo_lat_default','5103':'avanzamento_default',
    '5104':'rotazione_default','5105':'vc_default','5106':'tolleranza_default',
    'Avanz.':'avanzamento_default','Fz':'fz_default','Vt':'vc_default',
    'N':'rotazione_default','Passo Z':'passo_z_default',
    'Tolleranza':'tolleranza_default','Passo Laterale':'passo_lat_default',
}
MATERIALE_DEFAULT = 'HM'
FLOAT_FIELDS = {'diametro_mm','raggio_punta_mm','angolo_punta_gradi','lunghezza_totale_mm',
    'lunghezza_tagl_mm','angolo_elica_gradi','raggio_raccordo_mm','passo_mm','diam_libero_mm',
    'diam_gambo1_mm','fuori_pinza_mm','lungh_presa_mm','vc_default','passo_z_default',
    'passo_lat_default','avanzamento_default','fz_default','rotazione_default',
    'tolleranza_default','distanza_pivot'}
INT_FIELDS = {'num_taglienti','vita_utensile','num_magazzino'}

class CimatronCore(PluginCAM):
    software='Cimatron'; versione='core'; estensioni=['.zip']
    TIPO_MAP=TIPO_MAP; DIR_ROT_MAP=DIR_ROT_MAP; REFRIG_MAP=REFRIG_MAP
    CUTTERS_MAP=CUTTERS_MAP; MATERIALE_DEFAULT=MATERIALE_DEFAULT
    TECNOLOGIA_MAP=TECNOLOGIA_MAP

    def rileva(self, filepath):
        try:
            if not filepath.lower().endswith('.zip'): return 0.0
            with zipfile.ZipFile(filepath) as z:
                if not any('Cutters' in n for n in z.namelist()): return 0.0
                return self._match_versione(self._leggi_versione(z, z.namelist()))
        except: return 0.0

    def _leggi_versione(self, z, nomi):
        for fname in nomi:
            if 'Cutters' not in fname: continue
            try:
                raw = z.read(fname)
                for enc in ('utf-16','utf-8-sig','utf-8','latin-1'):
                    try:
                        text = raw.decode(enc)
                        for line in text.splitlines()[:6]:
                            s = line.strip().strip('"')
                            if s.startswith('//') and ('Cimatron' in s or 'V2' in s or 'SP' in s):
                                return s.replace('//','').strip()
                        break
                    except: continue
            except: continue
        return ''

    def _match_versione(self, versione_file):
        return 0.6 if versione_file else 0.5

    def analizza(self, filepath):
        try:
            with zipfile.ZipFile(filepath) as z:
                nomi = z.namelist()
                ver = self._leggi_versione(z, nomi)
                sezioni = {}
                for fname in nomi:
                    if not fname.endswith('.csv'): continue
                    sec = os.path.splitext(os.path.basename(fname))[0]
                    rows, cn, ci = self._leggi_csv(z, fname)
                    sezioni[sec] = {'colonne':cn,'col_ids':ci,'righe':len(rows),'campioni':rows[:3]}
                return {'software':self.software,'versione':ver or self.versione,
                        'plugin':repr(self),'sezioni':sezioni,'meta':{'filepath':filepath}}
        except Exception as e: return {'errore':str(e)}

    def _leggi_csv(self, z, fname):
        raw = z.read(fname); text = None
        for enc in ('utf-16','utf-8-sig','utf-8','latin-1'):
            try: text = raw.decode(enc); break
            except: continue
        if not text: return [],[],[]
        lines = text.splitlines(); nr=ir=-1
        for i,line in enumerate(lines):
            s = line.strip().lstrip('"')
            if s.startswith('//') or s=='' or s.startswith('Cimatron'): continue
            if nr==-1: nr=i; continue
            if ir==-1: ir=i; break
        if nr<0 or ir<0: return [],[],[]
        cn=[c.strip() for c in lines[nr].split('|')]
        ci=[c.strip() for c in lines[ir].split('|')]
        dati=[l for l in lines[ir+1:] if l.strip() and not l.strip().startswith('//')]
        rows=[{ci[j]:parts[j].strip() if j<len(parts) else ''
               for j in range(len(ci))} for parts in [r.split('|') for r in dati]]
        return rows,cn,ci

    def importa(self, filepath, db_path, dry_run=False):
        ins=upd=ign=0; errs=[]; log=[]
        try:
            with zipfile.ZipFile(filepath) as z:
                nomi=z.namelist()
                cf=next((n for n in nomi if 'Cutters' in os.path.basename(n) and n.endswith('.csv')),None)
                if not cf: return {'errore':'Cutters.csv non trovato'}
                rows,_,_=self._leggi_csv(z,cf)
                log.append(f'Letti {len(rows)} utensili')
                conn=self._conn(db_path)
                try:
                    for row in rows:
                        try:
                            _,updated=self._importa_riga(conn,row,dry_run)
                            if updated: upd+=1
                            else: ins+=1
                        except Exception as e: ign+=1; errs.append(str(e))
                    if not dry_run: conn.commit()
                finally: conn.close()
        except Exception as e: return {'errore':str(e),'log':log}
        return {'inseriti':ins,'aggiornati':upd,'ignorati':ign,'errori':errs[:10],'log':log,'dry_run':dry_run}

    def _importa_riga(self, conn, row, dry_run):
        mapped={}
        for id_col,valore in row.items():
            campo=self.CUTTERS_MAP.get(id_col)
            if not campo or not valore or not valore.strip(): continue
            if campo=='_tipo': mapped['_tipo']=self.TIPO_MAP.get(valore,'FLAT')
            elif campo=='_refrigerante': mapped['refrigerante']=self.REFRIG_MAP.get(valore,valore)
            elif campo=='_dir_rotazione': mapped['dir_rotazione']=self.DIR_ROT_MAP.get(valore,valore)
            elif campo=='_tecnologia': mapped['_tecnologia']=self.TECNOLOGIA_MAP.get(valore,valore)
            elif not campo.startswith('_'): mapped[campo]=valore
        codice=self._to_str(mapped.get('codice_interno'))
        if not codice: raise ValueError('codice_interno mancante')
        tipo_cod=mapped.pop('_tipo','FLAT'); mapped.pop('_tecnologia',None)
        tipo_id=self._get_tipo_id(conn,tipo_cod)
        mat_id=self._get_mat_id(conn,self.MATERIALE_DEFAULT)
        for k in list(mapped.keys()):
            if k in FLOAT_FIELDS: mapped[k]=self._to_float(mapped[k])
            elif k in INT_FIELDS: mapped[k]=self._to_int(mapped[k])
            else: mapped[k]=self._to_str(mapped[k])
        params={**mapped,'id_tipo':tipo_id,'id_materiale':mat_id,
                'cam_sorgente':f'{self.software} {self.versione}'}
        esiste=conn.execute("SELECT id FROM utensile WHERE codice_interno=?",(codice,)).fetchone()
        if not dry_run:
            if esiste:
                sets=', '.join(f"{k}=:{k}" for k in params)
                conn.execute(f"UPDATE utensile SET {sets} WHERE codice_interno=:codice_interno",
                             {**params,'codice_interno':codice})
            else:
                cols='codice_interno, '+', '.join(params.keys())
                vals=':codice_interno, '+', '.join(f':{k}' for k in params)
                conn.execute(f"INSERT INTO utensile ({cols}) VALUES ({vals})",
                             {'codice_interno':codice,**params})
        return codice, bool(esiste)
