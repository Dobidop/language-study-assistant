import json
import re
from engine.llm_client import chat
import os
import random

# Load vocab data
VOCAB_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'vocab_data.json')
with open(VOCAB_DATA_PATH, 'r', encoding='utf-8') as f:
    VOCAB_DATA = json.load(f)



def categorize_vocab(shuffle=True, limit_core=6, limit_familiar=3, limit_new=2):
    core = []
    familiar = []
    newly_introduced = []

    for item in VOCAB_DATA:
        ease = item.get("ease")
        word = item.get("vocab")
        if ease is None or ease == 0:
            newly_introduced.append(word)
        elif ease > 2.5:
            core.append(word)
        else:
            familiar.append(word)

    if shuffle:
        random.shuffle(core)
        random.shuffle(familiar)
        random.shuffle(newly_introduced)

    return core[:limit_core], familiar[:limit_familiar], newly_introduced[:limit_new]



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
    vocab_core, vocab_familiar, vocab_new = categorize_vocab()

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
    - Do NOT explain or comment on the exercise.
    - The exercise should preferably (but not necessarily) match this type: {user_profile['learning_preferences']['preferred_exercise_types'][0]}
    - It must reinforce these grammar points: {grammar_points_formatted}
    - Match the user's level: {user_profile.get("level", "beginner")}-appropriate grammar and vocabulary.
    - The prompt must be written in {task_lang}, the glossary in {instruction_lang}, and the answer in {target_lang}.
    - {formality_instruction}
    - Provide ALL words for the glossary in dictionary(this is a must!) form (including from the suggested solution)
    - The generated sentence MUST make sense. It cannot be something like "I drink an apple"

    ## Grammar Maturity (for your planning):
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
        for idx, ex in enumerate(recent_exercises[-3:], 1):
            prompt += f"- Exercise {idx}:\n"
            prompt += f"  Type: {ex['exercise_type']}\n"
            prompt += f"  Prompt: {ex['prompt']}\n"
            prompt += f"  User Answer: {ex['user_answer']}\n"
            prompt += f"  Expected: {ex['expected_answer']}\n"
            prompt += f"  Result: {ex['result']}\n"
        prompt += "\nAvoid repeating prompts or patterns from the session history listed above.\n"
    print(prompt)

    response_text = chat(
        messages=[
            {"role": "system", "content": "You are a helpful Korean tutor assistant."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.4
    )
    response_text = response_text.replace("___ .","___.")
    print(response_text)
    try:
        return json.loads(sanitize_json_string(response_text))
    except json.JSONDecodeError:
        print("⚠️ GPT response was not valid JSON:")
        print(response_text)

        with open("last_response_debug.txt", "w", encoding="utf-8") as f:
            f.write(response_text)

        return None



