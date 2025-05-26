import json
import os
from flask import Flask, jsonify, send_from_directory, request
from uuid import uuid4
from datetime import datetime
from engine.profile import load_user_profile, update_user_profile, save_user_profile
from engine.planner import select_review_and_new_items
from engine.generator import generate_exercise_auto as generate_exercise, get_exercise_type_info, validate_exercise_type
from engine.evaluator import evaluate_answer, build_filled_sentence
from engine.logger import log_exercise_to_session
from engine.utils import normalize_grammar_id, summarize_common_errors
from engine.utils import categorize_session_errors, merge_error_categories
from engine.curriculum import load_curriculum

# Initialize Flask app to serve UI and API
app = Flask(__name__, static_folder="web", static_url_path="/")
# Align with engine.logger SESSION_DIR
SESSION_LOGS_DIR = "sessions"

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

    def start_new_session(self):
        self.current_session = []
        self.recent_exercises = []
        self.session_start_time = datetime.now()

    def end_current_session(self):
        if not self.current_session:
            return None
        summary = log_exercise_to_session({
            "session_id": f"session_{datetime.now().strftime('%Y_%m_%d_%H%M')}",
            "user_id": self.profile.get("user_id", "user_001"),
            "date": datetime.now().strftime('%Y-%m-%d'),
            "duration_minutes": (datetime.now() - self.session_start_time).seconds // 60,
            "exercises": self.current_session,
            "summary": None  # placeholder, will be filled below
        })
        # Actually retrieve summary dict using load_latest_session_summary
        summary = load_latest_session_summary()
        # Update profile with per-exercise records
        update_user_profile(self.profile, self.current_session)
        save_user_profile(self.profile, "user_profile.json")
        return summary

    def generate_exercise(self, exercise_type="fill_in_blank"):
        """Generate exercise with validation for exercise type"""
        
        # Validate exercise type
        if not validate_exercise_type(exercise_type):
            available_info = get_exercise_type_info()
            return {
                "error": f"Invalid exercise type: {exercise_type}",
                "available_types": available_info['available_types']  # No more legacy_types
            }
        
        try:
            exercise = generate_exercise(
                profile_path="user_profile.json",
                recent_exercises=self.recent_exercises,  # Pass the actual recent exercises
                exercise_type=exercise_type
            )

            if not exercise or exercise.get('error'):
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
                # Translation now uses the same structure as other exercises
                response.update({
                    'expected_answer': exercise.get('expected_answer'),
                    'filled_sentence': exercise.get('filled_sentence')
                })
            
            return response
            
        except Exception as e:
            print(f"❌ Error generating exercise: {e}")
            return {
                "error": f"Failed to generate exercise: {str(e)}"
            }

    def evaluate_exercise(self, exercise_id, user_answer):
        matching = next((ex for ex in self.current_session if ex['exercise_id'] == exercise_id), None)
        if not matching:
            return None
        
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
            expected = matching.get('correct_answer', '')
        elif exercise_type == 'sentence_building':
            # Compare ordered word list
            if isinstance(user_answer, str):
                user_answer = user_answer.split()  # Simple split for now
            comparison_text = ' '.join(user_answer) if isinstance(user_answer, list) else user_answer
            expected_order = matching.get('expected_answer', [])
            expected = ' '.join(expected_order) if isinstance(expected_order, list) else str(expected_order)
        elif exercise_type == 'translation':
            # Translation exercises now handled the same as other text-based exercises
            comparison_text = user_answer.strip()
            expected = str(expected).strip()
        else:
            # Default case for any other exercise types
            comparison_text = user_answer.strip()
            expected = str(expected).strip()

        # Quick exact match check
        if comparison_text.strip() == str(expected).strip():
            feedback = {
                'is_correct': True,
                'corrected_answer': expected,
                'error_analysis': [],
                'grammar_focus': matching.get('grammar_focus', []),
                'explanation_summary': 'Perfect match — no issues detected.'
            }
        else:
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
            
        print(f"📝 Added to recent exercises. Total: {len(self.recent_exercises)}")  # Debug
        
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

# -- Session Management --
@app.route('/api/session/start', methods=['POST'])
def api_start_session():
    manager.start_new_session()
    return jsonify({'message': 'New session started.'}), 200

@app.route('/api/exercise/new', methods=['POST'])
def api_new_exercise():
    data = request.get_json()
    exercise_type = data.get("exercise_type", "fill_in_blank")
    
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
    summary = manager.end_current_session()
    if summary:
        return jsonify({'summary': summary}), 200
    return jsonify({'error': 'No active session.'}), 400

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

# -- Error Aggregation --
@app.route('/api/errors/aggregate', methods=['POST'])
def api_aggregate_common_errors():
    profile = load_user_profile('user_profile.json')
    error_dict = profile.get('common_errors', {})
    if not error_dict:
        return jsonify({'message': 'No common errors to summarize.', 'categories': []}), 200
    summary = summarize_common_errors(error_dict)
    profile['common_error_categories'] = summary
    save_user_profile(profile, 'user_profile.json')
    return jsonify({'message': 'Common errors summarized.', 'categories': summary}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)