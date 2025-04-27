import json
import os

CURRICULUM_DIR = os.path.join(os.path.dirname(__file__), "..", "curriculum")

def load_curriculum(language="korean"):
    """
    Load the grammar curriculum for a specific language.
    Default is Korean.
    """
    filename = os.path.join(CURRICULUM_DIR, f"{language}.json")
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Curriculum file not found: {filename}")

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def get_grammar_points_by_level(curriculum, level="beginner"):
    """
    Get a list of grammar point IDs for a given level.
    """
    levels = curriculum.get("levels", {})
    level_data = levels.get(level)

    if not level_data:
        raise ValueError(f"Level '{level}' not found in curriculum.")

    return [gp["id"] for gp in level_data.get("grammar_points", [])]
