from collections import defaultdict
from engine.curriculum import load_curriculum, get_grammar_points_by_level

# Load curriculum once when module loads
CURRICULUM = load_curriculum("korean")

def select_focus_areas(profile, max_targets=2):
    """
    Select grammar points for the next session:
    - Prioritize weak points.
    - If weak points are handled, introduce missing curriculum grammar.
    - Limit new grammar introduction if unresolved weak points exist.
    """

    grammar_summary = profile.get("grammar_summary", {})
    seen_grammar = set(profile.get("session_tracking", {}).get("grammar_points_seen", []))

    # Get full grammar point entries now
    user_level = profile.get("level", "beginner")
    curriculum_points = get_grammar_points_by_level(CURRICULUM, user_level)

    # Map IDs to full entries for easier lookup
    id_to_entry = {gp["id"]: gp for gp in curriculum_points}

    # Identify based on IDs
    weak = _get_weak_grammar_points(grammar_summary)
    underexposed = _get_underexposed_grammar_points(grammar_summary, threshold=3)
    missing_curriculum = [gp["id"] for gp in curriculum_points if gp["id"] not in grammar_summary]

    candidates = []

    if weak:
        candidates.extend(weak)
    if not weak and missing_curriculum:
        candidates.extend(missing_curriculum)
    if not weak and not missing_curriculum and underexposed:
        candidates.extend(underexposed)

    selected = []
    seen = set()

    for g_id in candidates:
        if g_id not in seen and g_id in id_to_entry:
            selected.append({
                "id": g_id,
                "description": id_to_entry[g_id]["description"]
            })
            seen.add(g_id)
        if len(selected) >= max_targets:
            break

    return selected

def _get_weak_grammar_points(grammar_summary):
    return [g for g, info in grammar_summary.items() if info.get("status") == "weak"]

def _get_underexposed_grammar_points(grammar_summary, threshold=3):
    return [g for g, info in grammar_summary.items() if info.get("exposure", 0) < threshold]
