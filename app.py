import json
import os
from datetime import datetime
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory

from engine.curriculum import load_curriculum
from engine.evaluator import build_filled_sentence, evaluate_answer
from engine.generator import generate_exercise_auto as generate_exercise, get_exercise_type_info, validate_exercise_type
from engine.logger import log_exercise_to_session
from engine.planner import select_review_and_new_items
from engine.profile import load_user_profile, save_user_profile, update_user_profile
from engine.utils import normalize_answer_for_comparison,normalize_grammar_id
from engine.vocab_manager import get_vocab_manager
from engine.generator import get_difficulty_info
from engine.profile import get_mastery_progression_summary
from engine.difficulty_system import (
    DifficultyProgressionManager, 
    ExerciseDifficulty,
    integrate_with_exercise_generator,
    update_profile_with_difficulty_progress
)

# Initialize Flask app to serve UI and API
app = Flask(__name__, static_folder="web", static_url_path="/")
# Align with engine.logger SESSION_DIR
SESSION_LOGS_DIR = "sessions"

# Initialize vocabulary manager on app startup
print("🔧 Initializing vocabulary manager...")
vocab_manager = get_vocab_manager()
vocab_stats = vocab_manager.get_stats()
print(f"✅ Vocabulary manager ready: {vocab_stats.get('total_words', 0)} words loaded")
print(f"   Distribution: {vocab_stats.get('by_tags', {})}")

# Utility to load the most recent session summary
def load_latest_session_summary():
    try:
        files = [f for f in os.listdir(SESSION_LOGS_DIR) if f.endswith(".json")]
    except FileNotFoundError:
        return None
    if not files:
        return None
    latest_file = sorted(files)[-1]
    with open(os.path.join(SESSION_LOGS_DIR, latest_file), "r", encoding="utf-8") as f:
        session_log = json.load(f)
    return session_log.get("summary")

class ExerciseSessionManager:
    def __init__(self):
        self.current_session = []
        self.profile = load_user_profile("user_profile.json")
        self.recent_exercises = []
        self.session_start_time = datetime.now()
        self.session_active = False  # NEW: Track session state explicitly
        
        # Log vocabulary manager integration
        print(f"🎯 Session manager initialized with vocabulary manager")
        print(f"   User level: {self.profile.get('level', 'unknown')}")
        print(f"   Known vocabulary: {len(self.profile.get('vocab_summary', {}))}")

    def start_new_session(self):
        self.current_session = []
        self.recent_exercises = []
        self.session_start_time = datetime.now()
        self.session_active = True  # NEW: Set session as active
        print(f"🎬 New session started at {self.session_start_time}")

    def end_current_session(self):
        # Check if session is active instead of checking exercise count
        if not self.session_active:
            print("❌ No active session to end")
            return None
        
        print(f"🏁 Ending session with {len(self.current_session)} exercises")
        
        # Create session log even if no exercises were completed
        session_log = {
            "session_id": f"session_{datetime.now().strftime('%Y_%m_%d_%H%M')}",
            "user_id": self.profile.get("user_id", "user_001"),
            "date": datetime.now().strftime('%Y-%m-%d'),
            "duration_minutes": (datetime.now() - self.session_start_time).seconds // 60,
            "exercises": self.current_session,
            "summary": None  # Will be filled below
        }
        
        # Create summary based on session data
        if self.current_session:
            # Normal session with exercises
            # Calculate summary stats
            total_exercises = len(self.current_session)
            correct_count = sum(1 for ex in self.current_session if ex.get('is_correct', False))
            accuracy_rate = round((correct_count / total_exercises) * 100) if total_exercises > 0 else 0
            
            summary = {
                "total_exercises": total_exercises,
                "accuracy_rate": accuracy_rate,
                "duration_minutes": (datetime.now() - self.session_start_time).seconds // 60,
                "error_categories": [],  # Could be populated with error analysis
                "session_type": "normal"
            }
            
            # Add summary to session log and save it
            session_log["summary"] = summary
            log_exercise_to_session(session_log)
            
            # Update profile with exercise records
            update_user_profile(self.profile, self.current_session)
            save_user_profile(self.profile, "user_profile.json")
        else:
            # Empty session - create minimal summary
            summary = {
                "total_exercises": 0,
                "accuracy_rate": 0,
                "duration_minutes": (datetime.now() - self.session_start_time).seconds // 60,
                "error_categories": [],
                "session_type": "empty"
            }
            
            # Add summary to session log and save it
            session_log["summary"] = summary
            log_exercise_to_session(session_log)
        
        # Mark session as inactive
        self.session_active = False
        
        print(f"✅ Session completed and profile updated")
        return summary

    # Rest of the methods remain the same...
    def generate_exercise(self, exercise_type="fill_in_blank"):
        """Generate exercise with validation for exercise type"""
        
        # Check if session is active
        if not self.session_active:
            return {
                "error": "No active session. Please start a new session first."
            }
        
        # Validate exercise type
        if not validate_exercise_type(exercise_type):
            available_info = get_exercise_type_info()
            return {
                "error": f"Invalid exercise type: {exercise_type}",
                "available_types": available_info['available_types']
            }
        
        try:
            print(f"🎯 Generating {exercise_type} exercise (session exercise #{len(self.current_session) + 1})")
            
            exercise = generate_exercise(
                profile_path="user_profile.json",
                recent_exercises=self.recent_exercises,
                exercise_type=exercise_type
            )

            if not exercise or exercise.get('error'):
                print(f"❌ Exercise generation failed: {exercise.get('error', 'Unknown error')}")
                return None

            exercise_id = str(uuid4())
            exercise["exercise_id"] = exercise_id
            self.current_session.append(exercise)
            
            # Build response based on exercise type
            response = {
                'exercise_id': exercise_id,
                'exercise_type': exercise.get('exercise_type'),
                'prompt': exercise.get('prompt'),
                'glossary': exercise.get('glossary'),
                'grammar_focus': exercise.get('grammar_focus', []),
                'translated_sentence': exercise.get('translated_sentence', '')
            }
            
            # Add type-specific fields
            if exercise_type == 'multiple_choice':
                response.update({
                    'choices': exercise.get('choices', {}),
                    'explanation': exercise.get('explanation', '')
                })
            elif exercise_type == 'error_correction':
                response.update({
                    'sentences': exercise.get('sentences', {}),
                    'instruction': exercise.get('prompt', 'Select the correct sentence')
                })
            elif exercise_type == 'sentence_building':
                response.update({
                    'word_pieces': exercise.get('word_pieces', []),
                    'instruction': 'Arrange these words in the correct order'
                })
            elif exercise_type in ['fill_in_blank', 'fill_multiple_blanks', 'translation']:
                response.update({
                    'expected_answer': exercise.get('expected_answer'),
                    'filled_sentence': exercise.get('filled_sentence')
                })
            
            print(f"✅ Exercise generated successfully: {exercise.get('prompt', '')[:50]}...")
            return response
            
        except Exception as e:
            print(f"❌ Error generating exercise: {e}")
            return {
                "error": f"Failed to generate exercise: {str(e)}"
            }

    def evaluate_exercise(self, exercise_id, user_answer):
        matching = next((ex for ex in self.current_session if ex['exercise_id'] == exercise_id), None)
        if not matching:
            print(f"❌ Exercise not found: {exercise_id}")
            return None
        
        print(f"📝 Evaluating exercise: {matching.get('exercise_type')} - {matching.get('prompt', '')[:50]}...")
        
        exercise_type = matching.get('exercise_type')
        expected = matching.get('expected_answer', '')
        
        # Handle different exercise types
        if exercise_type == 'fill_in_blank':
            # Check if user provided the complete sentence or just the missing word
            if '___' in matching.get('prompt', ''):
                expected_complete = matching.get('filled_sentence', '')
                if user_answer.strip() == expected_complete.strip():
                    # User provided complete sentence - compare directly
                    comparison_text = user_answer.strip()
                    expected = expected_complete.strip()
                else:
                    # User provided just the missing word - build sentence and compare
                    filled = build_filled_sentence(matching.get('prompt', ''), user_answer).strip()
                    comparison_text = filled
                    expected = expected_complete.strip()
            else:
                # Fallback for prompts without blanks
                comparison_text = user_answer.strip()
                expected = str(expected).strip()
        elif exercise_type == 'fill_multiple_blanks':
            # Handle array of answers
            if isinstance(user_answer, str):
                # If user_answer is a string, try to parse it as comma-separated values
                user_answer = [ans.strip().replace('"', '').replace("'", '') for ans in user_answer.split(',')]
            
            # Check if user provided complete sentence or individual answers
            expected_complete = matching.get('filled_sentence', '')
            if isinstance(user_answer, list) and len(user_answer) == 1:
                # Single string provided, check if it's the complete sentence
                if user_answer[0].strip() == expected_complete.strip():
                    comparison_text = user_answer[0].strip()
                    expected = expected_complete.strip()
                else:
                    # Build sentence from the single answer (likely incorrect)
                    filled = build_filled_sentence(matching.get('prompt', ''), user_answer).strip()
                    comparison_text = filled
                    expected = expected_complete.strip()
            else:
                # Multiple answers provided - build the sentence
                filled = build_filled_sentence(matching.get('prompt', ''), user_answer).strip()
                comparison_text = filled
                expected = expected_complete.strip()
        elif exercise_type == 'multiple_choice':
            # For multiple choice, compare the choice letter (A, B, C, D)
            comparison_text = user_answer.strip().upper()
            expected = matching.get('correct_answer', '')
        elif exercise_type == 'error_correction':
            # Compare choice letter for error correction
            comparison_text = user_answer.strip().upper()
            expected = matching.get('correct_answer', '').strip().upper()
            
            # Additional validation - make sure the expected answer is a valid choice
            if expected not in ['A', 'B', 'C', 'D']:
                print(f"⚠️ Invalid correct_answer in exercise: {expected}")
                expected = 'A'  # Fallback, though this shouldn't happen with validation
            
            # For error correction, we can also provide the actual sentence text in feedback
            sentences = matching.get('sentences', {})
            expected_sentence = sentences.get(expected, '') if expected in sentences else ''
            
            # Store the sentence text as well for more detailed feedback
            matching['expected_sentence_text'] = expected_sentence
        elif exercise_type == 'sentence_building':
            # Compare ordered word list
            if isinstance(user_answer, str):
                user_answer = user_answer.split()  # Simple split for now
            comparison_text = ' '.join(user_answer) if isinstance(user_answer, list) else user_answer
            expected_order = matching.get('expected_answer', [])
            expected = ' '.join(expected_order) if isinstance(expected_order, list) else str(expected_order)
        elif exercise_type == 'translation':
            # Translation exercises handled the same as other text-based exercises
            comparison_text = user_answer.strip()
            expected = str(expected).strip()
        else:
            # Default case for any other exercise types
            comparison_text = user_answer.strip()
            expected = str(expected).strip()

        # ✅ NEW: Normalize both answers for comparison (ignore trailing punctuation)
        normalized_comparison = normalize_answer_for_comparison(comparison_text)
        normalized_expected = normalize_answer_for_comparison(expected)
        
        print(f"🔍 Comparison debug:")
        print(f"   Original user: '{comparison_text}'")
        print(f"   Normalized user: '{normalized_comparison}'")
        print(f"   Original expected: '{expected}'")
        print(f"   Normalized expected: '{normalized_expected}'")

        # Quick exact match check with normalized versions
        if normalized_comparison == normalized_expected:
            feedback = {
                'is_correct': True,
                'corrected_answer': expected,
                'error_analysis': [],
                'grammar_focus': matching.get('grammar_focus', []),
                'explanation_summary': 'Perfect match — no issues detected.'
            }
            print(f"✅ Correct answer! (normalized match)")
        else:
            print(f"❌ Incorrect - using LLM evaluation")
            print(f"   Difference: '{normalized_comparison}' ≠ '{normalized_expected}'")
            # Use LLM evaluation for incorrect answers
            feedback = evaluate_answer(
                prompt=matching.get('prompt', ''),
                user_answer=comparison_text,
                expected_answer=expected,
                grammar_focus=matching.get('grammar_focus', []),
                target_language=self.profile.get('target_language', 'Korean')
            )
        
        # Normalize grammar IDs
        feedback['grammar_focus'] = [normalize_grammar_id(g) for g in feedback.get('grammar_focus', [])]
        
        # Update exercise record
        matching.update({
            'is_correct': feedback['is_correct'],
            'error_analysis': feedback.get('error_analysis', []),
            'corrected_answer': feedback.get('corrected_answer', '')
        })
        
        # Create history entry
        history_entry = {
            'exercise_type': matching.get('exercise_type'),
            'prompt': matching.get('prompt'),
            'user_answer': user_answer,
            'expected_answer': expected,
            'is_correct': feedback['is_correct']
        }
        
        # Update profile and recent exercises
        update_user_profile(self.profile, [feedback])
        self.recent_exercises.append(history_entry)
        
        # Keep only last 10 exercises for prompt context
        if len(self.recent_exercises) > 10:
            self.recent_exercises = self.recent_exercises[-10:]
            
        print(f"📝 Exercise evaluated. Recent exercises: {len(self.recent_exercises)}")
        
        return feedback

manager = ExerciseSessionManager()
manager.start_new_session()

# -- UI Routes --
@app.route('/')
def serve_index():
    return send_from_directory('web', 'dashboard.html')

@app.route('/curriculum/<filename>')
def serve_curriculum(filename):
    """Serve curriculum files for frontend access"""
    return send_from_directory('curriculum', filename)

# -- Vocabulary API Endpoints --
@app.route('/api/vocab/stats', methods=['GET'])
def api_vocab_stats():
    """Get vocabulary database statistics"""
    stats = vocab_manager.get_stats()
    return jsonify(stats), 200

@app.route('/api/vocab/search', methods=['GET'])
def api_vocab_search():
    """Search vocabulary by query string"""
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 10))
    
    if not query:
        return jsonify({'error': 'Query parameter "q" is required'}), 400
    
    results = vocab_manager.search_words(query, limit)
    
    # Return detailed results with translations
    detailed_results = []
    for word in results:
        word_data = vocab_manager.get_word_data(word)
        if word_data:
            detailed_results.append({
                'word': word,
                'translation': word_data.get('translation', ''),
                'frequency_rank': word_data.get('frequency_rank'),
                'topik_level': word_data.get('topik_level'),
                'tags': word_data.get('tags')
            })
    
    return jsonify({'results': detailed_results}), 200

@app.route('/api/vocab/suggestions/<level>', methods=['GET'])
def api_vocab_suggestions(level):
    """Get vocabulary suggestions for a specific level"""
    limit = int(request.args.get('limit', 10))
    
    # Get user's known words from profile
    profile = load_user_profile("user_profile.json")
    known_words = set(profile.get('vocab_summary', {}).keys())
    
    suggestions = vocab_manager.get_words_for_level(
        user_level=level,
        known_words=known_words,
        limit=limit
    )
    
    # Return detailed suggestions
    detailed_suggestions = []
    for word in suggestions:
        word_data = vocab_manager.get_word_data(word)
        if word_data:
            detailed_suggestions.append({
                'word': word,
                'translation': word_data.get('translation', ''),
                'frequency_rank': word_data.get('frequency_rank'),
                'topik_level': word_data.get('topik_level'),
                'tags': word_data.get('tags')
            })
    
    return jsonify({'suggestions': detailed_suggestions}), 200

# -- Session Management --
@app.route('/api/session/start', methods=['POST'])
def api_start_session():
    manager.start_new_session()
    return jsonify({'message': 'New session started.'}), 200

@app.route('/api/exercise/new', methods=['POST'])
def api_new_exercise():
    """Enhanced exercise generation with difficulty progression support"""
    data = request.get_json()
    exercise_type = data.get("exercise_type", "auto")  # Default to auto
    
    # If auto is selected, let the difficulty system choose
    if exercise_type == "auto":
        print("🤖 Using automatic exercise type selection based on difficulty progression")
    else:
        print(f"👤 User manually selected: {exercise_type}")
    
    exercise = manager.generate_exercise(exercise_type=exercise_type)
    
    if exercise and not exercise.get('error'):
        return jsonify({'exercise': exercise}), 200
    elif exercise and exercise.get('error'):
        return jsonify({'error': exercise['error']}), 400
    else:
        return jsonify({'error': 'Could not generate exercise.'}), 500

@app.route('/api/exercise/answer', methods=['POST'])
def api_answer_exercise():
    data = request.get_json()
    exercise_id = data.get('exercise_id')
    user_answer = data.get('user_answer')
    
    if not exercise_id or user_answer is None:
        return jsonify({'error': 'Missing exercise_id or user_answer.'}), 400
    
    feedback = manager.evaluate_exercise(exercise_id, user_answer)
    if feedback:
        return jsonify({'feedback': feedback}), 200
    return jsonify({'error': 'Exercise ID not found.'}), 404

@app.route('/api/session/end', methods=['POST'])
def api_end_session():
    try:
        print("🔚 API: Attempting to end session...")
        summary = manager.end_current_session()
        print(f"🔚 API: End session returned: {summary}")
        
        if summary is not None:
            # Session ended successfully (even if it was empty)
            session_type = summary.get('session_type', 'normal')
            print(f"🔚 API: Session type: {session_type}")
            
            if session_type == 'empty':
                return jsonify({
                    'summary': summary,
                    'message': 'Session ended (no exercises completed)'
                }), 200
            else:
                return jsonify({'summary': summary}), 200
        else:
            # No active session
            print("🔚 API: No active session detected")
            return jsonify({'error': 'No active session to end.'}), 400
            
    except Exception as e:
        print(f"❌ API: Error ending session: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to end session: {str(e)}'}), 500

# -- Exercise Type Information --
@app.route('/api/exercise/types', methods=['GET'])
def api_get_exercise_types():
    """Get information about available exercise types"""
    return jsonify(get_exercise_type_info()), 200

# -- Configuration & Metadata --
@app.route('/api/config/update', methods=['POST'])
def update_config():
    data = request.get_json()
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    provider = data.get('provider', config.get('default_provider'))
    config['default_provider'] = provider
    if provider == 'openai':
        config['openai_model'] = data.get('model', config.get('openai_model'))
    elif provider == 'local':
        config['local_port'] = int(data.get('port', config.get('local_port')))
        config['local_model'] = data.get('model', config.get('local_model'))
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    return jsonify({'message': 'Configuration updated successfully.'}), 200

# -- Session Summary & History --
@app.route('/api/session/summary', methods=['GET'])
def get_session_summary():
    summary = load_latest_session_summary()
    if not summary:
        return jsonify({'error': 'No session summary available.'}), 404
    return jsonify({'summary': summary}), 200

@app.route('/api/session/history', methods=['GET'])
def get_session_history():
    try:
        files = [f for f in os.listdir(SESSION_LOGS_DIR) if f.endswith('.json')]
    except FileNotFoundError:
        return jsonify({'sessions': []}), 200
    sessions = []
    for file in sorted(files, reverse=True):
        with open(os.path.join(SESSION_LOGS_DIR, file), 'r', encoding='utf-8') as f:
            session_log = json.load(f)
            summary = session_log.get('summary')
            if summary:
                sessions.append({
                    'session_id': session_log.get('session_id', file),
                    'date': session_log.get('date', 'Unknown Date'),
                    'total_exercises': summary.get('total_exercises', 0),
                    'accuracy_rate': summary.get('accuracy_rate', 0.0)
                })
    return jsonify({'sessions': sessions}), 200

# -- Vocabulary Management Endpoints --
@app.route('/api/vocab/reload', methods=['POST'])
def api_vocab_reload():
    """Reload vocabulary data (useful for development)"""
    try:
        vocab_manager.reload()
        stats = vocab_manager.get_stats()
        return jsonify({
            'message': 'Vocabulary reloaded successfully',
            'stats': stats
        }), 200
    except Exception as e:
        return jsonify({'error': f'Failed to reload vocabulary: {str(e)}'}), 500

@app.route('/api/vocab/word/<word>', methods=['GET'])
def api_get_word_details(word):
    """Get detailed information about a specific word"""
    word_data = vocab_manager.get_word_data(word)
    if not word_data:
        return jsonify({'error': 'Word not found'}), 404
    
    # Add the word itself to the response
    response = {'word': word, **word_data}
    return jsonify(response), 200

# -- Development/Debug Endpoints --
@app.route('/api/debug/vocab-manager', methods=['GET'])
def api_debug_vocab_manager():
    """Debug endpoint to inspect vocabulary manager state"""
    stats = vocab_manager.get_stats()
    sample_words = vocab_manager.get_all_words()[:10]  # First 10 words as sample
    
    return jsonify({
        'stats': stats,
        'sample_words': sample_words,
        'total_loaded': len(vocab_manager.get_all_words()),
        'manager_initialized': vocab_manager._initialized
    }), 200



@app.route('/api/difficulty/info', methods=['GET'])
def api_get_difficulty_info():
    """Get difficulty progression information for all grammar points"""
    try:
        from engine.difficulty_system import DifficultyProgressionManager
        
        profile = load_user_profile("user_profile.json")
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
        
        return jsonify({
            'grammar_difficulty_details': difficulty_info,
            'overall_stats': {
                'total_grammar_points': total_grammar,
                'unlocked_difficulty_types': list(unlocked_difficulties),
                'mastered_difficulty_types': list(mastered_difficulties),
                'progression_percentage': len(mastered_difficulties) / 4 * 100 if unlocked_difficulties else 0
            }
        }), 200
    except Exception as e:
        return jsonify({'error': f'Failed to get difficulty info: {str(e)}'}), 500

@app.route('/api/difficulty/progression', methods=['GET'])
def api_get_progression_summary():
    """Get comprehensive progression summary including difficulty mastery"""
    try:
        from engine.difficulty_system import DifficultyProgressionManager
        
        profile = load_user_profile("user_profile.json")
        manager = DifficultyProgressionManager()
        grammar_summary = profile.get('grammar_summary', {})
        
        # Traditional mastery stats
        traditional_stats = {
            "new": 0, "learning": 0, "reviewing": 0, "mastered": 0
        }
        
        # Count traditional mastery levels
        for gid, data in grammar_summary.items():
            reps = data.get('reps', 0)
            exposures = data.get('exposure', 0)
            consecutive_correct = data.get('consecutive_correct', 0)
            recent_accuracy = data.get('recent_accuracy', 0.0)
            total_attempts = data.get('total_attempts', 0)
            
            if exposures == 0:
                traditional_stats["new"] += 1
            elif reps < 4 or consecutive_correct < 4 or total_attempts < 8:
                traditional_stats["learning"] += 1
            elif reps < 6 or recent_accuracy < 0.8 or consecutive_correct < 5:
                traditional_stats["reviewing"] += 1
            else:
                traditional_stats["mastered"] += 1
        
        # Difficulty progression stats
        difficulty_progression = {}
        difficulty_totals = {
            'RECOGNITION': {'mastered': 0, 'attempted': 0},
            'GUIDED_PRODUCTION': {'mastered': 0, 'attempted': 0},
            'STRUCTURED_PRODUCTION': {'mastered': 0, 'attempted': 0},
            'FREE_PRODUCTION': {'mastered': 0, 'attempted': 0}
        }
        
        for grammar_id in grammar_summary.keys():
            progress_summary = manager.get_difficulty_summary(profile, grammar_id)
            difficulty_progression[grammar_id] = progress_summary
            
            # Aggregate stats
            for diff_name, mastery_info in progress_summary['mastery_by_difficulty'].items():
                if mastery_info['reps'] > 0:
                    difficulty_totals[diff_name]['attempted'] += 1
                    if mastery_info['is_mastered']:
                        difficulty_totals[diff_name]['mastered'] += 1
        
        # Calculate progression percentages
        progression_percentages = {}
        for diff_name, stats in difficulty_totals.items():
            if stats['attempted'] > 0:
                progression_percentages[diff_name] = (stats['mastered'] / stats['attempted']) * 100
            else:
                progression_percentages[diff_name] = 0
        
        # Get recommendations
        recommendations = []
        for grammar_id, progress in difficulty_progression.items():
            current_max = progress['current_max_difficulty']
            can_unlock = progress['can_unlock_next']
            
            if can_unlock:
                recommendations.append({
                    'grammar_id': grammar_id,
                    'current_level': current_max,
                    'recommendation': 'Ready to unlock next difficulty level',
                    'priority': 'high'
                })
            else:
                # Find the lowest unmastered difficulty
                for diff_name, mastery in progress['mastery_by_difficulty'].items():
                    if mastery['reps'] > 0 and not mastery['is_mastered']:
                        recommendations.append({
                            'grammar_id': grammar_id,
                            'current_level': diff_name,
                            'recommendation': f'Continue practicing {diff_name.lower()}',
                            'priority': 'medium'
                        })
                        break
        
        return jsonify({
            'traditional_mastery': traditional_stats,
            'difficulty_mastery_totals': difficulty_totals,
            'difficulty_progression_percentages': progression_percentages,
            'grammar_difficulty_details': difficulty_progression,
            'next_recommended_difficulty': recommendations,
            'overall_stats': {
                'total_grammar_points': len(grammar_summary),
                'progression_percentage': sum(progression_percentages.values()) / 4 if progression_percentages else 0
            }
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to get progression summary: {str(e)}'}), 500

@app.route('/api/exercise/recommended', methods=['GET'])
def api_get_recommended_exercise():
    """Get the recommended exercise type based on difficulty progression"""
    try:
        from engine.planner import select_review_and_new_items
        from engine.utils import normalize_grammar_id
        
        profile = load_user_profile("user_profile.json")
        selections = select_review_and_new_items(profile_path="user_profile.json")
        
        grammar_targets = [normalize_grammar_id(g) for g in
                          selections['review_grammar'] + selections['new_grammar']]
        
        if not grammar_targets:
            grammar_targets = ['-이에요_예요', '-아요_어요']
        
        exercise_type, difficulty_level = integrate_with_exercise_generator(
            profile, grammar_targets
        )
        
        return jsonify({
            'recommended_exercise_type': exercise_type,
            'difficulty_level': difficulty_level.name,
            'difficulty_value': difficulty_level.value,
            'target_grammar': grammar_targets,
            'explanation': f'Recommended {exercise_type} at {difficulty_level.name} level'
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get recommendation: {str(e)}'}), 500












if __name__ == '__main__':
    print("🚀 Starting Korean Study Assistant with centralized vocabulary management...")
    print(f"📚 Vocabulary Manager Status:")
    print(f"   - Total words: {vocab_stats.get('total_words', 0)}")
    print(f"   - TOPIK levels: {list(vocab_stats.get('by_topik_level', {}).keys())}")
    print(f"   - Tags: {list(vocab_stats.get('by_tags', {}).keys())}")
    print(f"   - Frequency data: {vocab_stats.get('frequency_coverage', 'N/A')}")
    print()
    
    app.run(host='0.0.0.0', port=8000, debug=True)
