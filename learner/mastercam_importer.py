"""
mastercam_importer.py  –  v1.0
Importa utensili da un database Mastercam .tooldb nel DB master Tool DB Manager.

Il formato .tooldb di Mastercam è un database SQLite standard.
Tabelle principali: Tools, Holders, Materials, Operations (schema variabile tra versioni).

Tabelle importate:
  Tools       → utensile  (geometria, tipo, materiale)
  Holders     → portautensile + portautensile_segmento
  Operations  → condizioni_taglio  (Vc, Fz, Vf, ap, ae per materiale)

Note:
  - Lo schema .tooldb varia tra Mastercam 2020, 2021, 2023, 2024, 2025.
  - L'importer prova nomi colonna multipli per ogni campo.
  - Strutture non riconosciute vengono segnalate con warning.
"""
import sqlite3, os, sys, math, re

# ── Mappatura tipo utensile Mastercam → master ─────────────────────────────
# Mastercam usa valori interi o stringhe per tool_type, a seconda della versione.
# Copriamo entrambi i casi.

_MC_TYPE_INT_MAP = {
    0:  'UNKNOWN',
    1:  'FLAT',       # End Mill Flat
    2:  'BALL',       # Ball End Mill
    3:  'BULL',       # Bull Nose
    4:  'DRILL',      # Drill
    5:  'TAP',        # Tap (Right Hand)
    6:  'REAM',       # Reamer
    7:  'BORING',     # Boring Bar
    8:  'FLAT',       # Face Mill (mapped to FLAT)
    9:  'SPOT',       # Spot Drill / Center Drill
    10: 'TAP',        # Tap (Left Hand)
    11: 'THREAD',     # Thread Mill
    12: 'FLAT',       # Slot Mill → FLAT
    13: 'FORM',       # Form Tool
    14: 'TAPER',      # Tapered End Mill
    15: 'LOLLIPOP',   # Lollipop / Undercutting
    16: 'FLAT',       # Shell Mill → FLAT
    17: 'DRILL',      # Spade Drill → DRILL
    18: 'FLAT',       # Chamfer Mill → FLAT
    19: 'FLAT',       # Dove Tail → FLAT
    # Mastercam 2024+ additional types
    20: 'FLAT',       # Key Cutter
    21: 'TURN',       # Turning Insert
    101: 'FLAT',      # Alternate End Mill
    102: 'BALL',      # Alternate Ball
    103: 'BULL',      # Alternate Bull Nose
}

_MC_TYPE_STR_MAP = {
    'endmill':       'FLAT',
    'end mill':      'FLAT',
    'flat end mill': 'FLAT',
    'flat endmill':  'FLAT',
    'facemill':      'FLAT',
    'face mill':     'FLAT',
    'ball':          'BALL',
    'ball end mill': 'BALL',
    'ball endmill':  'BALL',
    'ball nose':     'BALL',
    'bullnose':      'BULL',
    'bull nose':     'BULL',
    'bull':          'BULL',
    'torus':         'BULL',
    'drill':         'DRILL',
    'twist drill':   'DRILL',
    'center drill':  'SPOT',
    'spot drill':    'SPOT',
    'tap':           'TAP',
    'tap rh':        'TAP',
    'tap lh':        'TAP',
    'reamer':        'REAM',
    'boring bar':    'BORING',
    'bore':          'BORING',
    'thread mill':   'THREAD',
    'threadmill':    'THREAD',
    'taper':         'TAPER',
    'tapered':       'TAPER',
    'lollipop':      'LOLLIPOP',
    'undercutter':   'LOLLIPOP',
    'form':          'FORM',
    'chamfer':       'FLAT',
    'dovetail':      'FLAT',
    'dove tail':     'FLAT',
    'shell mill':    'FLAT',
    'slot mill':     'FLAT',
}

# Mappatura materiale utensile Mastercam → master
_MC_MATERIAL_MAP = {
    'carbide':        'HM',
    'solid carbide':  'HM',
    'hm':             'HM',
    'cemented carbide': 'HM',
    'hss':            'HSS',
    'high speed steel': 'HSS',
    'hss-e':          'HSS-E',
    'cobalt':         'HSS-E',
    'cbn':            'CBN',
    'pcd':            'PCD',
    'diamond':        'PCD',
    'ceramic':        'CERAMICA',
    'ceramics':       'CERAMICA',
    'cermet':         'CERMET',
}


def _warn(msg):
    """Stampa un warning su stderr."""
    print(f'[mastercam_importer] WARNING: {msg}', file=sys.stderr)


def _info(msg):
    print(f'[mastercam_importer] {msg}', file=sys.stderr)


# ── Rilevamento database Mastercam ─────────────────────────────────────────

def _get_tables(db_path):
    """Restituisce il set di nomi tabella presenti nel database."""
    try:
        con = sqlite3.connect(db_path)
        tables = {r[0].lower() for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        con.close()
        return tables
    except Exception:
        return set()


def _is_mastercam_tooldb(db_path):
    """Verifica se il file è un database Mastercam .tooldb.

    Controlla la presenza di tabelle chiave. Lo schema varia tra versioni,
    quindi proviamo diversi set di tabelle.
    """
    tables = _get_tables(db_path)
    if not tables:
        return False

    # Set 1: Mastercam 2020+ schema
    if 'tools' in tables:
        return True
    # Set 2: Mastercam con naming alternativo
    if 'tool' in tables:
        return True
    # Set 3: schema con prefisso mc_
    if 'mc_tools' in tables:
        return True
    # Set 4: verifica generica - se ha colonne tipiche di un tool db
    if any('tool' in t for t in tables):
        return True

    return False


def _get_columns(con, table_name):
    """Restituisce il set di nomi colonna per una tabella."""
    try:
        cols = {r[1].lower() for r in con.execute(f"PRAGMA table_info('{table_name}')").fetchall()}
        return cols
    except Exception:
        return set()


def _find_table(con, candidates):
    """Trova la prima tabella esistente tra i candidati (case-insensitive)."""
    tables = {r[0].lower(): r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    for c in candidates:
        if c.lower() in tables:
            return tables[c.lower()]
    return None


def _find_column(columns, candidates, default=None):
    """Trova il primo nome colonna presente tra i candidati."""
    cols_lower = {c.lower(): c for c in columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return default


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        f = float(val)
        return f if f != 0.0 else default
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=None):
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ── Risoluzione tipo utensile ──────────────────────────────────────────────

def _resolve_tool_type(tool_type_val, tool_name=''):
    """Converte il tool_type Mastercam nel codice master (FLAT, BALL, ecc.)."""
    # Prova come intero
    if tool_type_val is not None:
        try:
            tipo_int = int(tool_type_val)
            mapped = _MC_TYPE_INT_MAP.get(tipo_int)
            if mapped:
                return mapped
        except (ValueError, TypeError):
            pass

        # Prova come stringa
        tipo_str = str(tool_type_val).strip().lower()
        mapped = _MC_TYPE_STR_MAP.get(tipo_str)
        if mapped:
            return mapped
        # Fuzzy match
        for key, val in _MC_TYPE_STR_MAP.items():
            if key in tipo_str or tipo_str in key:
                return val

    # Fallback: prova a dedurre dal nome utensile
    if tool_name:
        name_lower = tool_name.lower()
        for key, val in _MC_TYPE_STR_MAP.items():
            if key in name_lower:
                return val

    return 'UNKNOWN'


def _resolve_tool_material(material_val):
    """Converte il materiale utensile Mastercam nel codice master."""
    if material_val is None:
        return 'HM'   # default carbide
    mat_str = str(material_val).strip().lower()
    mapped = _MC_MATERIAL_MAP.get(mat_str)
    if mapped:
        return mapped
    # Fuzzy
    for key, val in _MC_MATERIAL_MAP.items():
        if key in mat_str or mat_str in key:
            return val
    return 'HM'


# ── Detect tipo attacco dal nome holder ────────────────────────────────────

def _detect_tipo_attacco(holder_name):
    s = (holder_name or '').upper()
    if 'HSK' in s:
        m = re.search(r'HSK[-_ ]?([A-F])[-_ ]?(\d+)', s)
        return f"HSK-{m.group(1)}{m.group(2)}" if m else 'HSK63'
    if any(x in s for x in ('BT40', 'BT 40')):
        return 'BT40'
    if any(x in s for x in ('BT50', 'BT 50')):
        return 'BT50'
    if any(x in s for x in ('CAT40', 'CAT 40')):
        return 'CAT40'
    if any(x in s for x in ('CAT50', 'CAT 50')):
        return 'CAT50'
    if any(x in s for x in ('ISO40', 'ISO 40', 'SK40', 'SK 40', 'DIN69871')):
        return 'ISO40'
    if any(x in s for x in ('ISO50', 'ISO 50', 'SK50', 'SK 50')):
        return 'ISO50'
    if 'CAPTO' in s:
        return 'Capto'
    if 'WELDON' in s:
        return 'Weldon'
    if any(x in s for x in ('ER32', 'ER 32')):
        return 'ER32'
    if any(x in s for x in ('ER25', 'ER 25')):
        return 'ER25'
    if any(x in s for x in ('ER40', 'ER 40')):
        return 'ER40'
    if any(x in s for x in ('ER16', 'ER 16')):
        return 'ER16'
    if 'ER' in s:
        return 'ER'
    return None


# ═══════════════════════════════════════════════════════════════════════════
#   IMPORTAZIONE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════════════

def importa_mastercam_tooldb(mc_db_path, master_db_path, dry_run=False):
    """Importa utensili da un file Mastercam .tooldb nel DB master.

    Args:
        mc_db_path:    percorso al file .tooldb (SQLite) di Mastercam
        master_db_path: percorso al DB master tool_master.db
        dry_run:       se True, conta solo senza scrivere

    Returns:
        dict con statistiche: utensili, condizioni_taglio, portautensili, errori
    """
    if not os.path.isfile(mc_db_path):
        return {'errore': f'File non trovato: {mc_db_path}'}

    if not _is_mastercam_tooldb(mc_db_path):
        return {'errore': 'File non riconosciuto come database Mastercam .tooldb'}

    mc = sqlite3.connect(mc_db_path)
    mc.row_factory = sqlite3.Row

    stats = {
        'utensili': 0,
        'condizioni_taglio': 0,
        'portautensili': 0,
        'segmenti_holder': 0,
        'errori': 0,
        'warnings': [],
        'dry_run': dry_run,
    }

    try:
        # Analizza la struttura del database Mastercam
        schema = _analizza_schema_mc(mc)
        if not schema.get('tools_table'):
            mc.close()
            return {'errore': 'Tabella utensili non trovata nel database Mastercam'}

        _info(f"Schema rilevato: tools={schema['tools_table']}, "
              f"holders={schema.get('holders_table', 'N/A')}, "
              f"operations={schema.get('operations_table', 'N/A')}")

        if dry_run:
            stats['utensili'] = mc.execute(
                f"SELECT COUNT(*) FROM [{schema['tools_table']}]"
            ).fetchone()[0]
            if schema.get('holders_table'):
                stats['portautensili'] = mc.execute(
                    f"SELECT COUNT(*) FROM [{schema['holders_table']}]"
                ).fetchone()[0]
            if schema.get('operations_table'):
                stats['condizioni_taglio'] = mc.execute(
                    f"SELECT COUNT(*) FROM [{schema['operations_table']}]"
                ).fetchone()[0]
            mc.close()
            return stats

        master = sqlite3.connect(master_db_path)
        master.execute("PRAGMA foreign_keys = ON")
        master.execute("PRAGMA journal_mode = WAL")

        try:
            # 1. Portautensili
            if schema.get('holders_table'):
                h_stats = _importa_portautensili(mc, master, schema)
                stats['portautensili'] = h_stats['holders']
                stats['segmenti_holder'] = h_stats['segmenti']

            # 2. Utensili
            stats['utensili'] = _importa_utensili(mc, master, schema)

            # 3. Condizioni di taglio
            if schema.get('operations_table'):
                stats['condizioni_taglio'] = _importa_condizioni_taglio(
                    mc, master, schema)

            master.commit()
            _info(f"Importazione completata: {stats['utensili']} utensili, "
                  f"{stats['condizioni_taglio']} condizioni, "
                  f"{stats['portautensili']} portautensili")

        except Exception as e:
            master.rollback()
            stats['errore'] = str(e)
            import traceback
            traceback.print_exc()
        finally:
            master.close()

    except Exception as e:
        stats['errore'] = str(e)
        import traceback
        traceback.print_exc()
    finally:
        mc.close()

    return stats


# ── Analisi schema Mastercam ───────────────────────────────────────────────

def _analizza_schema_mc(mc):
    """Analizza il database Mastercam e individua tabelle e colonne chiave."""
    schema = {}

    # ── Tabella utensili ──
    tools_table = _find_table(mc, [
        'Tools', 'Tool', 'mc_tools', 'ToolDefinitions', 'ToolDefs',
        'TOOLS', 'tool_definitions', 'EndMills', 'MillTools',
    ])
    if tools_table:
        schema['tools_table'] = tools_table
        cols = _get_columns(mc, tools_table)
        schema['tools_cols'] = cols

        # Mappatura colonne con nomi alternativi
        schema['col_tool_id'] = _find_column(cols, [
            'ToolId', 'tool_id', 'ID', 'id', 'ToolID', 'pk', 'ToolNumber',
            'tool_number', 'ItemID',
        ])
        schema['col_name'] = _find_column(cols, [
            'Name', 'name', 'ToolName', 'tool_name', 'Description',
            'description', 'Comment', 'comment', 'Label',
        ])
        schema['col_comment'] = _find_column(cols, [
            'Comment', 'comment', 'Description', 'description',
            'Notes', 'notes', 'Remark', 'remark',
        ])
        schema['col_tool_type'] = _find_column(cols, [
            'Type', 'type', 'ToolType', 'tool_type', 'TypeId', 'type_id',
            'ToolTypeId', 'tool_type_id', 'Category', 'category',
        ])
        schema['col_diameter'] = _find_column(cols, [
            'Diameter', 'diameter', 'Dia', 'dia', 'D', 'd',
            'OutsideDiameter', 'outside_diameter', 'CuttingDiameter',
            'cutting_diameter', 'ToolDiameter', 'tool_diameter',
        ])
        schema['col_corner_radius'] = _find_column(cols, [
            'CornerRadius', 'corner_radius', 'Radius', 'radius',
            'TipRadius', 'tip_radius', 'CornerRad', 'corner_rad',
            'NoseRadius', 'nose_radius', 'CR',
        ])
        schema['col_flute_length'] = _find_column(cols, [
            'FluteLength', 'flute_length', 'CuttingLength', 'cutting_length',
            'CutLength', 'cut_length', 'LOC', 'loc',
            'LengthOfCut', 'length_of_cut', 'EffectiveLength',
        ])
        schema['col_overall_length'] = _find_column(cols, [
            'OverallLength', 'overall_length', 'TotalLength', 'total_length',
            'Length', 'length', 'OAL', 'oal', 'OL',
        ])
        schema['col_num_flutes'] = _find_column(cols, [
            'NumberOfFlutes', 'number_of_flutes', 'NumFlutes', 'num_flutes',
            'Flutes', 'flutes', 'FluteCount', 'flute_count', 'NFlutes',
            'TeethCount', 'teeth_count', 'NumberOfTeeth',
        ])
        schema['col_shank_diameter'] = _find_column(cols, [
            'ShankDiameter', 'shank_diameter', 'ShankDia', 'shank_dia',
            'ShoulderDiameter', 'shoulder_diameter',
        ])
        schema['col_point_angle'] = _find_column(cols, [
            'PointAngle', 'point_angle', 'TipAngle', 'tip_angle',
            'DrillAngle', 'drill_angle', 'Angle', 'angle',
        ])
        schema['col_helix_angle'] = _find_column(cols, [
            'HelixAngle', 'helix_angle', 'Helix', 'helix',
        ])
        schema['col_tool_material'] = _find_column(cols, [
            'Material', 'material', 'ToolMaterial', 'tool_material',
            'MaterialType', 'material_type', 'CuttingMaterial',
        ])
        schema['col_tool_number'] = _find_column(cols, [
            'ToolNumber', 'tool_number', 'Number', 'number',
            'ToolNo', 'tool_no', 'Tnumber', 'TNumber',
        ])
        schema['col_offset_number'] = _find_column(cols, [
            'OffsetNumber', 'offset_number', 'LengthOffset',
            'length_offset', 'DiameterOffset', 'diameter_offset',
            'HOffset', 'DOffset',
        ])
        schema['col_holder_id'] = _find_column(cols, [
            'HolderId', 'holder_id', 'HolderID', 'ToolHolderId',
            'tool_holder_id', 'HolderRef', 'holder_ref',
        ])
        schema['col_pitch'] = _find_column(cols, [
            'Pitch', 'pitch', 'ThreadPitch', 'thread_pitch',
        ])
        schema['col_taper_angle'] = _find_column(cols, [
            'TaperAngle', 'taper_angle', 'ConeAngle', 'cone_angle',
        ])
        schema['col_coolant'] = _find_column(cols, [
            'Coolant', 'coolant', 'CoolantType', 'coolant_type',
            'CoolantMode', 'coolant_mode',
        ])
        schema['col_spindle_direction'] = _find_column(cols, [
            'SpindleDirection', 'spindle_direction', 'SpinDirection',
            'spin_direction', 'Rotation', 'rotation',
        ])
        schema['col_feed'] = _find_column(cols, [
            'FeedRate', 'feed_rate', 'Feedrate', 'feedrate', 'Feed', 'feed',
            'DefaultFeedrate', 'default_feedrate',
        ])
        schema['col_speed'] = _find_column(cols, [
            'SpindleSpeed', 'spindle_speed', 'Speed', 'speed', 'RPM', 'rpm',
            'DefaultSpeed', 'default_speed', 'SpeedRPM',
        ])
        schema['col_plunge_feed'] = _find_column(cols, [
            'PlungeRate', 'plunge_rate', 'PlungeFeedrate', 'plunge_feedrate',
            'PlungeFeed', 'plunge_feed',
        ])
        schema['col_retract_feed'] = _find_column(cols, [
            'RetractRate', 'retract_rate', 'RetractFeedrate',
        ])
        schema['col_catalog'] = _find_column(cols, [
            'ProductId', 'product_id', 'CatalogNumber', 'catalog_number',
            'PartNumber', 'part_number', 'OrderCode', 'order_code',
            'ManufacturerToolCode',
        ])
        schema['col_manufacturer'] = _find_column(cols, [
            'Manufacturer', 'manufacturer', 'Vendor', 'vendor',
            'Brand', 'brand', 'MfgName',
        ])

    # ── Tabella portautensili ──
    holders_table = _find_table(mc, [
        'Holders', 'Holder', 'ToolHolders', 'mc_holders',
        'HolderDefinitions', 'HolderDefs', 'HOLDERS',
    ])
    if holders_table:
        schema['holders_table'] = holders_table
        cols = _get_columns(mc, holders_table)
        schema['holders_cols'] = cols

        schema['col_holder_pk'] = _find_column(cols, [
            'HolderId', 'holder_id', 'ID', 'id', 'HolderID', 'pk',
        ])
        schema['col_holder_name'] = _find_column(cols, [
            'Name', 'name', 'HolderName', 'holder_name',
            'Description', 'description', 'Label',
        ])
        schema['col_holder_comment'] = _find_column(cols, [
            'Comment', 'comment', 'Description', 'description',
            'Notes', 'notes',
        ])

    # ── Tabella segmenti holder ──
    holder_seg_table = _find_table(mc, [
        'HolderSegments', 'HolderSegment', 'HolderProfile',
        'HolderProfiles', 'HolderGeometry', 'HolderGeometries',
        'holder_segments', 'HolderPoints',
    ])
    if holder_seg_table:
        schema['holder_seg_table'] = holder_seg_table
        cols = _get_columns(mc, holder_seg_table)
        schema['holder_seg_cols'] = cols

        schema['col_seg_holder_id'] = _find_column(cols, [
            'HolderId', 'holder_id', 'HolderID', 'ParentId', 'parent_id',
        ])
        schema['col_seg_upper_dia'] = _find_column(cols, [
            'UpperDiameter', 'upper_diameter', 'TopDiameter', 'top_diameter',
            'DiameterUpper', 'OD', 'Diameter', 'diameter',
        ])
        schema['col_seg_lower_dia'] = _find_column(cols, [
            'LowerDiameter', 'lower_diameter', 'BottomDiameter',
            'bottom_diameter', 'DiameterLower', 'ID',
        ])
        schema['col_seg_length'] = _find_column(cols, [
            'Length', 'length', 'SegmentLength', 'segment_length',
            'Height', 'height',
        ])
        schema['col_seg_sequence'] = _find_column(cols, [
            'Sequence', 'sequence', 'SegmentNumber', 'segment_number',
            'Index', 'index', 'Order', 'order', 'Position', 'position',
        ])

    # ── Tabella operazioni / parametri di taglio ──
    ops_table = _find_table(mc, [
        'Operations', 'Operation', 'ToolOperations', 'CuttingConditions',
        'CuttingParameters', 'mc_operations', 'ToolpathParameters',
        'ToolParameters', 'Conditions', 'TechData',
    ])
    if ops_table:
        schema['operations_table'] = ops_table
        cols = _get_columns(mc, ops_table)
        schema['ops_cols'] = cols

        schema['col_op_tool_id'] = _find_column(cols, [
            'ToolId', 'tool_id', 'ToolID', 'ToolRef', 'tool_ref',
        ])
        schema['col_op_material'] = _find_column(cols, [
            'Material', 'material', 'WorkMaterial', 'work_material',
            'MaterialName', 'material_name', 'StockMaterial',
        ])
        schema['col_op_vc'] = _find_column(cols, [
            'CuttingSpeed', 'cutting_speed', 'Vc', 'vc',
            'SurfaceSpeed', 'surface_speed',
        ])
        schema['col_op_rpm'] = _find_column(cols, [
            'SpindleSpeed', 'spindle_speed', 'RPM', 'rpm', 'Speed', 'speed',
        ])
        schema['col_op_feed'] = _find_column(cols, [
            'FeedRate', 'feed_rate', 'Feedrate', 'feedrate', 'Feed', 'feed',
            'Vf', 'vf',
        ])
        schema['col_op_fz'] = _find_column(cols, [
            'FeedPerTooth', 'feed_per_tooth', 'Fz', 'fz',
            'FeedPerFlute', 'feed_per_flute', 'ChipLoad', 'chip_load',
        ])
        schema['col_op_ap'] = _find_column(cols, [
            'AxialDepth', 'axial_depth', 'Ap', 'ap', 'DOC', 'doc',
            'DepthOfCut', 'depth_of_cut', 'StepDown', 'step_down',
        ])
        schema['col_op_ae'] = _find_column(cols, [
            'RadialDepth', 'radial_depth', 'Ae', 'ae', 'WOC', 'woc',
            'WidthOfCut', 'width_of_cut', 'StepOver', 'step_over',
        ])
        schema['col_op_operation_type'] = _find_column(cols, [
            'OperationType', 'operation_type', 'OpType', 'op_type',
            'Application', 'application', 'Strategy', 'strategy',
        ])
        schema['col_op_coolant'] = _find_column(cols, [
            'Coolant', 'coolant', 'CoolantType', 'coolant_type',
        ])

    # ── Tabella materiali pezzo (opzionale) ──
    materials_table = _find_table(mc, [
        'Materials', 'Material', 'WorkMaterials', 'StockMaterials',
        'mc_materials', 'Stocks',
    ])
    if materials_table:
        schema['materials_table'] = materials_table

    return schema


# ── Import portautensili ───────────────────────────────────────────────────

def _importa_portautensili(mc, master, schema):
    holders_table = schema['holders_table']
    cols = schema.get('holders_cols', set())
    col_pk = schema.get('col_holder_pk', 'id')
    col_name = schema.get('col_holder_name', 'Name')
    col_comment = schema.get('col_holder_comment')

    sel_cols = [col_pk, col_name]
    if col_comment and col_comment != col_name:
        sel_cols.append(col_comment)

    query = f"SELECT * FROM [{holders_table}] ORDER BY [{col_pk}]"
    rows = mc.execute(query).fetchall()

    count_h = count_s = 0
    holder_id_map = {}   # mc_holder_id → master portautensile.id

    for r in rows:
        holder_name = r[col_name] if col_name else f"MC_Holder_{r[col_pk]}"
        holder_comment = r[col_comment] if col_comment and col_comment in r.keys() else ''
        tipo_attacco = _detect_tipo_attacco(holder_name)
        mc_id = str(r[col_pk]) if col_pk else str(count_h)

        codice = f"MC_{holder_name}" if holder_name else f"MC_holder_{mc_id}"

        master.execute("""INSERT OR IGNORE INTO portautensile
            (codice_interno, descrizione, tipo_attacco, cam_sorgente, id_originale_cam)
            VALUES (?,?,?,'Mastercam',?)""",
            (codice, holder_comment or holder_name, tipo_attacco, mc_id))

        row_id = master.execute(
            "SELECT id FROM portautensile WHERE codice_interno = ?", (codice,)
        ).fetchone()
        if row_id:
            holder_id_map[r[col_pk] if col_pk else count_h] = row_id[0]
        count_h += 1

    # Importa segmenti holder se la tabella esiste
    seg_table = schema.get('holder_seg_table')
    if seg_table:
        col_seg_hid = schema.get('col_seg_holder_id')
        col_seg_ud = schema.get('col_seg_upper_dia')
        col_seg_ld = schema.get('col_seg_lower_dia')
        col_seg_len = schema.get('col_seg_length')
        col_seg_seq = schema.get('col_seg_sequence')

        if col_seg_hid and col_seg_len:
            seg_rows = mc.execute(f"SELECT * FROM [{seg_table}] ORDER BY [{col_seg_hid}]").fetchall()
            for sr in seg_rows:
                hid_mc = sr[col_seg_hid]
                porta_id = holder_id_map.get(hid_mc)
                if not porta_id:
                    continue
                seq = _safe_int(sr[col_seg_seq], count_s + 1) if col_seg_seq else count_s + 1
                d_upper = _safe_float(sr[col_seg_ud]) if col_seg_ud else None
                d_lower = _safe_float(sr[col_seg_ld]) if col_seg_ld else d_upper
                seg_len = _safe_float(sr[col_seg_len]) if col_seg_len else None

                if seg_len:
                    master.execute("""INSERT OR IGNORE INTO portautensile_segmento
                        (id_portautensile, numero_segmento, diametro_inf_mm,
                         diametro_sup_mm, lunghezza_mm)
                        VALUES (?,?,?,?,?)""",
                        (porta_id, seq, d_lower, d_upper, seg_len))
                    count_s += 1
        else:
            _warn(f"Tabella segmenti {seg_table} trovata ma colonne chiave mancanti")

    return {'holders': count_h, 'segmenti': count_s}


# ── Import utensili ────────────────────────────────────────────────────────

def _importa_utensili(mc, master, schema):
    tools_table = schema['tools_table']
    col = schema   # alias per brevità

    # Pre-carica lookup master
    id_tipo_map = {}
    for row in master.execute("SELECT id, codice FROM tipo_utensile").fetchall():
        id_tipo_map[row[1]] = row[0]
    id_tipo_default = id_tipo_map.get('UNKNOWN', 1)

    id_mat_map = {}
    for row in master.execute("SELECT id, codice FROM materiale_utensile").fetchall():
        id_mat_map[row[1]] = row[0]
    id_mat_default = id_mat_map.get('HM', 1)

    porta_map = {}
    for row in master.execute(
        "SELECT id, id_originale_cam FROM portautensile WHERE cam_sorgente='Mastercam'"
    ).fetchall():
        porta_map[row[1]] = row[0]

    master_cols = {r[1] for r in master.execute("PRAGMA table_info('utensile')").fetchall()}

    rows = mc.execute(f"SELECT * FROM [{tools_table}]").fetchall()

    count = 0
    errori = 0
    for r in rows:
        try:
            # ID
            mc_id = r[col['col_tool_id']] if col.get('col_tool_id') else count
            mc_id_str = str(mc_id)

            # Nome / descrizione
            tool_name = r[col['col_name']] if col.get('col_name') else ''
            tool_comment = ''
            if col.get('col_comment') and col['col_comment'] != col.get('col_name'):
                try:
                    tool_comment = r[col['col_comment']] or ''
                except (IndexError, KeyError):
                    pass

            # Tipo
            tool_type_raw = r[col['col_tool_type']] if col.get('col_tool_type') else None
            tipo_str = _resolve_tool_type(tool_type_raw, tool_name)
            id_tipo = id_tipo_map.get(tipo_str, id_tipo_default)

            # Materiale utensile
            mat_raw = r[col['col_tool_material']] if col.get('col_tool_material') else None
            mat_str = _resolve_tool_material(mat_raw)
            id_mat = id_mat_map.get(mat_str, id_mat_default)

            # Geometria
            diametro = _safe_float(
                r[col['col_diameter']] if col.get('col_diameter') else None, 0.0)
            corner_radius = _safe_float(
                r[col['col_corner_radius']] if col.get('col_corner_radius') else None)
            flute_length = _safe_float(
                r[col['col_flute_length']] if col.get('col_flute_length') else None)
            overall_length = _safe_float(
                r[col['col_overall_length']] if col.get('col_overall_length') else None, 0.0)
            num_flutes = _safe_int(
                r[col['col_num_flutes']] if col.get('col_num_flutes') else None)
            shank_dia = _safe_float(
                r[col['col_shank_diameter']] if col.get('col_shank_diameter') else None)
            point_angle = _safe_float(
                r[col['col_point_angle']] if col.get('col_point_angle') else None)
            helix_angle = _safe_float(
                r[col['col_helix_angle']] if col.get('col_helix_angle') else None)
            pitch = _safe_float(
                r[col['col_pitch']] if col.get('col_pitch') else None)
            taper_angle = _safe_float(
                r[col['col_taper_angle']] if col.get('col_taper_angle') else None)

            # Parametri taglio default (se nella tabella Tools)
            feed_default = _safe_float(
                r[col['col_feed']] if col.get('col_feed') else None)
            speed_default = _safe_float(
                r[col['col_speed']] if col.get('col_speed') else None)

            # Calcolo Vc default da RPM + diametro
            vc_default = None
            if speed_default and diametro:
                vc_default = round(math.pi * diametro * speed_default / 1000, 2)

            # Calcolo Fz default da feed, RPM, flutes
            fz_default = None
            if feed_default and speed_default and num_flutes and num_flutes > 0:
                fz_default = round(feed_default / (speed_default * num_flutes), 4)

            # Raggio punta: per BALL = D/2, per BULL = corner_radius, per FLAT = 0
            raggio_punta = 0.0
            if tipo_str == 'BALL' and diametro:
                raggio_punta = round(diametro / 2.0, 4)
            elif tipo_str == 'BULL' and corner_radius:
                raggio_punta = corner_radius
            elif corner_radius:
                raggio_punta = corner_radius

            # Tool number / offset
            tool_number = _safe_int(
                r[col['col_tool_number']] if col.get('col_tool_number') else None)
            offset_number = _safe_int(
                r[col['col_offset_number']] if col.get('col_offset_number') else None)

            # Holder
            holder_id_mc = None
            if col.get('col_holder_id'):
                try:
                    holder_id_mc = r[col['col_holder_id']]
                except (IndexError, KeyError):
                    pass
            id_porta = porta_map.get(str(holder_id_mc)) if holder_id_mc else None

            # Catalogo / produttore
            catalogo = ''
            if col.get('col_catalog'):
                try:
                    catalogo = r[col['col_catalog']] or ''
                except (IndexError, KeyError):
                    pass

            # Coolant
            refrigerante = None
            if col.get('col_coolant'):
                try:
                    cool_val = r[col['col_coolant']]
                    if cool_val is not None:
                        cool_str = str(cool_val).lower()
                        if 'through' in cool_str:
                            refrigerante = 'Through'
                        elif 'flood' in cool_str:
                            refrigerante = 'Flood'
                        elif 'mist' in cool_str:
                            refrigerante = 'Mist'
                        elif 'air' in cool_str:
                            refrigerante = 'Air'
                        elif cool_str in ('off', '0', 'none', 'false'):
                            refrigerante = 'OFF'
                except (IndexError, KeyError):
                    pass

            # Spindle direction
            dir_rot = None
            if col.get('col_spindle_direction'):
                try:
                    sd = r[col['col_spindle_direction']]
                    if sd is not None:
                        sd_str = str(sd).lower()
                        if sd_str in ('0', 'cw', 'clockwise', 'right'):
                            dir_rot = 'CW'
                        elif sd_str in ('1', 'ccw', 'counterclockwise', 'left'):
                            dir_rot = 'CCW'
                except (IndexError, KeyError):
                    pass

            # Codice interno univoco
            name_part = tool_name or f"tool_{mc_id_str}"
            codice_interno = f"{name_part}_mc_{mc_id_str}"

            # Costruisci record
            utensile = {
                'codice_interno':       codice_interno,
                'alias':                tool_name or None,
                'descrizione':          tool_comment or tool_name or None,
                'codice_catalogo':      catalogo or None,
                'cam_sorgente':         'Mastercam',
                'id_originale_cam':     mc_id_str,
                'id_tipo':              id_tipo,
                'id_materiale':         id_mat,
                'id_portautensile':     id_porta,
                'diametro_mm':          diametro or 0,
                'raggio_punta_mm':      raggio_punta,
                'lunghezza_totale_mm':  overall_length or 0,
                'lunghezza_tagl_mm':    flute_length or 0,
                'num_taglienti':        num_flutes,
                'diam_stelo_mm':        shank_dia,
                'angolo_punta_gradi':   point_angle,
                'angolo_elica_gradi':   helix_angle,
                'angolo_conico_gradi':  taper_angle,
                'passo_mm':            pitch,
                'avanzamento_default':  feed_default,
                'rotazione_default':    speed_default,
                'vc_default':           vc_default,
                'fz_default':           fz_default,
                'dir_rotazione':        dir_rot,
                'refrigerante':         refrigerante,
                'mc_tool_number':       tool_number,
                'mc_offset_number':     offset_number,
                'mc_holder_id':         str(holder_id_mc) if holder_id_mc else None,
            }

            # Rimuovi valori None/vuoti
            utensile = {k: v for k, v in utensile.items() if v is not None and v != ''}
            # Filtra solo colonne esistenti nel master
            insert_data = {k: v for k, v in utensile.items() if k in master_cols}

            cols_str = ', '.join(insert_data.keys())
            ph = ', '.join(['?'] * len(insert_data))
            master.execute(
                f"INSERT INTO utensile ({cols_str}) VALUES ({ph})",
                list(insert_data.values()))
            count += 1

        except Exception as e:
            errori += 1
            if errori <= 5:
                _warn(f"Errore importazione utensile MC id={mc_id_str}: {e}")

    if errori > 0:
        _warn(f"Totale errori utensili: {errori}")

    return count


# ── Import condizioni di taglio ────────────────────────────────────────────

def _importa_condizioni_taglio(mc, master, schema):
    ops_table = schema['operations_table']
    col = schema

    # Mappa utensili master importati da Mastercam
    ut_map = {}
    for row in master.execute(
        "SELECT id, id_originale_cam FROM utensile WHERE cam_sorgente='Mastercam'"
    ).fetchall():
        ut_map[row[1]] = row[0]

    # Info geometria per calcoli derivati
    tool_geo = {}
    for row in master.execute(
        "SELECT id, diametro_mm, num_taglienti FROM utensile WHERE cam_sorgente='Mastercam'"
    ).fetchall():
        tool_geo[row[0]] = (row[1] or 0, row[2] or 0)

    col_op_tool = col.get('col_op_tool_id')
    if not col_op_tool:
        _warn("Colonna tool_id non trovata nella tabella operazioni, skip condizioni taglio")
        return 0

    rows = mc.execute(f"SELECT * FROM [{ops_table}]").fetchall()

    count = 0
    errori = 0

    for r in rows:
        try:
            mc_tool_id = str(r[col_op_tool])
            id_ut = ut_map.get(mc_tool_id)
            if not id_ut:
                continue

            diam, n_flutes = tool_geo.get(id_ut, (0, 0))

            # Materiale pezzo
            mat_name = 'Default'
            if col.get('col_op_material'):
                try:
                    mat_name = r[col['col_op_material']] or 'Default'
                except (IndexError, KeyError):
                    pass

            # Applicazione / tipo operazione
            applicazione = 'Default'
            if col.get('col_op_operation_type'):
                try:
                    applicazione = r[col['col_op_operation_type']] or 'Default'
                except (IndexError, KeyError):
                    pass

            # Parametri di taglio
            vc = _safe_float(r[col['col_op_vc']] if col.get('col_op_vc') else None)
            rpm = _safe_float(r[col['col_op_rpm']] if col.get('col_op_rpm') else None)
            feed = _safe_float(r[col['col_op_feed']] if col.get('col_op_feed') else None)
            fz = _safe_float(r[col['col_op_fz']] if col.get('col_op_fz') else None)
            ap = _safe_float(r[col['col_op_ap']] if col.get('col_op_ap') else None)
            ae = _safe_float(r[col['col_op_ae']] if col.get('col_op_ae') else None)

            # Skip righe senza dati utili
            if not any([vc, rpm, feed, fz, ap, ae]):
                continue

            # Calcoli derivati
            if not vc and rpm and diam:
                vc = round(math.pi * diam * rpm / 1000, 2)
            if not rpm and vc and diam and diam > 0:
                rpm = round(vc * 1000 / (math.pi * diam), 1)
            if not fz and feed and rpm and n_flutes and rpm > 0 and n_flutes > 0:
                fz = round(feed / (rpm * n_flutes), 4)
            if not feed and fz and rpm and n_flutes:
                feed = round(fz * rpm * n_flutes, 1)

            # Refrigerante
            refrig = None
            if col.get('col_op_coolant'):
                try:
                    cool_val = r[col['col_op_coolant']]
                    if cool_val is not None:
                        cool_str = str(cool_val).lower()
                        if 'through' in cool_str:
                            refrig = 'Through'
                        elif 'flood' in cool_str:
                            refrig = 'Flood'
                        elif 'mist' in cool_str:
                            refrig = 'Mist'
                        elif 'air' in cool_str:
                            refrig = 'Air'
                except (IndexError, KeyError):
                    pass

            # Trova ID materiale pezzo nel master (se esiste)
            id_mat_pezzo = None
            mat_row = master.execute(
                "SELECT id FROM materiale_pezzo WHERE nome = ?", (mat_name,)
            ).fetchone()
            if mat_row:
                id_mat_pezzo = mat_row[0]

            master.execute("""INSERT OR REPLACE INTO condizioni_taglio
                (id_utensile, id_materiale_pezzo, materiale_pezzo, applicazione,
                 cam_sorgente, vc_m_min, rotazione_rpm, fz_mm_z,
                 avanzamento_mm_min, ap_mm, ae_mm, refrigerante)
                VALUES (?,?,?,?,'Mastercam',?,?,?,?,?,?,?)""",
                (id_ut, id_mat_pezzo, mat_name, applicazione,
                 vc, rpm, fz, feed, ap, ae, refrig))
            count += 1

        except Exception as e:
            errori += 1
            if errori <= 5:
                _warn(f"Errore condizione taglio: {e}")

    if errori > 0:
        _warn(f"Totale errori condizioni taglio: {errori}")

    return count


# ═══════════════════════════════════════════════════════════════════════════
#   CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python mastercam_importer.py <file.tooldb> [master.db] [--dry-run]")
        sys.exit(1)

    mc_path = sys.argv[1]
    master_path = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'database', 'tool_master.db')
    dry = '--dry-run' in sys.argv

    result = importa_mastercam_tooldb(mc_path, master_path, dry_run=dry)

    print("\n── Risultato importazione Mastercam ──")
    for k, v in result.items():
        if k == 'warnings' and v:
            print(f"  {k}:")
            for w in v:
                print(f"    - {w}")
        else:
            print(f"  {k}: {v}")
