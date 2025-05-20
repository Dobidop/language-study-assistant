import json
import os
from engine.llm_client import chat
from engine.planner import select_review_and_new_items
from engine.utils           import normalize_grammar_id, sanitize_json_string
from engine.prompt_builder import build_exercise_prompt
from datetime import datetime

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VOCAB_DATA_PATH = os.path.join(BASE_DIR, 'vocab_data.json')
with open(VOCAB_DATA_PATH, 'r', encoding='utf-8') as f:
    VOCAB_DATA = json.load(f)

# Helper loaders

def load_user_profile(path: str = None) -> dict:
    path = path or os.path.join(BASE_DIR, 'user_profile.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_curriculum(path: str = None) -> dict:
    path = path or os.path.join(BASE_DIR, 'korean.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_vocab_data(path: str = None) -> dict:
    path = path or VOCAB_DATA_PATH
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Core generate_exercise now delegates prompt building

def generate_exercise(user_profile: dict,
                      grammar_targets: list,
                      recent_exercises: list = None) -> dict:
    # 1) Compute the “Grammar Maturity” section
    grammar_summary = user_profile.get('grammar_summary', {})
    grammar_maturity_section = "\n".join(
        f"- {normalize_grammar_id(gid)}: level {info.get('srs_level',0)}, next review {info.get('next_review_date','N/A')}"
        for gid, info in grammar_summary.items()
        if gid in grammar_targets
    ) or "None"

    # 2) Split vocab into new/familiar/core by reps
    vocab_summary = user_profile.get('vocab_summary', {})
    vocab_new, vocab_familiar, vocab_core = [], [], []
    for w, info in vocab_summary.items():
        reps = info.get('reps', 0)
        if reps <= 1:
            vocab_new.append(w)
        elif reps <= 3:
            vocab_familiar.append(w)
        else:
            vocab_core.append(w)

    # 3) Delegate the big prompt construction here
    prompt = build_exercise_prompt(
        user_profile=user_profile,
        grammar_targets=grammar_targets,
        vocab_new=vocab_new,
        vocab_familiar=vocab_familiar,
        vocab_core=vocab_core,
        grammar_maturity_section=grammar_maturity_section,
        recent_exercises=recent_exercises
    )
    
    print(f' ==> [Line 60]: \033[38;2;102;209;152m[prompt]\033[0m({type(prompt).__name__}) = \033[38;2;111;95;170m{prompt}\033[0m')
    print(f' ==> [Line 70]: \033[38;2;40;126;47m[vocab_new]\033[0m({type(vocab_new).__name__}) = \033[38;2;105;246;13m{vocab_new}\033[0m')
    print(f' ==> [Line 71]: \033[38;2;14;96;225m[vocab_familiar]\033[0m({type(vocab_familiar).__name__}) = \033[38;2;145;38;28m{vocab_familiar}\033[0m')
    print(f' ==> [Line 72]: \033[38;2;211;42;127m[vocab_core]\033[0m({type(vocab_core).__name__}) = \033[38;2;46;27;17m{vocab_core}\033[0m')
    print(f' ==> [Line 73]: \033[38;2;232;154;166m[grammar_maturity_section]\033[0m({type(grammar_maturity_section).__name__}) = \033[38;2;15;197;31m{grammar_maturity_section}\033[0m')

    # 4) Call the LLM correctly and parse its JSON
    response_text = chat([
        {"role": "system", "content": f"You are a helpful {user_profile.get('target_language','Korean')} tutor assistant."},
        {"role": "user",   "content": prompt}
    ], temperature=0.4)

    safe = sanitize_json_string(response_text)
    print(f' ==> [Line 76]: \033[38;2;92;44;89m[safe]\033[0m({type(safe).__name__}) = \033[38;2;169;96;16m{safe}\033[0m')
    return json.loads(safe)


# Wrapper to use planner selections

def generate_exercise_auto(
    profile_path: str = None,
    recent_exercises: list = None
) -> dict:
    """
    Selects grammar and vocabulary via SRS planner, then delegates to generate_exercise.
    """
    profile = load_user_profile(profile_path)
    selections = select_review_and_new_items(profile_path=profile_path)
    grammar_targets = [normalize_grammar_id(g) for g in
                       selections['review_grammar'] + selections['new_grammar']]
    return generate_exercise(profile, grammar_targets, recent_exercises)

# Example CLI usage
if __name__ == '__main__':
    ex = generate_exercise_auto()
    print(json.dumps(ex, ensure_ascii=False, indent=2))
