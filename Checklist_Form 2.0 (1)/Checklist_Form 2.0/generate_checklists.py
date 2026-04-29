import json
import re
import shutil
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
SCHEMA_DIR = ROOT / "data" / "checklists"
TEMPLATE_DIR = ROOT / "data" / "unfilled"
WORKBOOK_DIR = ROOT / "workbooks"

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

FIELD_TYPE_MAP = {
    "Text": "text",
    "Number": "number",
    "Timestamp": "datetime-local",
    "Hours": "number",
    "Date": "date",
    "OK/NOT OK": "select",
    "A/B/C": "select",
}

SELECT_OPTION_MAP = {
    "YES/NO": ["", "YES", "NO"],
    "ON/OFF": ["", "ON", "OFF"],
    "DONE / NOT DONE": ["", "DONE", "NOT DONE"],
    "DONE/NOT DONE": ["", "DONE", "NOT DONE"],
    "OK / NOT OK": ["", "OK", "NOT OK"],
    "OK/NOT OK": ["", "OK", "NOT OK"],
    "A/B/C": ["", "A", "B", "C"],
}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return value or "field"


def col_to_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    total = 0
    for letter in letters:
        total = total * 26 + (ord(letter.upper()) - 64)
    return total - 1


def read_workbook_sheets(path: Path) -> list[tuple[str, list[list[str]]]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                shared_strings.append("".join(node.text or "" for node in si.findall(".//a:t", NS)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("pr:Relationship", NS)}
        sheets = []

        for sheet in workbook.findall("a:sheets/a:sheet", NS):
            sheet_name = sheet.attrib["name"]
            target = rel_map[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            sheet_root = ET.fromstring(archive.read(f"xl/{target}"))
            rows = []
            max_col = 0

            for row in sheet_root.findall("a:sheetData/a:row", NS):
                values = {}
                for cell in row.findall("a:c", NS):
                    idx = col_to_index(cell.attrib.get("r", ""))
                    max_col = max(max_col, idx + 1)
                    value_type = cell.attrib.get("t")
                    value = ""
                    node = cell.find("a:v", NS)
                    inline = cell.find("a:is", NS)

                    if value_type == "s" and node is not None:
                        value = shared_strings[int(node.text)]
                    elif value_type == "inlineStr" and inline is not None:
                        value = "".join(part.text or "" for part in inline.findall(".//a:t", NS))
                    elif node is not None and node.text is not None:
                        value = node.text

                    values[idx] = value

                if values:
                    rows.append([values.get(i, "").strip() for i in range(max_col)])

            sheets.append((sheet_name, rows))

        return sheets


def last_non_empty(row: list[str]) -> str:
    for value in reversed(row):
        if value.strip():
            return value.strip()
    return ""


def extract_declared_answer_type(row: list[str]) -> str:
    for value in reversed(row):
        candidate = value.strip()
        if not candidate:
            continue
        if candidate in FIELD_TYPE_MAP or candidate in SELECT_OPTION_MAP:
            return candidate
    return ""


def row_text(row: list[str]) -> str:
    return " ".join(cell.strip() for cell in row if cell.strip())


def normalize_text(value: str) -> str:
    return " ".join(value.upper().split())


def count_checklist_items(payload: dict) -> int:
    return sum(len(section["items"]) for section in payload.get("sections", []))


def find_row_index(rows: list[list[str]], predicate) -> int | None:
    for index, row in enumerate(rows):
        if predicate(row):
            return index
    return None


def numeric_density(rows: list[list[str]], column_index: int, start_index: int, end_index: int | None = None) -> int:
    score = 0
    slice_rows = rows[start_index:end_index] if end_index is not None else rows[start_index:]
    for row in slice_rows:
        if column_index < len(row) and row[column_index].strip().isdigit():
            score += 1
    return score


def detect_category(path: Path) -> str:
    if path.parent == ROOT:
        return ROOT.name
    if path.parent == WORKBOOK_DIR:
        return WORKBOOK_DIR.name
    return path.parent.name


def make_field(field_id: str, label: str, answer_type: str, required: bool = True) -> dict:
    answer_type = answer_type.strip() or "Text"
    field = {
        "id": field_id,
        "label": label.strip(),
        "answer_type": answer_type,
        "input_type": FIELD_TYPE_MAP.get(answer_type, "text"),
        "required": required,
    }
    if answer_type in SELECT_OPTION_MAP:
        field["input_type"] = "select"
        field["options"] = SELECT_OPTION_MAP[answer_type]
    return field


def infer_metadata_type(label: str, explicit_type: str) -> str:
    if explicit_type in FIELD_TYPE_MAP or explicit_type in SELECT_OPTION_MAP:
        return explicit_type
    normalized = label.strip().upper()
    if normalized == "DATE":
        return "Date"
    return "Text"


def infer_response_type(specified_value: str, in_poka_yoke: bool = False) -> str:
    normalized = " ".join(specified_value.upper().split())
    if normalized in SELECT_OPTION_MAP:
        return normalized
    if normalized in FIELD_TYPE_MAP:
        return normalized
    for option_key in SELECT_OPTION_MAP:
        if option_key in normalized:
            return option_key
    for field_key in FIELD_TYPE_MAP:
        if field_key.upper() in normalized:
            return field_key
    if in_poka_yoke:
        return "OK / NOT OK"
    return "Text"


def is_probable_spec_value(value: str) -> bool:
    normalized = normalize_text(value)
    if not normalized:
        return False
    if normalized in SELECT_OPTION_MAP or normalized in FIELD_TYPE_MAP:
        return True
    if "OK/NOK" in normalized or "OK / NOK" in normalized:
        return True
    if "BAR" in normalized or "NM" in normalized:
        return True
    if normalized.startswith("LH SIDE") or normalized.startswith("RH SIDE"):
        return True
    if normalized.startswith("OK CONDITION") or normalized.startswith("NOT OK CONDITION"):
        return True
    return False


def is_setup_trailing_note(value: str) -> bool:
    normalized = normalize_text(value)
    return "CONDITION" in normalized and "REACTIVITY RULE" in normalized


def setup_trailing_note_key(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace("AT WHICH", "AT")
    normalized = normalized.replace("CHECK LIST IS BEING CARRIED OUT", "CHECK LIST IS BEING CARRIED OUT")
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    return normalized.strip()


def note_key(cells: list[str]) -> str:
    normalized_cells = [normalize_text(cell) for cell in cells if cell.strip()]
    return " | ".join(normalized_cells)


def format_note_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return text

    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    marker_patterns = [
        r"(?<!\n)[ \t]+([A-Ca-c]\)\s*)",
        r"(?<!\n)[ \t]+([1-9][\]\)]\s*)",
        r"(?<!\n)[ \t]+(\([0-9][a-zA-Z]\)\s*)",
    ]
    for pattern in marker_patterns:
        text = re.sub(pattern, r"\n\1", text)

    text = re.sub(r"\n([A-Ca-c]\)\s*)", r"\n\1", text)
    text = re.sub(r"\n([1-9][\]\)]\s*)", r"\n\1", text)
    text = re.sub(r"\n(\([0-9][a-zA-Z]\)\s*)", r"\n\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_standard_category_payload(path: Path, sheet_name: str, rows: list[list[str]]) -> tuple[dict, dict]:
    title = rows[0][0].strip()
    slug = slugify(path.stem)
    category_name = detect_category(path)

    metadata_fields = []
    section_start_index = len(rows)
    metadata_types = {"Text", "Number", "Timestamp", "Hours", "Date", *SELECT_OPTION_MAP.keys()}

    for index, row in enumerate(rows[1:], start=1):
        first = row[0].strip() if len(row) > 0 else ""
        label = row[3].strip() if len(row) > 3 else ""
        answer_type = extract_declared_answer_type(row)

        if first and "ACTIVITY" in first.upper():
            section_start_index = index
            break

        if label and answer_type in metadata_types:
            metadata_fields.append(make_field(slugify(label), label, answer_type))

    sections = []
    closing_fields = []
    notes = []
    seen_trailing_notes = set()
    current_section = None
    item_index = 1

    for row in rows[section_start_index:]:
        first = row[0].strip() if len(row) > 0 else ""
        item = row[1].strip() if len(row) > 1 else ""
        question = row[2].strip() if len(row) > 2 else ""
        answer_type = extract_declared_answer_type(row)
        normalized_first = normalize_text(first)

        is_section_header = bool(
            first
            and normalized_first.startswith(("OFFLINE ACTIVITY", "ONLINE ACTIVITY", "ON LINE ACTIVITY"))
            and not question
            and answer_type != "OK/NOT OK"
        )
        if is_section_header:
            current_section = {"title": " ".join(first.split()), "items": []}
            sections.append(current_section)
            continue

        if answer_type == "OK/NOT OK" and question:
            if current_section is None:
                current_section = {"title": "Checklist Items", "items": []}
                sections.append(current_section)
            current_section["items"].append(
                {
                    "id": f"activity_{item_index:02d}",
                    "serial_no": first,
                    "item": item,
                    "question": question,
                    "answer_type": answer_type,
                    "input_type": "select",
                    "options": ["", "OK", "NOT OK"],
                    "required": True,
                }
            )
            item_index += 1
            continue

        if answer_type in {"Timestamp", "Hours", "Text", "Number", "Date"} and question:
            closing_fields.append(make_field(slugify(question), question, answer_type))
            continue

        if first and is_setup_trailing_note(first):
            normalized_note = setup_trailing_note_key(first)
            if normalized_note not in seen_trailing_notes:
                notes.append([first])
                seen_trailing_notes.add(normalized_note)
            continue

        if question and current_section is not None and any(entry["id"].startswith("activity_") for entry in current_section["items"]):
            previous_item = current_section["items"][-1] if current_section["items"] else None
            if previous_item and previous_item.get("answer_type") == "OK/NOT OK":
                current_section["items"].append(
                    {
                        "id": f"activity_{item_index:02d}",
                        "serial_no": first,
                        "item": item,
                        "question": question,
                        "answer_type": "OK/NOT OK",
                        "input_type": "select",
                        "options": ["", "OK", "NOT OK"],
                        "required": True,
                    }
                )
                item_index += 1
                continue

        if any(cell.strip() for cell in row):
            notes.append([format_note_text(cell.strip()) for cell in row if cell.strip()])

    schema = {
        "slug": slug,
        "title": title,
        "category": category_name,
        "machine_type": sheet_name,
        "source_workbook": path.name,
        "source_sheet": sheet_name,
        "metadata_fields": metadata_fields,
        "sections": sections,
        "closing_fields": closing_fields,
        "notes": notes,
    }

    unfilled = {
        "checklist_type": slug,
        "category": category_name,
        "machine_type": sheet_name,
        "title": title,
        "source_workbook": path.name,
        "metadata": {field["id"]: "" for field in metadata_fields},
        "sections": [
            {
                "title": section["title"],
                "items": [
                    {
                        "id": entry["id"],
                        "serial_no": entry["serial_no"],
                        "item": entry["item"],
                        "question": entry["question"],
                        "answer_type": entry["answer_type"],
                        "value": "",
                    }
                    for entry in section["items"]
                ],
            }
            for section in sections
        ],
        "summary": {field["id"]: "" for field in closing_fields},
    }

    return schema, unfilled


def build_startup_shift_payload(path: Path, sheet_name: str, rows: list[list[str]]) -> tuple[dict, dict]:
    title = next((cell.strip() for row in rows[:3] for cell in row if "CHECKLIST" in cell.upper()), rows[0][0].strip())
    slug = slugify(path.stem)
    category_name = detect_category(path)
    notes = []
    metadata_fields = []
    sections = []
    closing_fields = []
    used_field_ids = set()
    seen_notes = set()

    machine_name = next(
        (
            cell.strip()
            for row in rows[:4]
            for cell in row
            if "NAME OF MACHINE" in cell.upper() or "NAME OF MACHINE/STATION" in cell.upper()
        ),
        "",
    )
    if machine_name:
        machine_note = [format_note_text(machine_name)]
        notes.append(machine_note)
        seen_notes.add(note_key(machine_note))

    def unique_id(label: str, prefix: str = "") -> str:
        base = slugify(f"{prefix}_{label}" if prefix else label)
        candidate = base
        counter = 2
        while candidate in used_field_ids:
            candidate = f"{base}_{counter}"
            counter += 1
        used_field_ids.add(candidate)
        return candidate

    first_section_index = len(rows)
    for index, row in enumerate(rows[:10]):
        normalized_row = normalize_text(row_text(row))
        if (
            ("SHIFT START UP CHECK LIST" in normalized_row or "END OF SHIFT CHECK" in normalized_row)
            and first_section_index == len(rows)
        ):
            first_section_index = index

        normalized_cells = [normalize_text(cell) for cell in row]
        for label in ("SHIFT", "CONDITION", "DATE"):
            if label not in normalized_cells:
                continue
            answer_type = infer_metadata_type(label.title(), last_non_empty(row))
            field_id = unique_id(label.title())
            metadata_fields.append(make_field(field_id, label.title(), answer_type))
            break

    if first_section_index == len(rows):
        first_section_index = 0

    header_row_index = find_row_index(
        rows[first_section_index:],
        lambda row: "S.NO." in normalize_text(row_text(row))
        or "SR.NO." in normalize_text(row_text(row))
        or "SR.NO" in normalize_text(row_text(row)),
    )
    if header_row_index is not None:
        header_row_index += first_section_index
    else:
        header_row_index = first_section_index

    header_row = rows[header_row_index]
    normalized_header = [normalize_text(cell) for cell in header_row]

    activity_col = next((i for i, cell in enumerate(normalized_header) if "ACTIVITY" in cell), None)
    specified_col = next((i for i, cell in enumerate(normalized_header) if "SPECIFIED VALUE" in cell), None)
    serial_candidates = [i for i, cell in enumerate(normalized_header) if "S.NO" in cell or "SR.NO" in cell]

    if activity_col is None:
        activity_col = 1 if len(header_row) > 1 else 0
    if specified_col is None:
        specified_col = len(header_row) - 1
    if serial_candidates:
        serial_col = max(serial_candidates, key=lambda idx: numeric_density(rows, idx, header_row_index + 1))
    else:
        serial_col = max(0, activity_col - 1)

    current_section = None
    current_section_title = ""
    item_index = 1

    def is_section_heading(text: str) -> bool:
        return text.startswith("SHIFT START UP CHECK LIST") or text.startswith("END OF SHIFT CHECK")

    def is_trailing_instruction(text: str) -> bool:
        return text.startswith("A)CONDITION FOR START") or text.startswith("A) CONDITION FOR START")

    def is_machine_note(cells: list[str]) -> bool:
        return any("NAME OF MACHINE" in normalize_text(cell) or "NAME OF MACHINE/STATION" in normalize_text(cell) for cell in cells)

    def extract_question_and_spec(row: list[str]) -> tuple[str, str]:
        non_empty = [(index, cell.strip()) for index, cell in enumerate(row) if cell.strip()]
        if not non_empty:
            return "", ""

        spec_parts = [(index, value) for index, value in non_empty if index > activity_col and is_probable_spec_value(value)]
        spec_indexes = {index for index, _ in spec_parts}
        question_parts = [value for index, value in non_empty if index >= activity_col and index not in spec_indexes]
        specified_value = " | ".join(value for _, value in spec_parts)
        question = " ".join(question_parts).strip()
        return question, specified_value

    for row in rows[first_section_index:]:
        non_empty_cells = [cell.strip() for cell in row if cell.strip()]
        if not non_empty_cells:
            continue

        first_visible = non_empty_cells[0]
        normalized_first = normalize_text(first_visible)
        normalized_row = normalize_text(row_text(row))
        serial_value = row[serial_col].strip() if serial_col < len(row) else ""
        question, specified_value = extract_question_and_spec(row)
        item_label = ""

        if normalized_first in {"SHIFT", "CONDITION", "DATE", "S.NO."}:
            continue
        if ("S.NO" in normalized_row or "SR.NO" in normalized_row) and "ACTIVITY" in normalized_row:
            continue

        if is_section_heading(normalized_row):
            current_section_title = first_visible.replace("  ", " ").strip()
            current_section = {"title": current_section_title, "items": []}
            sections.append(current_section)
            continue

        if "POKA YOKE" in normalized_row and "VALIDATION METHOD" in normalized_row:
            poka_title = f"{current_section_title} - Poka Yoke Validation" if current_section_title else "Poka Yoke Validation"
            current_section = {"title": poka_title, "items": []}
            sections.append(current_section)
            continue

        if is_machine_note(non_empty_cells):
            continue

        if is_trailing_instruction(normalized_first):
            trailing_note = [format_note_text(first_visible)]
            trailing_key = note_key(trailing_note)
            if trailing_key not in seen_notes:
                notes.append(trailing_note)
                seen_notes.add(trailing_key)

        if normalize_text(first_visible).startswith("NAME & SIGN"):
            label_prefix = current_section_title or "Checklist"
            label = f"{label_prefix} - {first_visible}"
            closing_fields.append(make_field(unique_id(label, "summary"), label, "Text"))
            continue

        sign_cell = next((cell.strip() for cell in row if normalize_text(cell).startswith("NAME & SIGN")), "")
        if sign_cell:
            label_prefix = current_section_title or "Checklist"
            label = f"{label_prefix} - {sign_cell}"
            closing_fields.append(make_field(unique_id(label, "summary"), label, "Text"))
            continue

        if serial_value.isdigit():
            if current_section is None:
                current_section_title = "Checklist Items"
                current_section = {"title": current_section_title, "items": []}
                sections.append(current_section)

            response_type = infer_response_type(specified_value, "POKA YOKE" in current_section["title"].upper())
            field = make_field(f"activity_{item_index:02d}", question, response_type)
            current_section["items"].append(
                {
                    "id": field["id"],
                    "serial_no": serial_value,
                    "item": item_label,
                    "question": question,
                    "specified_value": specified_value,
                    "answer_type": field["answer_type"],
                    "input_type": field["input_type"],
                    "options": field.get("options", []),
                    "required": True,
                }
            )
            item_index += 1
            continue

        if (
            not serial_value
            and current_section is not None
            and current_section["items"]
            and specified_value
            and not question
        ):
            previous = current_section["items"][-1]
            if previous.get("specified_value"):
                previous["specified_value"] = f"{previous['specified_value']} | {specified_value}"
            else:
                previous["specified_value"] = specified_value

            updated_type = infer_response_type(previous["specified_value"], "POKA YOKE" in current_section["title"].upper())
            previous["answer_type"] = updated_type
            previous["input_type"] = FIELD_TYPE_MAP.get(updated_type, "text")
            if updated_type in SELECT_OPTION_MAP:
                previous["input_type"] = "select"
                previous["options"] = SELECT_OPTION_MAP[updated_type]
            elif "options" in previous:
                previous["options"] = []
            continue

        if any(token in normalized_row for token in ["FORMAT NO.", "FORMAT & REV", "DATE"]) or "CONDITION FOR START" in normalized_row:
            current_note_key = note_key(non_empty_cells)
            if current_note_key not in seen_notes:
                notes.append([format_note_text(cell) for cell in non_empty_cells])
                seen_notes.add(current_note_key)
            continue

        current_note_key = note_key(non_empty_cells)
        if current_note_key not in seen_notes:
            notes.append([format_note_text(cell) for cell in non_empty_cells])
            seen_notes.add(current_note_key)

    schema = {
        "slug": slug,
        "title": title,
        "category": category_name,
        "machine_type": sheet_name,
        "source_workbook": path.name,
        "source_sheet": sheet_name,
        "metadata_fields": metadata_fields,
        "sections": sections,
        "closing_fields": closing_fields,
        "notes": notes,
    }

    unfilled = {
        "checklist_type": slug,
        "category": category_name,
        "machine_type": sheet_name,
        "title": title,
        "source_workbook": path.name,
        "metadata": {field["id"]: "" for field in metadata_fields},
        "sections": [
            {
                "title": section["title"],
                "items": [
                    {
                        "id": entry["id"],
                        "serial_no": entry["serial_no"],
                        "item": entry["item"],
                        "question": entry["question"],
                        "specified_value": entry.get("specified_value", ""),
                        "answer_type": entry["answer_type"],
                        "value": "",
                    }
                    for entry in section["items"]
                ],
            }
            for section in sections
        ],
        "summary": {field["id"]: "" for field in closing_fields},
    }

    return schema, unfilled


def parse_checklist(path: Path) -> tuple[dict, dict]:
    candidates = []
    for sheet_name, rows in read_workbook_sheets(path):
        if not rows:
            continue
        title = normalize_text(row_text(rows[0]))
        try:
            if "START UP & END OF SHIFT CHECKLIST" in title:
                schema, unfilled = build_startup_shift_payload(path, sheet_name, rows)
            else:
                schema, unfilled = build_standard_category_payload(path, sheet_name, rows)
        except Exception:
            continue

        score = count_checklist_items(schema) * 10 + len(schema.get("metadata_fields", [])) * 2
        if "OLD" in sheet_name.upper():
            score -= 5
        candidates.append((score, schema, unfilled))

    if not candidates:
        raise ValueError(f"Unable to parse workbook: {path}")

    _, schema, unfilled = max(candidates, key=lambda entry: entry[0])
    return schema, unfilled


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    WORKBOOK_DIR.mkdir(parents=True, exist_ok=True)

    manifest = []
    expected_schema_paths = set()
    expected_template_paths = set()

    def is_workbook_file(path: Path) -> bool:
        return path.suffix.lower() == ".xlsx" and not path.name.startswith("~$")

    workbook_paths = {path.resolve(): path for path in WORKBOOK_DIR.rglob("*.xlsx") if is_workbook_file(path)}
    for path in ROOT.glob("*.xlsx"):
        if not is_workbook_file(path):
            continue
        workbook_paths.setdefault(path.resolve(), path)

    for workbook_path in sorted(workbook_paths.values()):
        schema, unfilled = parse_checklist(workbook_path)
        category_slug = slugify(schema["category"])
        schema_subdir = SCHEMA_DIR / category_slug
        template_subdir = TEMPLATE_DIR / category_slug
        schema_subdir.mkdir(parents=True, exist_ok=True)
        template_subdir.mkdir(parents=True, exist_ok=True)

        schema_path = schema_subdir / f"{schema['slug']}.json"
        template_path = template_subdir / f"{schema['slug']}.json"
        manifest.append(
            {
                "slug": schema["slug"],
                "category": schema["category"],
                "title": schema["machine_type"],
                "machine_type": schema["machine_type"],
                "source_workbook": schema["source_workbook"],
                "form_path": f"/forms/{schema['slug']}",
                "schema_path": str(schema_path.relative_to(ROOT)).replace("\\", "/"),
                "template_path": str(template_path.relative_to(ROOT)).replace("\\", "/"),
            }
        )

        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        template_path.write_text(json.dumps(unfilled, indent=2), encoding="utf-8")
        expected_schema_paths.add(schema_path.resolve())
        expected_template_paths.add(template_path.resolve())

    (SCHEMA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for path in SCHEMA_DIR.rglob("*.json"):
        if path.name == "manifest.json":
            continue
        if path.resolve() not in expected_schema_paths:
            path.unlink(missing_ok=True)

    for path in TEMPLATE_DIR.rglob("*.json"):
        if path.resolve() not in expected_template_paths:
            path.unlink(missing_ok=True)

    for root_dir in (SCHEMA_DIR, TEMPLATE_DIR):
        for directory in sorted((path for path in root_dir.rglob("*") if path.is_dir()), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()

    print(f"Generated {len(manifest)} checklist schemas and unfilled templates.")


if __name__ == "__main__":
    main()
