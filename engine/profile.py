import json
import os
from datetime import datetime
from engine.utils import normalize_grammar_id

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
    """Update the user profile with a gradual grammar mastery progression."""

    # === Update Grammar Summary ===
    for g in exercise.get("grammar_focus", []):
        g_key = normalize_grammar_id(g)
        summary = profile.setdefault("grammar_summary", {})
        entry = summary.setdefault(g_key, {
            "exposure": 0,
            "status": "new",
            "recent_correct_streak": 0
        })

        # --- New progression logic ---
        stages = ["new", "new_weak", "weak", "weak_medium", "medium", "medium_strong", "strong"]
        current_stage = entry.get("status", "new")
        if current_stage not in stages:
            current_stage = "new"

        idx = stages.index(current_stage)

        # Always increment exposure
        entry["exposure"] += 1

        # Correct vs Mistake handling
        if feedback["is_correct"]:
            entry["recent_correct_streak"] += 1
            # Promote after 2 consecutive corrects
            if entry["recent_correct_streak"] >= 2 and idx < len(stages) - 1:
                idx += 1
                entry["recent_correct_streak"] = 0  # Reset streak after promotion
        else:
            entry["recent_correct_streak"] = 0
            if idx > 1:  # Don't demote back to "new"
                idx -= 1

        entry["status"] = stages[idx]

    # === Update Common Errors ===
    for err in feedback.get("error_analysis", []):
        profile["common_errors"][err] = profile["common_errors"].get(err, 0) + 1

    # === Update Vocabulary ===
    for word in exercise.get("vocab_used", []):
        vocab = profile.get("vocabulary", {})
        if word in vocab.get("familiar", {}):
            vocab["core"][word] = {
                "confidence": 5,
                "last_seen": datetime.today().strftime('%Y-%m-%d')
            }
            del vocab["familiar"][word]
        elif word in vocab.get("newly_introduced", {}):
            vocab["familiar"][word] = {
                "confidence": 2,
                "last_seen": datetime.today().strftime('%Y-%m-%d')
            }
            del vocab["newly_introduced"][word]
        elif word not in vocab.get("core", {}):
            vocab["newly_introduced"][word] = {
                "introduced_by": f"session_{datetime.today().strftime('%Y_%m_%d')}"
            }

    # === Save Updated Profile ===
    save_user_profile(profile)

