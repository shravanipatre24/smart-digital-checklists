# excel_maps.py

# ---------------------------------------------------------
# 1. HARDCODED COLUMN MAPS (Unique for every checklist)
# ---------------------------------------------------------

# FMS starts at Column E
FMS_COL_MAP = {
    "1": "E", "2": "F", "3": "G", "4": "H", "5": "I", "6": "J"
}

# Fan Motor Assembly starts at Column F
FAN_MOTOR_COL_MAP = {
    "1": "F", "2": "G", "3": "H", "4": "I", "5": "J", "6": "K"
}

# Leak Testing starts at Column F
LEAK_TESTING_COL_MAP = {
    "1": "E", "2": "F", "3": "G", "4": "H", "5": "I", "6": "J"
}

# Module Assembly starts at Column F (Update if this one is different!)
MODULE_ASSY_COL_MAP = {
    "1": "F", "2": "G", "3": "H", "4": "I", "5": "J", "6": "K"
}


# ---------------------------------------------------------
# 2. INDIVIDUAL CHECKLIST ROW MAPS
# ---------------------------------------------------------

FMS_ROW_MAP = {
    "date": 2, "condition": 3, "model_change_from": 4, "model_to": 5, "shift": 6,
    "activity_01": 8, "activity_02": 9, "activity_03": 10,
    "activity_04": 12, "activity_05": 13, "activity_06": 14, 
    "activity_07": 15, "activity_08": 16, "activity_09": 17, "activity_10": 18,
    "activity_11": 20, "activity_12": 21, "activity_13": 22,
    "set_up_start_time": 23, "set_up_end_time": 24, "total_set_up_time": 25,
    "set_up_done_by": 26, "set_up_approved_by_cc": 27, "set_up_approved_time": 28
}

FAN_MOTOR_MAP = {
    "date": 2, "condition": 3, "model_change_from": 4, "model_to": 5, "shift": 6,
    "activity_01": 8, "activity_02": 9, "activity_03": 10, "activity_04": 11,
    "activity_05": 13, "activity_06": 14, "activity_07": 15, "activity_08": 16, 
    "activity_09": 17, "activity_10": 18, "activity_11": 19, "activity_12": 20,
    "activity_13": 22, "activity_14": 23, "activity_15": 24,
    "set_up_start_time": 25, "set_up_end_time": 26, "total_set_up_time": 27,
    "set_up_done_by": 28, "set_up_approved_by_cc": 29, "set_up_approved_time": 30
}

LEAK_TESTING_MAP = {
    "date": 2, "condition": 3, "model_change_from": 4, "model_to": 5, "shift": 6,
    "activity_01": 8, "activity_02": 9, "activity_03": 10,
    "activity_04": 12, "activity_05": 13, "activity_06": 14, "activity_07": 15,
    "activity_08": 16, "activity_09": 17, "activity_10": 18, "activity_11": 19, "activity_12": 20,
    "activity_13": 22, "activity_14": 23, "activity_15": 24,
    "set_up_start_time": 25, "set_up_end_time": 26, "total_set_up_time": 27,
    "set_up_done_by": 28, "set_up_approved_by_cc": 29, "set_up_approved_time": 30
}

MODULE_ASSY_MAP = {
    "date": 2, "condition": 3, "model_change_from": 4, "model_to": 5, "shift": 6,
    "activity_01": 8, "activity_02": 9, "activity_03": 10, "activity_04": 11,
    "activity_05": 13, "activity_06": 14, "activity_07": 15, "activity_08": 16, 
    "activity_09": 17, "activity_10": 18, "activity_11": 19, "activity_12": 20,
    "activity_13": 22, "activity_14": 23, "activity_15": 24,
    "set_up_start_time": 25, "set_up_end_time": 26, "total_set_up_time": 27,
    "set_up_done_by": 28, "set_up_approved_by_cc": 29, "set_up_approved_time": 30
}


# ---------------------------------------------------------
# 3. MASTER REGISTRY
# ---------------------------------------------------------

CHECKLIST_REGISTRY = {
    "fms": {
        "rows": FMS_ROW_MAP,
        "cols": FMS_COL_MAP
    },
    "fms_checklist": {
        "rows": FMS_ROW_MAP,
        "cols": FMS_COL_MAP
    },
    "fan_motor_assembly_balancing": {
        "rows": FAN_MOTOR_MAP,
        "cols": FAN_MOTOR_COL_MAP
    },
    "leak_testing": {
        "rows": LEAK_TESTING_MAP,
        "cols": LEAK_TESTING_COL_MAP
    },
    "module_assembly_testing": {
        "rows": MODULE_ASSY_MAP,
        "cols": MODULE_ASSY_COL_MAP
    }
}


# ---------------------------------------------------------
# 4. UNIVERSAL MAPPING FUNCTION
# ---------------------------------------------------------

def get_cell_address(checklist_slug, sequence_num, field_id):
    """Returns exact cell like 'F10' based on fully hardcoded maps."""
    config = CHECKLIST_REGISTRY.get(checklist_slug)
    if not config:
        return None

    # Get the specific column map for this sheet
    col_map = config.get("cols")
    row_map = config.get("rows")

    col = col_map.get(str(sequence_num))
    row = row_map.get(field_id)
    
    if col and row:
        return f"{col}{row}"
    return None