import json
import os
from flask import Flask, jsonify, send_from_directory, request
from uuid import uuid4
from datetime import datetime
from engine.profile import load_user_profile, update_user_profile
from engine.planner import select_focus_areas
from engine.generator import generate_exercise
from engine.evaluator import evaluate_answer, build_filled_sentence
from engine.logger import log_exercise_to_session
from engine.utils import normalize_grammar_id, summarize_common_errors
from engine.profile import load_user_profile, save_user_profile
from engine.utils import categorize_session_errors, merge_error_categories
from engine.curriculum import load_curriculum


app = Flask(__name__, static_folder="web", static_url_path="/")

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
        

        if not self.current_session:
            return None

        session_duration = (datetime.now() - self.session_start_time).seconds // 60
        answered_exercises = [ex for ex in self.current_session if "is_correct" in ex]
        correct_count = sum(1 for ex in answered_exercises if ex["is_correct"])
        total_exercises = len(answered_exercises)


        # 🔥 Collect error counts
        error_counts = {}
        for ex in answered_exercises:
            for err in ex.get("error_analysis", []):
                error_counts[err] = error_counts.get(err, 0) + 1

        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        main_errors = [e[0] for e in sorted_errors[:3]] if sorted_errors else []

        # Step 1: Extract session-only error counts
        session_errors = {}
        for ex in answered_exercises:
            for err in ex.get("error_analysis", []):
                session_errors[err] = session_errors.get(err, 0) + 1

        # Step 2: Load current categories + grammar tree
        existing_categories = self.profile.get("common_error_categories", [])
        curriculum_tree = load_curriculum(self.profile.get("target_language", "korean"))

        # Step 3: Categorize session errors with LLM
        new_categorized = categorize_session_errors(session_errors, existing_categories, curriculum_tree)

        # Step 4: Merge new categorizations into existing ones deterministically
        merged = merge_error_categories(existing_categories, new_categorized)

        # Step 5: Save
        self.profile["common_error_categories"] = merged
        save_user_profile(self.profile)

        summary = {
            "duration_minutes": session_duration,
            "total_exercises": total_exercises,
            "correct_exercises": correct_count,
            "accuracy_rate": round((correct_count / total_exercises) * 100, 1) if total_exercises > 0 else 0.0,
            "main_errors": main_errors,
            "error_categories": merged
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
            "expected_answer": exercise["expected_answer"],
            "filled_sentence": exercise["filled_sentence"],
            "glossary": exercise["glossary"],
            "grammar_focus": exercise.get("grammar_focus", []),
            "translated_sentence": exercise.get("translated_sentence", "")
        }

    def evaluate_exercise(self, exercise_id, user_answer):
        matching = next((ex for ex in self.current_session if ex["exercise_id"] == exercise_id), None)
        if not matching:
            return None

        filled = build_filled_sentence(matching["prompt"], user_answer)
        expected = matching["filled_sentence"]

        # ✅ Fast match check: skip LLM if identical
        if filled.strip() == expected.strip():
            feedback = {
                "is_correct": True,
                "corrected_answer": expected,
                "error_analysis": [],
                "grammar_focus": matching.get("grammar_focus", []),
                "explanation_summary": "Perfect match — no issues detected."
            }
        else:
            feedback = evaluate_answer(
                prompt=matching["prompt"],
                user_answer=filled,
                expected_answer=expected,
                grammar_focus=matching.get("grammar_focus", []),
                target_language=self.profile.get("target_language", "Korean")
            )


        feedback["grammar_focus"] = [normalize_grammar_id(g) for g in feedback.get("grammar_focus", [])]


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

manager = ExerciseSessionManager()
manager.start_new_session()

@app.route("/")
def serve_index():
    return send_from_directory("web", "dashboard.html")


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

@app.route("/api/config/update", methods=["POST"])
def update_config():
    data = request.get_json()
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    provider = data.get("provider", config.get("default_provider"))
    config["default_provider"] = provider

    if provider == "openai":
        config["openai_model"] = data.get("model", config.get("openai_model"))
    elif provider == "local":
        config["local_port"] = int(data.get("port", config.get("local_port")))
        config["local_model"] = data.get("model", config.get("local_model"))

    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return jsonify({"message": "Configuration updated successfully."})



@app.route("/api/session/summary", methods=["GET"])
def get_session_summary():
    summary = load_latest_session_summary()
    if not summary:
        return jsonify({"error": "No session summary available."}), 404

    return jsonify({"summary": summary}), 200

@app.route("/api/errors/aggregate", methods=["POST"])
def api_aggregate_common_errors():
    from engine.utils import summarize_common_errors
    from engine.profile import load_user_profile, save_user_profile

    profile = load_user_profile()
    error_dict = profile.get("common_errors", {})

    if not error_dict:
        return jsonify({"message": "No common errors to summarize."}), 200

    summary = summarize_common_errors(error_dict)
    profile["common_error_categories"] = summary
    save_user_profile(profile)

    return jsonify({"message": "Common errors summarized.", "categories": summary}), 200



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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
