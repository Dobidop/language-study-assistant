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
    """Smarter update: Adjust grammar progression based on user performance."""

    # === Update Grammar Summary ===
    for g in exercise.get("grammar_focus", []):
        g_key = g.replace(" ", "_")
        summary = profile.setdefault("grammar_summary", {})
        entry = summary.setdefault(g_key, {
            "exposure": 0,
            "mistake_rate": 0.0,
            "status": "new",
            "recent_correct_streak": 0
        })
        
        # Ensure recent_correct_streak field exists for backward compatibility
        if "recent_correct_streak" not in entry:
            entry["recent_correct_streak"] = 0


        # Always increment exposure
        entry["exposure"] += 1

        # Determine if this mistake relates to this grammar
        grammar_mistake = any(g.replace("_", " ") in err.lower() for err in feedback.get("error_analysis", []))

        if feedback["is_correct"]:
            # Correct answer: improve!
            entry["recent_correct_streak"] += 1
            entry["mistake_rate"] = max(0.0, entry["mistake_rate"] - 0.05)
        else:
            # Mistake: only update if grammar mistake detected
            if grammar_mistake:
                entry["recent_correct_streak"] = 0
                # Critical mistakes can add more penalty later (simple +0.1 for now)
                entry["mistake_rate"] = min(1.0, entry["mistake_rate"] + 0.1)

        # Fast recovery rule
        if entry["recent_correct_streak"] >= 3:
            entry["status"] = "strong"
            entry["mistake_rate"] = min(entry["mistake_rate"], 0.05)  # Force near 0
        else:
            # Normal status updates
            if entry["mistake_rate"] > 0.5:
                entry["status"] = "very_weak"
            elif entry["mistake_rate"] > 0.25:
                entry["status"] = "weak"
            elif entry["mistake_rate"] < 0.1:
                entry["status"] = "strong"
            else:
                entry["status"] = "moderate"

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
