import json
import os
from datetime import datetime
from engine.llm_client import chat
from engine.planner import select_review_and_new_items
from engine.utils import normalize_grammar_id, sanitize_json_string
from engine.exercise_types import ExerciseTypeFactory, ExerciseConfig, generate_exercise_with_type
from engine.vocab_manager import get_vocab_manager  # NEW: Use centralized vocab manager
from engine.difficulty_system import (
    DifficultyProgressionManager, 
    ExerciseDifficulty,
    integrate_with_exercise_generator
)

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEBUG_DIR = os.path.join(BASE_DIR, 'debug')

# Load config for debug settings
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

DEBUG_MODE = CONFIG.get('debug_llm', True)  # Default to True for development

# Ensure debug directory exists
if DEBUG_MODE and not os.path.exists(DEBUG_DIR):
    os.makedirs(DEBUG_DIR)

# Get the global vocabulary manager instance
vocab_manager = get_vocab_manager()

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


def generate_exercise(user_profile: dict,
                      grammar_targets: list,
                      recent_exercises: list = None,
                      exercise_type: str = "fill_in_blank") -> dict:
    """
    Generate an exercise using the new modular system.
    Now uses centralized vocabulary manager instead of loading vocab data repeatedly.
    """
    print(f"🎯 Generating {exercise_type} exercise...")
    
    # Check if exercise type is supported by new system
    available_types = ExerciseTypeFactory.get_available_types()
    
    if exercise_type in available_types:
        # Use new modular system
        print(f"✅ Using new modular system for {exercise_type}")
        
        # Split vocab into categories by SRS level using vocabulary manager
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
        
        # Get new vocabulary suggestions from vocabulary manager
        known_words = set(vocab_summary.keys())
        user_level = user_profile.get('level', user_profile.get('user_level', 'beginner'))
        
        # Get level-appropriate new words using the vocabulary manager
        new_word_suggestions = vocab_manager.get_words_for_level(
            user_level=user_level,
            known_words=known_words,
            limit=15  # Get more candidates for better variety
        )
        
        # Also get some high-frequency words as backup
        frequent_new_words = vocab_manager.get_new_words_for_user(
            known_words=known_words,
            limit=10,
            prefer_frequent=True
        )
        
        # Combine and deduplicate new word suggestions
        available_new_words = list(dict.fromkeys(new_word_suggestions + frequent_new_words))
        vocab_new.extend(available_new_words)
        
        # Ensure we have some core vocabulary if user is new
        if not vocab_core and not vocab_familiar:
            # For brand new users, add some high-frequency words as familiar
            basic_words = vocab_manager.get_words_by_frequency(limit=8)
            # Only add words that aren't already in vocab_new
            for word in basic_words:
                if word not in vocab_new:
                    vocab_familiar.append(word)
            print(f"🔰 New user detected - added {len(vocab_familiar)} basic words to familiar vocabulary")
        
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
            vocab_new=vocab_new[:10],  # Limit to prevent overwhelming the LLM
            vocab_familiar=vocab_familiar[:15],
            vocab_core=vocab_core[:20],
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
        print(f'\033[38;2;100;149;237m  Vocab Categories:\033[0m Core({len(config.vocab_core)}), Familiar({len(config.vocab_familiar)}), New({len(config.vocab_new)})')
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
            "temperature": 0.4,
            "vocab_stats": {
                "core_count": len(config.vocab_core),
                "familiar_count": len(config.vocab_familiar), 
                "new_count": len(config.vocab_new)
            }
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
    exercise_type: str = "auto"  # Changed default to "auto"
) -> dict:
    """
    Enhanced version with difficulty progression.
    If exercise_type is "auto", selects based on difficulty progression.
    """
    profile = load_user_profile(profile_path)
    selections = select_review_and_new_items(profile_path=profile_path)
    
    # Debug the selection process
    print(f"📋 Grammar Selection Debug:")
    print(f"  Review grammar: {selections['review_grammar']}")
    print(f"  New grammar: {selections['new_grammar']}")
    
    grammar_targets = [normalize_grammar_id(g) for g in
                       selections['review_grammar'] + selections['new_grammar']]
    
    if not grammar_targets:
        print("⚠️  No grammar targets found, using default beginner grammar")
        grammar_targets = ['-이에요_예요', '-아요_어요']  # Default beginner grammar
    
    print(f"🎯 Final grammar targets: {grammar_targets}")
    
    # NEW: Integrate difficulty progression
    if exercise_type == "auto":
        selected_exercise_type, difficulty_level = integrate_with_exercise_generator(
            profile, grammar_targets
        )
        print(f"🎮 Difficulty system selected: {selected_exercise_type} ({difficulty_level.name})")
        exercise_type = selected_exercise_type
    else:
        # Manual override - user specified exercise type
        difficulty_level = ExerciseDifficulty.from_exercise_type(exercise_type)
        print(f"👤 User selected: {exercise_type} ({difficulty_level.name})")
    
    # Generate exercise with the selected type
    result = generate_exercise(profile, grammar_targets, recent_exercises, exercise_type)
    
    # Add difficulty information to the result
    if result and not result.get('error'):
        result['difficulty_level'] = difficulty_level.name
        result['difficulty_value'] = difficulty_level.value
    
    return result


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


# Backward compatibility function - now uses vocabulary manager
def load_vocab_data(path: str = None) -> dict:
    """
    Legacy function for backward compatibility.
    Now returns cached data from VocabularyManager instead of reading file.
    """
    return vocab_manager._vocab_data


# Example CLI usage
if __name__ == '__main__':
    print("🧪 Testing exercise generation...")
    
    # Print vocabulary manager stats
    print(f"\n📊 Vocabulary Manager Stats:")
    stats = vocab_manager.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
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

def get_difficulty_info(profile_path: str = None) -> dict:
    """
    Get difficulty progression information for the dashboard.
    """
    profile = load_user_profile(profile_path)
    manager = DifficultyProgressionManager()
    
    # Get all grammar points with difficulty info
    grammar_summary = profile.get('grammar_summary', {})
    difficulty_info = {}
    
    for grammar_id in grammar_summary.keys():
        summary = manager.get_difficulty_summary(profile, grammar_id)
        difficulty_info[grammar_id] = summary
    
    # Overall statistics
    total_grammar = len(grammar_summary)
    unlocked_difficulties = set()
    mastered_difficulties = set()
    
    for grammar_id, info in difficulty_info.items():
        for diff_name, mastery in info['mastery_by_difficulty'].items():
            if mastery['reps'] > 0:  # Has been attempted
                unlocked_difficulties.add(diff_name)
            if mastery['is_mastered']:
                mastered_difficulties.add(diff_name)
    
    return {
        'grammar_difficulty_details': difficulty_info,
        'overall_stats': {
            'total_grammar_points': total_grammar,
            'unlocked_difficulty_types': list(unlocked_difficulties),
            'mastered_difficulty_types': list(mastered_difficulties),
            'progression_percentage': len(mastered_difficulties) / 4 * 100 if unlocked_difficulties else 0
        }
    }