import json
import os

UNITS_FILE = os.path.join(os.path.dirname(__file__), "units.json")
MATERIALS_DIR = os.path.join(os.path.dirname(__file__), "materials")


def load_units() -> dict:
    with open(UNITS_FILE) as f:
        return json.load(f)


def get_unit_list() -> list[dict]:
    """Return list of units with id and name."""
    units = load_units()
    return [{"id": k, "name": v["name"]} for k, v in units.items()]


def get_materials_for_unit(unit_id: str) -> list[dict]:
    """Return list of materials for a given unit."""
    units = load_units()
    if unit_id not in units:
        return []
    return units[unit_id]["materials"]


def get_unit_context(unit_id: str) -> dict:
    """Return the pedagogical context for a unit: guiding question, skill focus, artwork."""
    units = load_units()
    if unit_id not in units:
        return {}
    u = units[unit_id]
    return {
        "guiding_question": u.get("guiding_question", ""),
        "skill_focus": u.get("skill_focus", ""),
        "skill_lesson": u.get("skill_lesson", ""),
        "artwork": u.get("artwork", ""),
    }


def load_material_text(file_path: str) -> str:
    """Load the text content of a material file."""
    full_path = os.path.join(MATERIALS_DIR, file_path)
    if not os.path.exists(full_path):
        return ""
    with open(full_path) as f:
        content = f.read().strip()
    # Return empty if it's just a placeholder
    if content.startswith("[Paste"):
        return ""
    return content
