import json
import uuid
from datetime import datetime
from engine.profile import load_user_profile, update_user_profile
from engine.generator import generate_exercise
from engine.evaluator import evaluate_answer, build_filled_sentence
from engine.logger import log_exercise_to_session
from engine.planner import select_focus_areas


def build_filled_sentence(prompt: str, user_response: str | list[str]) -> str:
    if isinstance(user_response, str):
        return prompt.replace("___", user_response, 1)
    elif isinstance(user_response, list):
        filled = prompt
        for fill in user_response:
            filled = filled.replace("___", fill, 1)
        return filled
    return prompt


def run_session():
    print("\n--- Korean Study Session ---\n")

    # Load user profile
    profile = load_user_profile("user_profile.json")
    user_id = profile.get("user_id", "user_001")

    # Session setup
    session_id = f"session_{datetime.today().strftime('%Y_%m_%d_%H%M')}"
    session_log = {
        "session_id": session_id,
        "user_id": user_id,
        "date": datetime.today().strftime('%Y-%m-%d'),
        "duration_minutes": 0,
        "exercises": [],
        "summary": {},
        "updates_to_user_profile": {},
        "user_profile_updated": False
    }

    # At the beginning of the session
    starting_grammar_status = {
        g: info.get("status", "new")
        for g, info in profile.get("grammar_summary", {}).items()
    }


    # Select grammar focus
    grammar_targets = select_focus_areas(profile)
    print(f"→ Today's grammar focus: {grammar_targets}\n")

    # Initialize session history
    recent_exercises = []


    # Start session loop
    exercise_count = 0
    session_start = datetime.now()

    while True:
        # Generate and present exercise
        exercise = generate_exercise(profile, grammar_targets, recent_exercises)
        if not exercise or "prompt" not in exercise:
            print("⚠️ No valid exercise was returned. Skipping.")
            continue

        print(f"Exercise:\n{exercise['prompt']}\n")

        # Get user input
        user_answer = input("Your answer: ").strip()

        # Fill user's answer into the blank(s)
        user_filled = build_filled_sentence(exercise["prompt"], user_answer)

        # Evaluate the user's answer
        feedback = evaluate_answer(
            prompt=user_filled,
            user_answer=user_filled,
            expected_answer=exercise["filled_sentence"],
            grammar_focus=exercise["grammar_focus"]
        )

        print("\n--- Feedback ---")
        if feedback["is_correct"]:
            print("✅ Correct!")
        else:
            print("❌ Not quite right.")
            print("Suggested correction:", feedback["corrected_answer"])
            print("Explanation:")
            for point in feedback["error_analysis"]:
                print("-", point)

        # Log exercise
        log_entry = {
            "exercise_id": str(uuid.uuid4()),
            "exercise_type": exercise["exercise_type"],
            "prompt": exercise["prompt"],
            "user_answer": user_answer,
            "expected_answer": exercise["expected_answer"],
            "filled_sentence": exercise["filled_sentence"],
            "is_correct": feedback["is_correct"],
            "error_analysis": feedback["error_analysis"],
            "grammar_focus": feedback["grammar_focus"],
            "vocab_used": list(exercise["glossary"].keys())
        }
        session_log["exercises"].append(log_entry)
        exercise_count += 1

        # Update profile after each exercise
        update_user_profile(profile, feedback, exercise)
        session_log["user_profile_updated"] = True

        # Update session history
        recent_exercises.append({
            "exercise_type": exercise["exercise_type"],
            "prompt": exercise["prompt"],
            "user_answer": user_answer,
            "expected_answer": exercise["expected_answer"],
            "result": "Correct" if feedback["is_correct"] else "; ".join(feedback["error_analysis"])
        })


        # Ask if user wants another exercise
        more = input("\nDo you want another exercise? (y/n): ").strip().lower()
        if more != "y":
            break

    # End session
    session_duration = (datetime.now() - session_start).seconds // 60

    # Build session summary
    correct_count = sum(1 for ex in session_log["exercises"] if ex["is_correct"])
    total_exercises = len(session_log["exercises"])
    error_counts = {}

    for ex in session_log["exercises"]:
        for err in ex["error_analysis"]:
            error_counts[err] = error_counts.get(err, 0) + 1

    # Determine main error areas
    sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
    main_errors = [e[0] for e in sorted_errors[:3]]  # Top 3 error types


    # Compare grammar promotions
    ending_grammar_status = {
        g: info.get("status", "new")
        for g, info in profile.get("grammar_summary", {}).items()
    }

    promotions = 0
    for g in starting_grammar_status:
        if starting_grammar_status[g] != "strong" and ending_grammar_status.get(g) == "strong":
            promotions += 1

    # Populate summary block
    session_log["summary"] = {
        "duration_minutes": session_duration,
        "total_exercises": total_exercises,
        "correct_exercises": correct_count,
        "accuracy_rate": round((correct_count / total_exercises) * 100, 1) if total_exercises > 0 else 0.0,
        "main_errors": main_errors,
        "promotions": promotions
    }

    # Save session log
    log_exercise_to_session(session_log)

    # CLI report (for now)
    print(f"\n📚 Session complete! Exercises completed: {total_exercises}, Duration: {session_duration} minutes.")
    print(f"✅ Correct answers: {correct_count} ({session_log['summary']['accuracy_rate']}%)")
    if main_errors:
        print("⚠️ Common mistakes:")
        for err in main_errors:
            print(f"- {err}")
    else:
        print("🎉 No significant recurring mistakes!")



if __name__ == "__main__":
    run_session()
