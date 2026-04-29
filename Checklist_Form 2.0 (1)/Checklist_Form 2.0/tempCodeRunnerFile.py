import json
import os
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request
import werkzeug


# Paths
BASE_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = BASE_DIR / "data" / "checklists"
TEMPLATE_DIR = BASE_DIR / "data" / "unfilled"
SUBMISSION_DIR = BASE_DIR / "data" / "submissions"
ACTIVE_DIR = BASE_DIR / "data" / "active"

app = Flask(__name__)

# Workbook Registry - Maps JSON slugs to Excel filenames
WORKBOOK_MAP = {
    "fms": "FMS.xlsx",
    "fms_checklist": "FMS.xlsx",
    "fan_motor_assembly_balancing": "FanMotorAB.xlsx",
    "leak_testing": "LeakTesting.xlsx",
    "module_assembly_testing": "ModuleAssembly.xlsx",
}

# Compatibility fix for older Werkzeug versions
if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"


# --- HELPER FUNCTIONS ---

def load_manifest() -> list[dict]:
    manifest_path = SCHEMA_DIR / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_by_slug() -> dict[str, dict]:
    return {entry["slug"]: entry for entry in load_manifest()}


def resolve_manifest_path(entry: dict, key: str, fallback_dir: Path) -> Path:
    relative_path = entry.get(key)
    if relative_path:
        return BASE_DIR / relative_path
    cat_slug = category_slug(entry.get("category", ""))
    return fallback_dir / cat_slug / f"{entry['slug']}.json"


def group_manifest_entries(manifest: list[dict]) -> list[dict]:
    grouped = {}
    for entry in manifest:
        category = entry.get("category", "General Checklist")
        grouped.setdefault(category, []).append(entry)
    return [{"name": name, "items": items} for name, items in grouped.items()]


def sanitize_filename_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip()).strip("_").lower()
    return cleaned or fallback


def category_slug(value: str) -> str:
    return sanitize_filename_part(value, "general_checklist")


def extract_submitter_name(payload: dict) -> str:
    summary = payload.get("summary", {})
    preferred_keys = ["set_up_done_by", "set_up_done_by_oe"]
    for key in preferred_keys:
        value = summary.get(key, "")
        if isinstance(value, str) and value.strip():
            return value
    return "unknown"


def extract_shift(payload: dict) -> str:
    metadata = payload.get("metadata", {})
    return metadata.get("shift", "no_shift")


def next_batch_details(checklist_dir: Path) -> tuple[int, int]:
    submission_count = sum(1 for path in checklist_dir.glob("*.json") if path.is_file())
    next_checklist_index = submission_count + 1
    batch_no = ((next_checklist_index - 1) // 6) + 1
    checklist_no = ((next_checklist_index - 1) % 6) + 1
    return batch_no, checklist_no


# --- PAGE ROUTES ---

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        # handle login logic
        data = request.form
        print(data)  # debug
        return "Login Successful"  # replace with redirect
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "POST":
        data = request.form
        print(data)
        return "Registered Successfully"
    
    return render_template("register.html")

@app.route("/admin")
def admin_page():
    return render_template("admin.html")

@app.route("/supervisor")
def supervisor_page():
    return render_template("supervisor.html")

@app.route("/operator")
def operator_page():
    return render_template("operator.html")

@app.route("/forms/<slug>")
def form_page(slug: str):
    entry = manifest_by_slug().get(slug)
    if not entry:
        return "Checklist not found", 404
    return render_template("form.html", checklist_slug=slug, checklist=entry)


# Optional: keep old dashboard route working, but point it to new supervisor UI
@app.route("/dashboard")
def supervisor_dashboard():
    return render_template("supervisor.html")


# --- CHECKLIST APIs ---

@app.route("/api/checklists")
def api_all_checklists():
    manifest = load_manifest()
    return jsonify(manifest)


@app.route("/api/checklists/<slug>")
def api_checklist(slug: str):
    entry = manifest_by_slug().get(slug)
    if not entry:
        return jsonify({"error": "Checklist not found"}), 404

    schema_path = resolve_manifest_path(entry, "schema_path", SCHEMA_DIR)
    if not schema_path.exists():
        return jsonify({"error": f"Schema not found at {schema_path}"}), 404

    return jsonify(load_json(schema_path))


@app.route("/api/templates/<slug>")
def api_template(slug: str):
    entry = manifest_by_slug().get(slug)
    if not entry:
        return jsonify({"error": "Template not found"}), 404

    template_path = resolve_manifest_path(entry, "template_path", TEMPLATE_DIR)
    if not template_path.exists():
        cat_slug = category_slug(entry.get("category", ""))
        template_path = TEMPLATE_DIR / cat_slug / f"{slug}.json"

    if not template_path.exists():
        return jsonify({"metadata": {}, "sections": [], "summary": {}})

    return jsonify(load_json(template_path))


@app.route("/api/checklists/<slug>/save", methods=["POST"])
def save_checklist(slug: str):
    entry = manifest_by_slug().get(slug)
    if not entry:
        return jsonify({"error": "Checklist not found"}), 404

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON payload"}), 400

    cat_slug = category_slug(entry.get("category", "General Checklist"))
    checklist_dir = SUBMISSION_DIR / cat_slug / slug
    checklist_dir.mkdir(parents=True, exist_ok=True)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)

    saved_at = datetime.now()
    shift_part = sanitize_filename_part(extract_shift(payload), "no_shift").upper()
    operator_part = sanitize_filename_part(extract_submitter_name(payload), "unknown")
    timestamp_part = saved_at.strftime("%Y%m%d_%H%M%S")
    batch_no, checklist_no = next_batch_details(checklist_dir)

    filename = f"B{batch_no:03d}_({checklist_no})_{slug}_{shift_part}_{operator_part}_{timestamp_part}.json"
    save_path = checklist_dir / filename
    save_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    try:
        from processor import process_submission_to_excel
        relative_filename = f"{cat_slug}/{slug}/{filename}"
        process_submission_to_excel(relative_filename)
        print(f"SUCCESS: Excel Active file created/updated for {filename}")
    except Exception as e:
        print(f"ERROR: Excel Processing Failed: {e}")

    return jsonify({
        "message": "Checklist saved successfully.",
        "saved_file": filename
    })


# --- SUPERVISOR APIs ---

@app.route("/api/supervisor/pending")
def get_pending_submissions():
    if not SUBMISSION_DIR.exists():
        return jsonify([])

    submissions = []
    for root, dirs, files in os.walk(SUBMISSION_DIR):
        for filename in files:
            if filename.endswith(".json"):
                parts = filename.split("_")
                if len(parts) >= 7:
                    current_slug = Path(root).name
                    submissions.append({
                        "filename": filename,
                        "batch": parts[0],
                        "sequence": parts[1].replace("(", "").replace(")", ""),
                        "slug": current_slug,
                        "shift": parts[3],
                        "operator": parts[4],
                        "time": f"{parts[5]} {parts[6].replace('.json', '')}"
                    })

    submissions.sort(key=lambda x: x["time"], reverse=True)
    return jsonify(submissions)


@app.route("/api/supervisor/preview/<batch_id>/<slug>")
def preview_excel(batch_id, slug):
    template_name = WORKBOOK_MAP.get(slug, "FMS.xlsx")
    active_file = ACTIVE_DIR / f"{batch_id}_{template_name}"

    print(f"DEBUG: Preview requested for {batch_id} | {slug}")
    print(f"DEBUG: Checking path: {active_file}")

    if not active_file.exists():
        print("DEBUG: Direct file not found, searching directory...")
        if ACTIVE_DIR.exists():
            for f in os.listdir(ACTIVE_DIR):
                if f.startswith(batch_id) and f.endswith(".xlsx"):
                    active_file = ACTIVE_DIR / f
                    print(f"DEBUG: Found match: {f}")
                    break

    if not active_file.exists():
        print("DEBUG: No file found after search.")
        return jsonify({"error": f"No Excel file found for {batch_id} in {ACTIVE_DIR}"}), 404

    try:
        import openpyxl
        wb = openpyxl.load_workbook(active_file, data_only=True)
        ws = wb.active

        preview_data = []
        for r_idx in range(1, 65):
            row_cells = []
            for c_idx in range(1, 15):
                val = ws.cell(row=r_idx, column=c_idx).value
                row_cells.append(str(val) if val is not None else "")
            preview_data.append({"index": r_idx, "cells": row_cells})

        return jsonify({"batch": batch_id, "rows": preview_data, "slug": slug})

    except Exception as e:
        print(f"DEBUG: Excel Error - {str(e)}")
        return jsonify({"error": f"Excel Error: {str(e)}"}), 500


@app.route("/api/checklists/approve", methods=["POST"])
def approve_checklist():
    data = request.json or {}
    batch = data.get("batch_id")
    seq = data.get("sequence")
    approver = data.get("approver")
    slug = data.get("slug")

    template_name = WORKBOOK_MAP.get(slug, "FMS.xlsx")

    try:
        from processor import add_supervisor_approval
        result = add_supervisor_approval(batch, seq, approver, slug, template_name)
        return jsonify({"message": result})
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)