import json
from datetime import datetime, timedelta
from pathlib import Path

# Constants for SM-2 algorithm
MIN_EASE_FACTOR = 1.3
INITIAL_EASE = 2.5
INITIAL_INTERVALS = [1, 6]  # days for first two repetitions

DEFAULT_PROFILE = {
  "user_id": "user_001",
  "user_level": "beginner",
  "level": "beginner",
  "native_language": "English",
  "target_language": "Korean",
  "instruction_language": "English",
  "task_language": "Korean",
  "session_tracking": {
    "last_session_date": "",
    "exercises_completed": 0,
    "correct_ratio_last_10": 0.0,
    "grammar_points_seen": []
  },
  "learning_preferences": {
    "preferred_formality": "polite",
    "max_new_words_per_session": 2,
    "preferred_exercise_types": ["fill_in_blank", "translation"],
    "prefers_korean_prompts": False,
    "allow_open_tasks": True,
    "reviews_per_session": 10,
    "new_grammar_per_session": 2,
    "new_vocab_per_session": 5
  },
  "grammar_summary": {},
  "vocab_summary": {}
}


def load_user_profile(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # first-run: write out a blank/default profile
        save_user_profile(DEFAULT_PROFILE, path)
        # make sure we return a fresh copy
        return DEFAULT_PROFILE.copy()


def save_user_profile(profile: dict, path: str = 'user_profile.json') -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def _apply_sm2(item: dict, correct: bool) -> None:
    """
    Applies a simplified SM-2 update to a single item (grammar or vocab).
    Mutates item in-place to update interval, ease_factor, srs_level, lapses, next_review_date.
    """
    today = datetime.now().date()

    # Initialize fields if missing
    item.setdefault('ease_factor', INITIAL_EASE)
    item.setdefault('interval', INITIAL_INTERVALS[0])
    item.setdefault('reps', 0)
    item.setdefault('lapses', 0)

    # Quality: high if correct, low if incorrect
    quality = 5 if correct else 2

    if quality < 3:
        # Failure: reset repetitions
        item['reps'] = 0
        item['interval'] = INITIAL_INTERVALS[0]
        item['lapses'] += 1
        # Decrease ease_factor, but not below MIN_EASE_FACTOR
        item['ease_factor'] = max(
            MIN_EASE_FACTOR,
            item['ease_factor'] - 0.2
        )
    else:
        # Success: increment repetitions
        item['reps'] += 1
        if item['reps'] == 1:
            item['interval'] = INITIAL_INTERVALS[0]
        elif item['reps'] == 2:
            item['interval'] = INITIAL_INTERVALS[1]
        else:
            # From third repetition on, use ease factor
            item['interval'] = round(item['interval'] * item['ease_factor'])
        # Adjust ease factor slightly
        delta = (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        item['ease_factor'] = max(MIN_EASE_FACTOR, item['ease_factor'] + delta)

    item['srs_level'] = item['reps']
    # Schedule next review
    item['next_review_date'] = (today + timedelta(days=item['interval'])).isoformat()


def update_user_profile(profile: dict, session_exercises: list) -> dict:
    """
    Updates the user profile based on session exercises.
    Each exercise in session_exercises must have keys:
      - 'grammar_focus': list of grammar IDs
      - 'vocab_used': list of vocabulary strings
      - 'is_correct': bool
    Returns updated profile.
    """
    # Ensure necessary sections exist
    profile.setdefault('grammar_summary', {})
    profile.setdefault('vocab_summary', {})

    for ex in session_exercises:
        correct = ex.get('is_correct', False)
        # Update grammar items
        for gid in ex.get('grammar_focus', []):
            gsum = profile['grammar_summary'].setdefault(
                gid, {'exposure': 0, 'reps': 0, 'ease_factor': INITIAL_EASE,
                      'interval': INITIAL_INTERVALS[0], 'lapses': 0}
            )
            # Increment exposure
            gsum['exposure'] = gsum.get('exposure', 0) + 1
            # Apply SM-2
            _apply_sm2(gsum, correct)

        # Update vocabulary items
        for word in ex.get('vocab_used', []):
            vsum = profile['vocab_summary'].setdefault(
                word, {'reps': 0, 'ease_factor': INITIAL_EASE,
                       'interval': INITIAL_INTERVALS[0], 'lapses': 0}
            )
            _apply_sm2(vsum, correct)

    return profile
