import json
import os
from flask import Flask, jsonify, send_from_directory, request
from uuid import uuid4
from datetime import datetime
from engine.profile import load_user_profile, update_user_profile, save_user_profile
from engine.planner import select_review_and_new_items
from engine.generator import generate_exercise_auto as generate_exercise
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

    def generate_exercise(self):
        # Use SRS-driven generator
        exercise = generate_exercise(
            profile_path="user_profile.json",
            recent_exercises=self.recent_exercises
        )
        if not exercise:
            return None
        exercise_id = str(uuid4())
        exercise["exercise_id"] = exercise_id
        self.current_session.append(exercise)
        return {
            'exercise_id': exercise_id,
            'prompt': exercise.get('prompt'),
            'exercise_type': exercise.get('exercise_type'),
            'expected_answer': exercise.get('expected_answer'),
            'filled_sentence': exercise.get('filled_sentence'),
            'glossary': exercise.get('glossary'),
            'grammar_focus': exercise.get('grammar_focus', []),
            'translated_sentence': exercise.get('translated_sentence', '')
        }

    def evaluate_exercise(self, exercise_id, user_answer):
        matching = next((ex for ex in self.current_session if ex['exercise_id'] == exercise_id), None)
        if not matching:
            return None
        # Fast match
        filled = build_filled_sentence(matching.get('prompt', ''), user_answer)
        expected = matching.get('filled_sentence', '')
        if filled.strip() == expected.strip():
            feedback = {
                'is_correct': True,
                'corrected_answer': expected,
                'error_analysis': [],
                'grammar_focus': matching.get('grammar_focus', []),
                'explanation_summary': 'Perfect match — no issues detected.'
            }
        else:
            feedback = evaluate_answer(
                prompt=matching.get('prompt', ''),
                user_answer=filled,
                expected_answer=expected,
                grammar_focus=matching.get('grammar_focus', []),
                target_language=self.profile.get('target_language', 'Korean')
            )
        # Normalize grammar IDs
        feedback['grammar_focus'] = [normalize_grammar_id(g) for g in feedback.get('grammar_focus', [])]
        matching.update({
            'is_correct': feedback['is_correct'],
            'error_analysis': feedback.get('error_analysis', []),
            'corrected_answer': feedback.get('corrected_answer', '')
        })
        # Log per-exercise to profile
        # Create a minimal history record for the prompt‐builder
        history_entry = {
            'exercise_type': matching.get('exercise_type'),
            'prompt':         matching.get('prompt'),
            # If you want to record exactly what they typed in,
            # use the raw `user_answer` (or the filled sentence)
            'user_answer':    user_answer,
            'expected_answer': matching.get('filled_sentence'),
            'is_correct':     feedback['is_correct']
        }
        update_user_profile(self.profile, [feedback])
        self.recent_exercises.append(history_entry)
        return feedback

manager = ExerciseSessionManager()
manager.start_new_session()

# -- UI Routes --
@app.route('/')
def serve_index():
    return send_from_directory('web', 'dashboard.html')

# -- Session Management --
@app.route('/api/session/start', methods=['POST'])
def api_start_session():
    manager.start_new_session()
    return jsonify({'message': 'New session started.'}), 200

@app.route('/api/exercise/new', methods=['POST'])
def api_new_exercise():
    exercise = manager.generate_exercise()
    if exercise:
        return jsonify({'exercise': exercise}), 200
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
