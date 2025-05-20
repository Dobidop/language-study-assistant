import json
import sys
from collections import defaultdict
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from engine.profile import save_user_profile  # reuse existing function


def normalize_grammar_id(raw_id: str) -> str:
    import re
    s = raw_id.lower().strip()
    s = re.sub(r"[^\w\s()\-]", "", s)
    s = re.sub(r"\s+", "_", s)
    s = s.replace("(", "_").replace(")", "")
    s = re.sub(r"__+", "_", s)
    return s.strip("_")

def merge_duplicate_grammar_keys(profile_path="user_profile.json"):
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    original = profile.get("grammar_summary", {})
    merged = defaultdict(lambda: {
        "exposure": 0,
        "mistake_rate": 0.0,
        "status": "new",
        "recent_correct_streak": 0
    })

    status_ranking = [
        "new", "new_weak", "weak", "weak_medium", "medium", "medium_strong", "strong"
    ]

    for raw_key, stats in original.items():
        norm_key = normalize_grammar_id(raw_key)
        entry = merged[norm_key]

        # Accumulate exposure and correct streak
        entry["exposure"] += stats.get("exposure", 0)
        entry["recent_correct_streak"] = max(entry["recent_correct_streak"], stats.get("recent_correct_streak", 0))

        # Combine status conservatively (use the weaker one)
        old_rank = status_ranking.index(entry["status"]) if entry["status"] in status_ranking else 0
        new_rank = status_ranking.index(stats.get("status", "new")) if stats.get("status") in status_ranking else 0
        entry["status"] = status_ranking[min(old_rank, new_rank)]

        # Average mistake rate (weighted)
        total_ex = entry["exposure"]
        prev_weight = total_ex - stats.get("exposure", 0)
        if total_ex > 0:
            entry["mistake_rate"] = round(
                (entry["mistake_rate"] * prev_weight + stats.get("mistake_rate", 0.0) * stats.get("exposure", 0)) / total_ex,
                3
            )

    # Replace with merged data
    profile["grammar_summary"] = dict(merged)

    # Save back
    save_user_profile(profile, path=profile_path)
    print(f"✅ Grammar keys normalized and merged. Saved to {profile_path}.")

# Run it
if __name__ == "__main__":
    merge_duplicate_grammar_keys()
