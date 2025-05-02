import json
import re
from engine.llm_client import chat
import os
import random



# Load vocab data
VOCAB_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'vocab_data.json')
with open(VOCAB_DATA_PATH, 'r', encoding='utf-8') as f:
    VOCAB_DATA = json.load(f)

def select_vocab_words(vocab_list, count=10, focus_rank=500, rank_deviation=300):
    # Step 1: Prioritize by need
    sorted_vocab = sorted(
        vocab_list,
        key=lambda v: (
            v.get("lapses", 0) > 0,
            v.get("ease", 2.5),
            -v.get("reps", 0),
            v.get("frequency_rank", 9999)
        ),
        reverse=True
    )

    # Step 2: Filter by frequency rank deviation
    close_rank_words = [v for v in sorted_vocab
                        if abs(v.get("frequency_rank", 9999) - focus_rank) <= rank_deviation]

    # Step 3: Random selection from different importance tiers
    top_focus = close_rank_words[:count * 2]
    low_reps = [v for v in close_rank_words if v.get("reps", 0) <= 2]

    selected = random.sample(top_focus, min(5, len(top_focus))) + \
               random.sample(low_reps, min(3, len(low_reps)))

    # Fill up remaining from full pool with some randomness
    remaining = [v for v in sorted_vocab if v not in selected]
    selected += random.sample(remaining, max(0, count - len(selected)))

    return selected[:count]

def categorize_vocab_smart(shuffle=True, count=20):
    selected = select_vocab_words(VOCAB_DATA, count=count)

    core = [v["vocab"] for v in selected if v.get("ease", 0) > 2.5]
    familiar = [v["vocab"] for v in selected if 1.5 < v.get("ease", 0) <= 2.5]
    new = [v["vocab"] for v in selected if v.get("ease", 0) <= 1.5]

    if shuffle:
        random.shuffle(core)
        random.shuffle(familiar)
        random.shuffle(new)

    return core[:10], familiar[:6], new[:2]


def sanitize_json_string(s):
    s = s.strip()

    # Remove <think>...</think> and anything before first {
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL)
    
    # Keep only content between first "{" and last "}"
    if "{" in s and "}" in s:
        start = s.find("{")
        end = s.rfind("}")
        s = s[start:end+1]

    s = s.replace('“', '"').replace('”', '"').replace("’", "'")
    return s


def generate_exercise(user_profile, grammar_targets, recent_exercises=None):
    vocab_core, vocab_familiar, vocab_new = categorize_vocab_smart()

    # Then slice if needed
    vocab_core = vocab_core[:6]
    vocab_familiar = vocab_familiar[:3]
    vocab_new = vocab_new[:2]


    native_lang = user_profile.get("native_language", "English")
    target_lang = user_profile.get("target_language", "Korean")
    instruction_lang = user_profile.get("instruction_language", native_lang)
    task_lang = user_profile.get("task_language", target_lang)

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

    # 👉 NEW: grammar_targets is now a list of dicts, not strings
    if grammar_targets:
        grammar_points_formatted = ", ".join(
            f"{gt['description']} ({gt['id']})" for gt in grammar_targets
        )
    else:
        grammar_points_formatted = "none"

    prompt = f"""/no_think
    You are a {target_lang} language tutor assistant. Your role is to generate structured learning tasks.

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
        - "fill_in_blank": one blank in one sentence, clearly marked with ___.
        - "multiple_choice"
        - "translation"
        - "open_prompt"
    If exercise_type is "fill_in_blank":
        - Prompt must contain one blank marked as ___. 
        - It is very important that the blank part actually would be completed by the missing word(s) or particles! Be sure that the blank, "___", serves a purpose!
        - expected_answer must be a string (for one blank).
        - filled_sentence must be the full sentence with all blanks filled in correctly. 
        - the blanks should also include any attached particles; i.e. "사과를" should always be blanked out as one word, never just as "___를". 
            - For example: (expected answer=소주를) Incorrect prompt: 저는 ___를 마셔요. Correct prompt: 저는 ___ 마셔요
        - do NOT leave any space between the blank part and other characters if the answer is supposed to be connected to those other characters.
        - The blank MUST be at a place which lets the user practice the grammar points! Do not just 'blank' random words. 
            - For example: If the exercise is about location of action, blanking "방에서" would be much better! Incorrect: (expected answer = 내) 저는 ___ 방에서 소주를 마셔요, Correct: (expected answer = 방에서) 저는 내 ___ 소주를 마셔요
        - If the grammar point for the exercise is related to particles, then that is the word to replace blank
    - Do NOT explain or comment on the exercise.
    - The exercise should preferably (but not necessarily) match this type: {user_profile['learning_preferences']['preferred_exercise_types'][0]}
    - It must reinforce these grammar points: {grammar_points_formatted}
    - Match the user's level: {user_profile.get("level", "beginner")}-appropriate grammar and vocabulary.
    - The prompt must be written in {task_lang}, the glossary in {instruction_lang}, and the answer in {target_lang}.
    - {formality_instruction}
    - Provide ALL words for the glossary in basic dictionary(this is a must!) form (including from the suggested solution)
    - The generated sentence MUST make sense. It cannot be something like "I drink an apple"


    ## Grammar Maturity (for your planning, avoid using "내", posessive, as the grammar point):
    {grammar_maturity_section}

    ## Vocabulary to use:
    - Core: {vocab_core}
    - Familiar: {vocab_familiar}
    - Allow up to 2 new words (optional): {vocab_new}, or other level appropriate words

    ## Format:
    Return ONLY one exercise as a valid JSON object with the following keys:
    {{
      "exercise_type": "...",
      "prompt": "...",
      "expected_answer": "...",
      "filled_sentence": "...",
      "glossary": {{ "term (in dictionary form)": "definition", ... }},
      "translated_sentence": "filled_sentence, but translated to {instruction_lang}. This must also include any filled in blank spaces!",
      "grammar_focus": [ ... ]
    }}
    """

    if recent_exercises:
        prompt += "\n## Session History:\n"
        for idx, ex in enumerate(recent_exercises[-10:], 1):
            prompt += f"- Exercise {idx}:\n"
            prompt += f"  Type: {ex['exercise_type']}\n"
            prompt += f"  Prompt: {ex['prompt']}\n"
            prompt += f"  User Answer: {ex['user_answer']}\n"
            prompt += f"  Expected: {ex['expected_answer']}\n"
            prompt += f"  Result: {ex['result']}\n"
        prompt += "\nAvoid repeating prompts, patterns, and/or patterns from the session history listed above.\n"

    print(f' ==> [Line 164]: \033[38;2;176;134;198m[prompt]\033[0m({type(prompt).__name__}) = \033[38;2;127;177;201m{prompt}\033[0m')

    response_text = chat(
        messages=[
            {"role": "system", "content": f"""You are a helpful {target_lang} tutor assistant."""},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.4
    )
    response_text = response_text.replace("___ .","___.")
    print(f' ==> [Line 175]: \033[38;2;51;223;163m[response_text]\033[0m({type(response_text).__name__}) = \033[38;2;119;128;184m{response_text}\033[0m')
    try:
        return json.loads(sanitize_json_string(response_text))
    except json.JSONDecodeError:
        print("⚠️ GPT response was not valid JSON:")
        print(response_text)

        with open("last_response_debug.txt", "w", encoding="utf-8") as f:
            f.write(response_text)

        return None



