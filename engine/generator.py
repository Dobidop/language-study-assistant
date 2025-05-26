import json
import os
from engine.llm_client import chat
from engine.planner import select_review_and_new_items
from engine.utils import normalize_grammar_id, sanitize_json_string
from engine.exercise_types import ExerciseTypeFactory, ExerciseConfig, generate_exercise_with_type
from datetime import datetime

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VOCAB_DATA_PATH = os.path.join(BASE_DIR, 'vocab_data.json')

# Load vocabulary data once and cache it
with open(VOCAB_DATA_PATH, 'r', encoding='utf-8') as f:
    VOCAB_DATA = json.load(f)

# Ensure VOCAB_DATA is in dictionary format
if isinstance(VOCAB_DATA, list):
    print("⚠️  Converting vocabulary data from array to dictionary format...")
    vocab_dict = {}
    for entry in VOCAB_DATA:
        if isinstance(entry, dict) and 'vocab' in entry:
            vocab_word = entry['vocab']
            vocab_info = {k: v for k, v in entry.items() if k != 'vocab'}
            vocab_dict[vocab_word] = vocab_info
    VOCAB_DATA = vocab_dict
    print(f"✅ Converted {len(VOCAB_DATA)} vocabulary entries to dictionary format")

# Helper loaders

def load_user_profile(path: str = None) -> dict: # type: ignore
    path = path or os.path.join(BASE_DIR, 'user_profile.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_curriculum(path: str = None) -> dict: # type: ignore
    path = path or os.path.join(BASE_DIR, 'curriculum', 'korean.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_vocab_data(path: str = None) -> dict: # type: ignore
    """
    Load vocabulary data and ensure it's in dictionary format.
    """
    path = path or VOCAB_DATA_PATH
    with open(path, 'r', encoding='utf-8') as f:
        vocab_data = json.load(f)
    
    # Ensure dictionary format (with fallback for legacy array format)
    if isinstance(vocab_data, list):
        print("⚠️  Converting legacy array format to dictionary format...")
        vocab_dict = {}
        for entry in vocab_data:
            if isinstance(entry, dict) and 'vocab' in entry:
                vocab_word = entry['vocab']
                vocab_info = {k: v for k, v in entry.items() if k != 'vocab'}
                vocab_dict[vocab_word] = vocab_info
        return vocab_dict
    elif isinstance(vocab_data, dict):
        return vocab_data
    else:
        raise ValueError(f"Invalid vocab_data format: {type(vocab_data)}")


def generate_exercise(user_profile: dict,
                      grammar_targets: list,
                      recent_exercises: list = None, # type: ignore
                      exercise_type: str = "fill_in_blank") -> dict:
    """
    Generate an exercise using the new modular system.
    """
    print(f"🎯 Generating {exercise_type} exercise...")
    
    # Check if exercise type is supported by new system
    available_types = ExerciseTypeFactory.get_available_types()
    
    if exercise_type in available_types:
        # Use new modular system
        print(f"✅ Using new modular system for {exercise_type}")
        
        # Split vocab into categories by SRS level
        vocab_summary = user_profile.get('vocab_summary', {})
        vocab_new, vocab_familiar, vocab_core = [], [], []
        for w, info in vocab_summary.items():
            reps = info.get('reps', 0)
            if reps <= 1:
                vocab_new.append(w)
            elif reps <= 3:
                vocab_familiar.append(w)
            else:
                vocab_core.append(w)
        
        # Compute grammar maturity section
        grammar_summary = user_profile.get('grammar_summary', {})
        grammar_maturity_section = "\n".join(
            f"- {normalize_grammar_id(gid)}: level {info.get('srs_level',0)}, next review {info.get('next_review_date','N/A')}"
            for gid, info in grammar_summary.items()
            if gid in grammar_targets
        ) or "None"
        
        # Create exercise configuration
        config = ExerciseConfig(
            user_profile=user_profile,
            grammar_targets=grammar_targets,
            vocab_new=vocab_new,
            vocab_familiar=vocab_familiar,
            vocab_core=vocab_core,
            grammar_maturity_section=grammar_maturity_section,
            recent_exercises=recent_exercises
        )
        
        # Generate exercise using modular system
        exercise_data = generate_exercise_with_type(exercise_type, config)
        
        # Call LLM with generated prompt
        response_text = chat([
            {"role": "system", "content": f"You are a helpful {user_profile.get('target_language','Korean')} tutor assistant."},
            {"role": "user", "content": exercise_data['prompt']}
        ], temperature=0.4)
        
        # Parse and validate response
        try:
            safe = sanitize_json_string(response_text)
            exercise = json.loads(safe)
            
            # Validate using exercise-specific validator
            is_valid, errors = exercise_data['validator'](exercise)
            
            if not is_valid:
                print(f"⚠️  Exercise validation failed: {errors}")
                print(f"Generated exercise: {exercise}")
                # Return anyway but log the issues
            
            return exercise
            
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse LLM response as JSON: {e}")
            print(f"Raw response: {response_text[:200]}...")
            
            # Return a fallback exercise
            return {
                "exercise_type": exercise_type,
                "prompt": "Error generating exercise",
                "expected_answer": "",
                "filled_sentence": "",
                "glossary": {},
                "translated_sentence": "",
                "grammar_focus": grammar_targets,
                "error": "Failed to parse LLM response"
            }
    
    else:
        # Unknown exercise type
        print(f"❌ Unknown exercise type: {exercise_type}")
        print(f"Available types: {available_types}")
        raise ValueError(f"Unsupported exercise type: {exercise_type}")


def generate_exercise_auto(
    profile_path: str = None, # type: ignore
    recent_exercises: list = None, # type: ignore
    exercise_type: str = "fill_in_blank"
) -> dict:
    """
    Selects grammar and vocabulary via SRS planner, then delegates to generate_exercise.
    """
    profile = load_user_profile(profile_path)
    selections = select_review_and_new_items(profile_path=profile_path)
    grammar_targets = [normalize_grammar_id(g) for g in
                       selections['review_grammar'] + selections['new_grammar']]
    
    if not grammar_targets:
        print("⚠️  No grammar targets found, using default beginner grammar")
        grammar_targets = ['-이에요_예요', '-아요_어요']  # Default beginner grammar
    
    return generate_exercise(profile, grammar_targets, recent_exercises, exercise_type)


def get_exercise_type_info() -> dict:
    """
    Get information about available exercise types for the frontend.
    """
    return {
        'available_types': ExerciseTypeFactory.get_available_types(),
        'type_info': ExerciseTypeFactory.get_type_info(),
        'legacy_types': []  # No more legacy types - all migrated to modular system
    }


def validate_exercise_type(exercise_type: str) -> bool:
    """
    Check if an exercise type is valid/supported.
    """
    available = ExerciseTypeFactory.get_available_types()
    return exercise_type in available


# Example CLI usage
if __name__ == '__main__':
    print("🧪 Testing exercise generation...")
    
    # Test each exercise type
    test_types = ['fill_in_blank', 'multiple_choice', 'fill_multiple_blanks', 'error_correction', 'sentence_building', 'translation']
    
    for ex_type in test_types:
        try:
            print(f"\n--- Testing {ex_type} ---")
            ex = generate_exercise_auto(exercise_type=ex_type)
            print(f"✅ {ex_type}: {ex.get('prompt', 'No prompt')[:50]}...")
        except Exception as e:
            print(f"❌ {ex_type}: {e}")
    
    print(f"\n📋 Available exercise types: {get_exercise_type_info()}")