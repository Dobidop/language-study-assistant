import json
import os
from datetime import datetime

PROFILE_PATH = "user_profile.json"

def load_user_profile(path=PROFILE_PATH):
    if not os.path.exists(path):
        print("🆕 Creating new user profile...")
        return {
            "user_id": "user_001",
            "level": "beginner",
            "grammar_summary": {},
            "common_errors": {},
            "vocabulary": {
                "core": {},
                "familiar": {},
                "newly_introduced": {}
            },
            "session_tracking": {
                "last_session_date": None,
                "exercises_completed": 0,
                "correct_ratio_last_10": 0.0,
                "grammar_points_seen": []
            },
            "learning_preferences": {
                "max_new_words_per_session": 2,
                "preferred_exercise_types": ["fill_in_blank", "translation"],
                "prefers_korean_prompts": False,
                "allow_open_tasks": True
            }
        }

    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_user_profile(profile, path=PROFILE_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    print(f"✅ User profile saved to {path}")


def update_user_profile(profile, feedback, exercise):
    """Update grammar exposure, error stats, and vocabulary promotion after an exercise."""

    # Update grammar maturity exposure counts
    for g in exercise.get("grammar_focus", []):
        g_key = g.replace(" ", "_")
        summary = profile.setdefault("grammar_summary", {})
        entry = summary.setdefault(g_key, {"exposure": 0, "mistake_rate": 0.0, "status": "new"})
        entry["exposure"] += 1

        if not feedback["is_correct"]:
            # crude error tracking for now
            entry["mistake_rate"] = min(1.0, entry["mistake_rate"] + 0.1)
            if entry["mistake_rate"] > 0.25:
                entry["status"] = "weak"
        else:
            # slowly improve
            entry["mistake_rate"] = max(0.0, entry["mistake_rate"] - 0.05)
            if entry["mistake_rate"] < 0.1:
                entry["status"] = "strong"

    # Track errors
    for err in feedback.get("error_analysis", []):
        profile["common_errors"][err] = profile["common_errors"].get(err, 0) + 1

    # Vocabulary tracking
    for word in exercise.get("vocab_used", []):
        if word in profile["vocabulary"].get("familiar", {}):
            profile["vocabulary"]["core"][word] = {
                "confidence": 5,
                "last_seen": datetime.today().strftime('%Y-%m-%d')
            }
            del profile["vocabulary"]["familiar"][word]
        elif word in profile["vocabulary"].get("newly_introduced", {}):
            profile["vocabulary"]["familiar"][word] = {
                "confidence": 2,
                "last_seen": datetime.today().strftime('%Y-%m-%d')
            }
            del profile["vocabulary"]["newly_introduced"][word]
        elif word not in profile["vocabulary"]["core"]:
            profile["vocabulary"]["newly_introduced"][word] = {
                "introduced_by": f"session_{datetime.today().strftime('%Y_%m_%d')}"
            }

    # Save updated profile
    save_user_profile(profile)
