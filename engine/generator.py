import json
import re
from engine.llm_client import chat

def sanitize_json_string(s):
    s = s.strip()

    # Remove Markdown-style code fences if present
    if s.startswith("```"):
        s = s.strip("`")
        s = s.replace("json\n", "", 1).replace("\n", "", 1)

    s = s.replace('“', '"').replace('”', '"').replace("’", "'")
    return s


def generate_exercise(user_profile, grammar_targets, recent_exercises=None):

    """
    Request a beginner-level exercise from GPT based on current profile and grammar focus.
    Returns structured exercise as dict.
    """

    vocab_core = list(user_profile.get("vocabulary", {}).get("core", {}).keys())[:6]
    vocab_familiar = list(user_profile.get("vocabulary", {}).get("familiar", {}).keys())[:3]
    vocab_new = list(user_profile.get("vocabulary", {}).get("newly_introduced", {}).keys())[:2]

    # Resolve language preferences
    native_lang = user_profile.get("native_language", "English")
    target_lang = user_profile.get("target_language", "Korean")
    instruction_lang = user_profile.get("instruction_language", native_lang)
    task_lang = user_profile.get("task_language", target_lang)

    # Format grammar maturity into readable lines
    grammar_maturity_section = "\n".join(
        f"- {g.replace('_', ' ')}: {info['status']}"
        for g, info in user_profile.get("grammar_summary", {}).items()
    )

    formality_instruction = ""
    preferred_formality = user_profile.get("learning_preferences", {}).get("preferred_formality", "polite")

    if preferred_formality == "polite":
        formality_instruction = "Use polite verb endings appropriate for friendly but respectful conversation (~어요/아요 endings)."
    elif preferred_formality == "casual":
        formality_instruction = "Use casual speech verb endings appropriate for close friends or younger people."
    elif preferred_formality == "formal":
        formality_instruction = "Use formal verb endings appropriate for official or respectful situations (~습니다 endings)."


    # Build segmented prompt with very clear directives
    prompt = f"""
    You are a Korean language tutor assistant. Your role is to generate structured learning tasks.

    The user's profile:
    - Proficiency level: {user_profile.get("level", "beginner")}
    - Native language: {native_lang}
    - Target language: {target_lang}
    - Instruction language: {instruction_lang}
    - Task language: {task_lang}

    They want instructions and explanations in {instruction_lang}, but the exercise itself (the thing they will respond to) must be written entirely in {task_lang}.

    ## Constraints:
    - You must return only ONE exercise.
    - Only ONE exercise should be returned — never include multiple items or numbered lists.
    - Choose one exercise_type from the list below:
        - "fill_in_blank": one blank in one sentence, clearly marked with ___. This can be either for a word, several consecituve words, or a particle.
        - "multiple_choice"
        - "translation"
        - "open_prompt"
    If exercise_type is \"fill_in_blank\":
        - Prompt must contain one blanks marked as ___.
        - expected_answer must be a string (for one blank).
        - filled_sentence must be the full sentence with all blanks filled in correctly.
    - Do NOT explain or comment on the exercise.
    - The exercise should match this type: {user_profile['learning_preferences']['preferred_exercise_types'][0]}
    - It must reinforce these grammar points: {grammar_targets}
    - Match the user's level: {user_profile.get("level", "beginner")}-appropriate grammar and vocabulary.
    - The prompt must be written in {task_lang}, the glossary in {instruction_lang}, and the answer in {target_lang}.
    - {formality_instruction}


    ## Grammar Maturity (for your planning):
    {grammar_maturity_section}

    ## Vocabulary to use:
    - Core: {vocab_core}
    - Familiar: {vocab_familiar}
    - Allow up to 2 new words (optional): {vocab_new}

    ## Format:
    Return ONLY one exercise as a valid JSON object with the following keys:
    {{
      "exercise_type": "...",
      "prompt": "...",
      "expected_answer": "...",
      "filled_sentence": "...",
      "glossary": {{ "term": "definition", ... }},
      "grammar_focus": [ ... ]
    }}

    """

    if recent_exercises:
        prompt += "\n## Session History:\n"
        for idx, ex in enumerate(recent_exercises[-3:], 1):
            prompt += f"- Exercise {idx}:\n"
            prompt += f"  Type: {ex['exercise_type']}\n"
            prompt += f"  Prompt: {ex['prompt']}\n"
            prompt += f"  User Answer: {ex['user_answer']}\n"
            prompt += f"  Expected: {ex['expected_answer']}\n"
            prompt += f"  Result: {ex['result']}\n"
        prompt += "\nAvoid repeating prompts or patterns from the session history listed above.\n"


    response_text = chat(
        messages=[
            {"role": "system", "content": "You are a helpful Korean tutor assistant."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.4
    )

    try:
        return json.loads(sanitize_json_string(response_text))
    except json.JSONDecodeError:
        print("⚠️ GPT response was not valid JSON:")
        print(response_text)

        with open("last_response_debug.txt", "w", encoding="utf-8") as f:
            f.write(response_text)

        return None



