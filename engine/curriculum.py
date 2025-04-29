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
    # 🚨 NEW: Match flat grammar_points structure
    all_points = curriculum.get("grammar_points", [])

    return [gp for gp in all_points if gp.get("level") == level]
