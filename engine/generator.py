import json
import os
from datetime import datetime
from engine.llm_client import chat
from engine.planner import select_review_and_new_items
from engine.utils import normalize_grammar_id, sanitize_json_string
from engine.exercise_types import ExerciseTypeFactory, ExerciseConfig, generate_exercise_with_type

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VOCAB_DATA_PATH = os.path.join(BASE_DIR, 'vocab_data.json')
DEBUG_DIR = os.path.join(BASE_DIR, 'debug')

# Load config for debug settings
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

DEBUG_MODE = CONFIG.get('debug_llm', True)  # Default to True for development

# Ensure debug directory exists
if DEBUG_MODE and not os.path.exists(DEBUG_DIR):
    os.makedirs(DEBUG_DIR)

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

def log_debug_info(stage: str, data: dict, exercise_type: str = "unknown", file_only: bool = False):
    """Log debug information to console and/or separate exercise file"""
    if not DEBUG_MODE:
        return
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create filename based on exercise type and timestamp
    debug_filename = f"{exercise_type}_{session_id}.log"
    debug_filepath = os.path.join(DEBUG_DIR, debug_filename)
    
    # Format the data for better readability
    formatted_data = data.copy()
    
    # Special formatting for prompts to preserve whitespace
    if 'prompt' in formatted_data:
        # Keep the prompt as-is for file logging, but format it nicely
        prompt_content = formatted_data['prompt']
        formatted_data['prompt_preview'] = prompt_content[:200] + "..." if len(prompt_content) > 200 else prompt_content
        # Store full prompt separately for better readability
        formatted_data['full_prompt'] = prompt_content
    
    log_entry = {
        'timestamp': timestamp,
        'stage': stage,
        'exercise_type': exercise_type,
        'data': formatted_data
    }
    
    # Always log to individual exercise file if debug mode is on
    try:
        # Check if this is the first entry for this exercise session
        file_exists = os.path.exists(debug_filepath)
        
        with open(debug_filepath, 'a', encoding='utf-8') as f:
            if not file_exists:
                f.write(f"Exercise Debug Log: {exercise_type}\n")
                f.write(f"Session: {session_id}\n")
                f.write(f"{'='*80}\n\n")
            
            f.write(f"[{timestamp}] {stage}\n")
            f.write(f"{'-'*40}\n")
            
            # Special handling for prompts
            if stage == "LLM_REQUEST" and 'full_prompt' in formatted_data:
                f.write(f"Exercise Type: {formatted_data.get('exercise_type', 'unknown')}\n")
                f.write(f"Grammar Targets: {formatted_data.get('grammar_targets', [])}\n")
                f.write(f"Temperature: {formatted_data.get('temperature', 'N/A')}\n\n")
                f.write("FULL PROMPT:\n")
                f.write(formatted_data['full_prompt'])
                f.write("\n\n")
            else:
                # Regular JSON formatting for other data
                f.write(json.dumps(formatted_data, indent=2, ensure_ascii=False))
                f.write("\n")
            
            f.write(f"{'-'*40}\n\n")
        
        if not file_only:
            print(f'\033[38;2;255;165;0m🔍 Debug logged to: {debug_filename}\033[0m')
            
    except Exception as e:
        print(f"⚠️  Failed to write debug log: {e}")
    
    # Console output (unless file_only)
    if not file_only:
        print(f'\033[38;2;255;165;0m🔍 Debug - {stage}:\033[0m')
        if stage == "LLM_REQUEST" and 'prompt_preview' in formatted_data:
            # Show just a preview for prompts in console
            print(f"    Exercise: {formatted_data.get('exercise_type', 'unknown')}")
            print(f"    Grammar: {formatted_data.get('grammar_targets', [])}")
            print(f"    Prompt preview: {formatted_data['prompt_preview']}")
        elif isinstance(formatted_data, dict) and len(str(formatted_data)) > 500:
            print(f"    Large data logged to: debug/{debug_filename}")
        else:
            # For small data, show in console
            display_data = {k: v for k, v in formatted_data.items() if k != 'full_prompt'}
            formatted = json.dumps(display_data, indent=2, ensure_ascii=False)
            print(f"    {formatted}")


def load_user_profile(path: str = None) -> dict:
    path = path or os.path.join(BASE_DIR, 'user_profile.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_curriculum(path: str = None) -> dict:
    path = path or os.path.join(BASE_DIR, 'curriculum', 'korean.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_vocab_data(path: str = None) -> dict:
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
                      recent_exercises: list = None,
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
        
        # Split vocab into categories by SRS level and add new words from vocab_data
        vocab_summary = user_profile.get('vocab_summary', {})
        vocab_new, vocab_familiar, vocab_core = [], [], []
        
        # Categorize known vocabulary by SRS level
        for w, info in vocab_summary.items():
            reps = info.get('reps', 0)
            if reps <= 1:
                vocab_new.append(w)
            elif reps <= 3:
                vocab_familiar.append(w)
            else:
                vocab_core.append(w)
        
        # Add new vocabulary from vocab_data (words not yet learned)
        known_words = set(vocab_summary.keys())
        available_new_words = []
        
        # Get words from vocab_data that aren't in user's vocabulary yet
        for word in VOCAB_DATA.keys():
            if word not in known_words:
                available_new_words.append(word)
        
        # Sort by frequency rank if available, take top candidates for new words
        available_new_words.sort(key=lambda w: VOCAB_DATA[w].get('frequency_rank', float('inf')))
        vocab_new.extend(available_new_words[:10])  # Add top 10 new words as candidates
        
        # Ensure we have some core vocabulary if user is new
        if not vocab_core and not vocab_familiar:
            # For brand new users, add some high-frequency words as familiar
            basic_words = available_new_words[:5]  # Take 5 most frequent words
            vocab_familiar.extend(basic_words)
            print(f"🔰 New user detected - added {len(basic_words)} basic words to familiar vocabulary")
        
        print(f"📚 Vocabulary counts: Core={len(vocab_core)}, Familiar={len(vocab_familiar)}, New={len(vocab_new)}")
        if recent_exercises:
            print(f"📜 Recent exercises count: {len(recent_exercises)}")
        else:
            print(f"📜 No recent exercises available")
        
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
        
        # Print formatted exercise data for debugging
        print(f'\n\033[38;2;170;239;94m🎯 Generated Exercise Data for {exercise_type}:\033[0m')
        print(f'\033[38;2;100;149;237m  Exercise Type:\033[0m {exercise_data["exercise_type"]}')
        print(f'\033[38;2;100;149;237m  Difficulty:\033[0m {exercise_data["difficulty"]}')
        print(f'\033[38;2;100;149;237m  Schema Fields:\033[0m {", ".join(exercise_data["schema"].keys())}')
        print(f'\033[38;2;100;149;237m  Prompt Length:\033[0m {len(exercise_data["prompt"])} characters')
        print(f'\033[38;2;100;149;237m  Grammar Targets:\033[0m {", ".join(config.grammar_targets)}')
        print(f'\033[38;2;100;149;237m  Vocab Categories:\033[0m Core({len(vocab_core)}), Familiar({len(vocab_familiar)}), New({len(vocab_new)})')
        print(f'\033[38;2;100;149;237m  Recent Exercises:\033[0m {len(recent_exercises or [])}')
        
        # Show prompt preview (first 200 chars)
        prompt_preview = exercise_data["prompt"][:200].replace('\n', ' ')
        print(f'\033[38;2;100;149;237m  Prompt Preview:\033[0m "{prompt_preview}..."')
        print('\033[38;2;156;100;90m' + '─' * 80 + '\033[0m')
        
        # Call LLM with generated prompt
        print(f'\033[38;2;255;206;84m📤 Sending prompt to LLM ({user_profile.get("target_language","Korean")} tutor)...\033[0m')
        
        # Log the complete prompt being sent
        log_debug_info("LLM_REQUEST", {
            "exercise_type": exercise_type,
            "grammar_targets": config.grammar_targets,
            "prompt": exercise_data['prompt'],
            "temperature": 0.4
        }, exercise_type=exercise_type, file_only=True)  # Large prompts go to file only
        
        response_text = chat([
            {"role": "system", "content": f"You are a helpful {user_profile.get('target_language','Korean')} tutor assistant."},
            {"role": "user", "content": exercise_data['prompt']}
        ], temperature=0.4)
        
        print(f'\033[38;2;144;238;144m📥 LLM Response received ({len(response_text)} chars)\033[0m')
        
        # Log the raw response
        log_debug_info("LLM_RESPONSE_RAW", {
            "exercise_type": exercise_type,
            "response_length": len(response_text),
            "response_text": response_text
        }, exercise_type=exercise_type)
        
        # Parse and validate response
        try:
            safe = sanitize_json_string(response_text)
            exercise = json.loads(safe)
            
            # Log the parsed exercise
            log_debug_info("EXERCISE_PARSED", {
                "exercise_type": exercise_type,
                "sanitized_json": safe,
                "parsed_exercise": exercise
            }, exercise_type=exercise_type)
            
            print(f'\033[38;2;144;238;144m✅ JSON parsing successful\033[0m')
            print(f'\033[38;2;100;149;237m  Exercise Type:\033[0m {exercise.get("exercise_type", "N/A")}')
            print(f'\033[38;2;100;149;237m  Prompt:\033[0m {exercise.get("prompt", "N/A")[:100]}...')
            print(f'\033[38;2;100;149;237m  Expected Answer:\033[0m {exercise.get("expected_answer", "N/A")}')
            
            # Validate using exercise-specific validator
            is_valid, errors = exercise_data['validator'](exercise)
            
            # Log validation results
            log_debug_info("VALIDATION_RESULT", {
                "exercise_type": exercise_type,
                "is_valid": is_valid,
                "errors": errors,
                "exercise_data": exercise
            }, exercise_type=exercise_type, file_only=True)  # Detailed validation goes to file
            
            if not is_valid:
                print(f"\033[38;2;255;99;71m⚠️  Exercise validation failed:\033[0m")
                for error in errors:
                    print(f"    \033[38;2;255;99;71m• {error}\033[0m")
                print(f"\033[38;2;255;206;84m📋 Generated exercise data:\033[0m")
                for key, value in exercise.items():
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:50] + "..."
                    print(f"    \033[38;2;100;149;237m{key}:\033[0m {value}")
                # Return anyway but log the issues
            else:
                print(f'\033[38;2;144;238;144m✅ Exercise validation passed\033[0m')
            
            print('\033[38;2;156;100;90m' + '─' * 80 + '\033[0m\n')
            return exercise
            
        except json.JSONDecodeError as e:
            # Log the JSON parsing error with full details
            log_debug_info("JSON_PARSE_ERROR", {
                "exercise_type": exercise_type,
                "error": str(e),
                "raw_response": response_text,
                "sanitized_response": sanitize_json_string(response_text)
            }, exercise_type=exercise_type)
            
            print(f"\033[38;2;255;99;71m❌ Failed to parse LLM response as JSON:\033[0m {e}")
            print(f"\033[38;2;255;206;84m📄 Raw response preview:\033[0m")
            preview = response_text[:300].replace('\n', '\\n')
            print(f"    \"{preview}...\"")
            print(f"\033[38;2;255;206;84m📋 Full details logged to debug/ directory\033[0m")
            print('\033[38;2;156;100;90m' + '─' * 80 + '\033[0m\n')
            
            # Return a fallback exercise
            return {
                "exercise_type": exercise_type,
                "prompt": "Error generating exercise - LLM response was not valid JSON",
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
    profile_path: str = None,
    recent_exercises: list = None,
    exercise_type: str = "fill_in_blank"
) -> dict:
    """
    Selects grammar and vocabulary via SRS planner, then delegates to generate_exercise.
    """
    profile = load_user_profile(profile_path)
    selections = select_review_and_new_items(profile_path=profile_path)
    
    # Debug the selection process
    print(f"📋 Grammar Selection Debug:")
    print(f"  Review grammar: {selections['review_grammar']}")
    print(f"  New grammar: {selections['new_grammar']}")
    print(f"  Review vocab: {len(selections['review_vocab'])} words")
    print(f"  New vocab: {len(selections['new_vocab'])} words")
    
    grammar_targets = [normalize_grammar_id(g) for g in
                       selections['review_grammar'] + selections['new_grammar']]
    
    if not grammar_targets:
        print("⚠️  No grammar targets found, using default beginner grammar")
        grammar_targets = ['-이에요_예요', '-아요_어요']  # Default beginner grammar
    
    print(f"🎯 Final grammar targets: {grammar_targets}")
    
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