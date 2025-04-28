from flask import Flask, jsonify, send_from_directory, request
import json
import os
from uuid import uuid4
from datetime import datetime
from engine.profile import load_user_profile, update_user_profile
from engine.planner import select_focus_areas
from engine.generator import generate_exercise
from engine.evaluator import evaluate_answer, build_filled_sentence


app = Flask(__name__, static_folder=".", static_url_path="")

SESSION_LOGS_DIR = "sessions"

class ExerciseSessionManager:
    def __init__(self):
        self.current_session = []
        self.grammar_targets = []
        self.profile = load_user_profile("user_profile.json")
        self.recent_exercises = []
        self.session_start_time = datetime.now()
        

    def start_new_session(self):
        self.current_session = []
        self.grammar_targets = select_focus_areas(self.profile)
        self.recent_exercises = []
        self.session_start_time = datetime.now()
        
    def end_current_session(self):
        from engine.logger import log_exercise_to_session

        if not self.current_session:
            return None

        session_duration = (datetime.now() - self.session_start_time).seconds // 60
        correct_count = sum(1 for ex in self.current_session if ex.get("is_correct"))
        total_exercises = len(self.current_session)

        # 🔥 Collect error counts
        error_counts = {}
        for ex in self.current_session:
            for err in ex.get("error_analysis", []):
                error_counts[err] = error_counts.get(err, 0) + 1

        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        main_errors = [e[0] for e in sorted_errors[:3]] if sorted_errors else []

        summary = {
            "duration_minutes": session_duration,
            "total_exercises": total_exercises,
            "correct_exercises": correct_count,
            "accuracy_rate": round((correct_count / total_exercises) * 100, 1) if total_exercises > 0 else 0.0,
            "main_errors": main_errors
        }



        session_log = {
            "session_id": f"session_{datetime.now().strftime('%Y_%m_%d_%H%M')}",
            "user_id": self.profile.get("user_id", "user_001"),
            "date": datetime.now().strftime('%Y-%m-%d'),
            "duration_minutes": session_duration,
            "exercises": self.current_session,
            "summary": summary
        }
        log_exercise_to_session(session_log)

        # Reset
        self.current_session = []
        return summary

    def generate_exercise(self):
        from engine.generator import generate_exercise

        exercise = generate_exercise(self.profile, self.grammar_targets, self.recent_exercises)
        if not exercise:
            return None

        exercise_id = str(uuid4())
        exercise["exercise_id"] = exercise_id

        self.current_session.append(exercise)

        return {
            "exercise_id": exercise_id,
            "prompt": exercise["prompt"],
            "exercise_type": exercise["exercise_type"],
            "grammar_focus": exercise.get("grammar_focus", [])
        }

    def evaluate_exercise(self, exercise_id, user_answer):
        from engine.evaluator import evaluate_answer
        from engine.session import build_filled_sentence
        from engine.profile import update_user_profile

        matching = next((ex for ex in self.current_session if ex["exercise_id"] == exercise_id), None)
        if not matching:
            return None

        user_filled = build_filled_sentence(matching["prompt"], user_answer)
        feedback = evaluate_answer(
            prompt=user_filled,
            user_answer=user_filled,
            expected_answer=matching["filled_sentence"],
            grammar_focus=matching.get("grammar_focus", [])
        )

        # 🔥 Fix: update the exercise with result
        matching["is_correct"] = feedback["is_correct"]
        matching["error_analysis"] = feedback["error_analysis"]
        matching["corrected_answer"] = feedback.get("corrected_answer", "")

        # Track exercise result in profile immediately
        update_user_profile(self.profile, feedback, matching)

        self.recent_exercises.append({
            "exercise_type": matching["exercise_type"],
            "prompt": matching["prompt"],
            "user_answer": user_answer,
            "expected_answer": matching["expected_answer"],
            "result": "Correct" if feedback["is_correct"] else "; ".join(feedback["error_analysis"])
        })

        return feedback


def load_latest_session_summary():
    files = [f for f in os.listdir(SESSION_LOGS_DIR) if f.endswith(".json")]
    if not files:
        return None

    latest_file = sorted(files)[-1]
    with open(os.path.join(SESSION_LOGS_DIR, latest_file), "r", encoding="utf-8") as f:
        session_log = json.load(f)
    
    return session_log.get("summary")

@app.route("/")
def serve_index():
    return send_from_directory(".", "summary.html")

@app.route("/api/session/summary", methods=["GET"])
def get_session_summary():
    summary = load_latest_session_summary()
    if summary:
        return jsonify({"summary": summary}), 200
    else:
        return jsonify({"error": "No session summary available."}), 404


@app.route("/api/session/history", methods=["GET"])
def get_session_history():
    files = [f for f in os.listdir(SESSION_LOGS_DIR) if f.endswith(".json")]
    sessions = []

    for file in sorted(files, reverse=True):  # Newest first
        with open(os.path.join(SESSION_LOGS_DIR, file), "r", encoding="utf-8") as f:
            session_log = json.load(f)
            summary = session_log.get("summary")
            if summary:
                sessions.append({
                    "session_id": session_log.get("session_id", file),
                    "date": session_log.get("date", "Unknown Date"),
                    "total_exercises": summary.get("total_exercises", 0),
                    "accuracy_rate": summary.get("accuracy_rate", 0.0)
                })

    return jsonify({"sessions": sessions})

manager = ExerciseSessionManager()
manager.start_new_session()

@app.route("/api/exercise/new", methods=["POST"])
def api_new_exercise():
    exercise = manager.generate_exercise()
    if exercise:
        return jsonify({"exercise": exercise}), 200
    else:
        return jsonify({"error": "Could not generate exercise."}), 500

@app.route("/api/exercise/answer", methods=["POST"])
def api_answer_exercise():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Invalid JSON data."}), 400

    exercise_id = data.get("exercise_id")
    user_answer = data.get("user_answer")

    if not exercise_id or user_answer is None:
        return jsonify({"error": "Missing exercise_id or user_answer."}), 400

    feedback = manager.evaluate_exercise(exercise_id, user_answer)
    if feedback:
        return jsonify({"feedback": feedback}), 200
    else:
        return jsonify({"error": "Exercise ID not found."}), 404



@app.route("/api/session/start", methods=["POST"])
def api_start_session():
    manager.start_new_session()
    return jsonify({"message": "New session started."}), 200

@app.route("/api/session/end", methods=["POST"])
def api_end_session():
    session_summary = manager.end_current_session()
    if session_summary:
        return jsonify({"summary": session_summary}), 200
    else:
        return jsonify({"error": "No active session."}), 400



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
