import json
from datetime import datetime
from engine.utils import normalize_grammar_id


def build_exercise_prompt(
    user_profile: dict,
    grammar_targets: list,
    vocab_new: list,
    vocab_familiar: list,
    vocab_core: list,
    grammar_maturity_section: str,
    recent_exercises: list = None,
    forced_exercise_type: str = "fill_in_blank"
) -> str:
    """
    Constructs the detailed LLM prompt for exercise generation.
    Only generates one exercise type, explicitly forced by caller.
    """
    target_lang = user_profile.get('target_language', 'Korean')
    native_lang = user_profile.get('native_language', 'English')
    instruction_lang = user_profile.get('instruction_language', 'English')
    task_lang = user_profile.get('task_language', target_lang)
    level = user_profile.get('level', user_profile.get('user_level', 'beginner'))
    formality_instruction = user_profile.get('learning_preferences', {}).get('preferred_formality', '')

    grammar_points_formatted = "\n" + "\n".join(f"- {normalize_grammar_id(g)}" for g in grammar_targets)

    prompt = f"""/no_think
You are a {target_lang} language tutor assistant. Your role is to generate structured learning tasks.

The user's profile:
- Proficiency level: {level}
- Native language: {native_lang}
- Target language: {target_lang}
- Instruction language: {instruction_lang}
- Task language: {task_lang}

They want instructions and explanations in {instruction_lang}, but the exercise itself must be written entirely in {task_lang}.

## Constraints:
- You must return only ONE exercise.
- Exercise type must be: "{forced_exercise_type}"
- Do not include multiple exercises or numbered lists.
"""
    
    # Tailored constraints
    if forced_exercise_type == "fill_in_blank":
        prompt += """
        - Prompt must contain one blank marked as ___. 
        - It is very important that the blank part actually would be completed by the missing word(s) or particles! Be sure that the blank, "___", serves a purpose!
        - expected_answer must be a string (for one blank).
        - filled_sentence must be the full sentence with all blanks filled in correctly. 
        - the blanks should also include any attached particles; i.e. "사과를" should always be blanked out as one word, never just as "___를". 
            - For example: (expected answer=소주를) Incorrect prompt: 저는 ___를 마셔요. Correct prompt: 저는 ___ 마셔요. This is very important
        - do NOT leave any space between the blank part and other characters if the answer is supposed to be connected to those other characters.
        - The blank MUST be at a place which the users practice the grammar points! Do not just 'blank' random words. 
            - For example: If the exercise is about location of action, blanking the entire word "방에서" would be much better, like this Incorrect: (expected answer = 내) 저는 ___ 방에서 소주를 마셔요, Correct: (expected answer = 방에서) 저는 내 ___ 소주를 마셔요
        - If the grammar point for the exercise is related to particles, then that is the word to replace blank
        - IMPORTANT: It is better to <blank> an entire word instead of just the grammar focus. Make sure you blank out the relevant part of the exercise!
        """
    elif forced_exercise_type == "translation":
        prompt += f"""
- Provide a sentence in {instruction_lang} the user must translate into {task_lang}.
- expected_answer is the correct {task_lang} translation.
"""

    prompt += f"""
    - Do NOT explain or comment on the exercise.
    - The exercise should preferably (but not necessarily) match this type: {user_profile['learning_preferences']['preferred_exercise_types'][0]}


    ## Exercise specification:
    - It must use these grammar points as ther blank: {grammar_points_formatted}
    - Match the user's level: {user_profile.get("level", "beginner")}-appropriate grammar and vocabulary.
    - The prompt must be written in {task_lang}, the glossary in {instruction_lang}, and the answer in {target_lang}.
    - Provide ALL words for the glossary in basic dictionary(this is a must!) form
    - The generated sentence MUST make sense. It cannot be something like "I drink an apple"
    - If choosing the multiple "fill_in_blank" or "multiple_choice", then the specific blanked item/choice MUST be one of the grammar focus words and/or particles!
    - Be absolutely certain that the blank is actually replacing a word, and that it makes sense to insert the 'expected_answer' in that spot. 
        - For example:
            This is incorrect: 저는 아침에 커피를 ___ 마셔요. (expected_answer = 마셔요)
            This is correct: 저는 아침에 커피를 ___. (expected_answer = 마셔요)
    - You MUST this language formality level: {formality_instruction}, This is very important!!!!

    ## Grammar Maturity:
    {grammar_maturity_section}
    - never use possessive particle "내/의", as the grammar focus.

    ## Vocabulary to use:
    - Core: {vocab_core}
    - Familiar: {vocab_familiar}
    - Allow up to 2 new words (optional): {vocab_new}, or other level appropriate words

    ## Format:
    Return ONLY one exercise as a valid JSON object with the following keys (only valid JSON is accepted!):
    {{
      "exercise_type": "...",
      "prompt": "...",
      "expected_answer": "...",
      "filled_sentence": "...",
      "glossary": {{ "terms (used in THIS exercise sentence (in dictionary form)": "definition in {instruction_lang}"}},
      "translated_sentence": "filled_sentence, but translated to {instruction_lang}. This must also include any filled in blank spaces!",
      "grammar_focus": [ ... ]
    }}
    """

    # Optionally append recent exercises history
    if recent_exercises:
        prompt += "\n## Session History:\n"
        for idx, ex in enumerate(recent_exercises[-10:], 1):
            prompt += f"- Exercise {idx}: Type: {ex.get('exercise_type')}\n"
            prompt += f"  Prompt: {ex.get('prompt')}\n"
            prompt += f"  User Answer: {ex.get('user_answer')}\n"
            prompt += f"  Expected: {ex.get('expected_answer')}\n"
            prompt += f"  Result: {'correct' if ex.get('is_correct') else 'incorrect'}\n"
        prompt += "Avoid repeating patterns from the session history.\n"

    return prompt
