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

    # Get curriculum grammar points for the user's level
    user_level = profile.get("level", "beginner")
    curriculum_grammar = get_grammar_points_by_level(CURRICULUM, user_level)

    # Identify:
    weak = _get_weak_grammar_points(grammar_summary)
    underexposed = _get_underexposed_grammar_points(grammar_summary, threshold=3)
    missing_curriculum = [g for g in curriculum_grammar if g not in grammar_summary]

    # Priority:
    candidates = []

    if weak:
        candidates.extend(weak)

    if not weak and missing_curriculum:
        candidates.extend(missing_curriculum)

    if not weak and not missing_curriculum and underexposed:
        candidates.extend(underexposed)

    # Deduplicate and limit
    selected = []
    seen = set()

    for g in candidates:
        if g not in seen:
            selected.append(g.replace("_", " "))  # human-readable
            seen.add(g)
        if len(selected) >= max_targets:
            break

    return selected

def _get_weak_grammar_points(grammar_summary):
    return [g for g, info in grammar_summary.items() if info.get("status") == "weak"]

def _get_underexposed_grammar_points(grammar_summary, threshold=3):
    return [g for g, info in grammar_summary.items() if info.get("exposure", 0) < threshold]
