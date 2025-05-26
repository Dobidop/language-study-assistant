import re
import json
from engine.llm_client import chat

def normalize_grammar_id(raw_id: str) -> str:
    """
    Improved normalization that preserves Korean characters and creates consistent IDs.
    
    Rules:
    1. Keep Korean characters intact
    2. Normalize slash variants: / vs - vs nothing  
    3. Remove extra spaces and punctuation
    4. Use lowercase for English parts
    5. Use consistent separators
    
    Examples:
    '-아요/-어요' -> '-아요_어요'
    '-아요-어요' -> '-아요_어요' 
    '-아요어요' -> '-아요_어요'
    '-이에요/예요' -> '-이에요_예요'
    """
    if not raw_id:
        return raw_id
        
    s = raw_id.strip()
    
    # Handle Korean character separations (be more specific about boundaries)
    s = re.sub(r'([가-힣])/([가-힣])', r'\1_\2', s)  # 아요/어요 -> 아요_어요
    s = re.sub(r'([가-힣])-([가-힣])', r'\1_\2', s)   # 아요-어요 -> 아요_어요
    
    # Handle cases where Korean chars are mashed together (need manual rules)
    korean_splits = {
        '이에요예요': '이에요_예요',
        '아요어요': '아요_어요', 
        '은는': '은_는',
        '이가': '이_가',
        '을를': '을_를'
    }
    
    for original, replacement in korean_splits.items():
        s = s.replace(original, replacement)
    
    # Handle mixed patterns like "-아요/-어요" more aggressively
    # Look for pattern: prefix + korean + separator + korean + suffix
    s = re.sub(r'(-[가-힣]+)/(-[가-힣]+)', r'\1_\2', s)  # -아요/-어요 -> -아요_-어요
    s = re.sub(r'(-[가-힣]+)-(-[가-힣]+)', r'\1_\2', s)   # -아요--어요 -> -아요_-어요
    
    # Clean up double prefixes: -아요_-어요 -> -아요_어요
    s = re.sub(r'_-([가-힣])', r'_\1', s)
    
    # Normalize English parts to lowercase
    s = re.sub(r'[A-Z]', lambda m: m.group().lower(), s)
    
    # Clean up punctuation but keep Korean chars and essential markers
    s = re.sub(r'[^\w\s가-힣_\-]', '', s)  # Keep Korean, word chars, spaces, underscores, hyphens
    s = re.sub(r'\s+', '_', s)  # Spaces to underscores
    s = re.sub(r'_+', '_', s)   # Collapse multiple underscores
    s = s.strip('_')            # Remove leading/trailing underscores
    
    return s


def merge_error_categories(existing, new):
    """
    Deterministically merge LLM-categorized session errors into existing categories.
    - LLM input is session-only: each 'new_cat' count is for this session.
    - Sum counts across sessions.
    - Merge examples, avoiding duplicates.
    """
    label_to_cat = {cat["label"]: cat for cat in existing}

    for new_cat in new:
        label = new_cat["label"]
        session_count = new_cat.get("count", 0)
        session_examples = set(new_cat.get("examples", []))

        if label in label_to_cat:
            existing_cat = label_to_cat[label]
            existing_cat["count"] = existing_cat.get("count", 0) + session_count
            combined = set(existing_cat.get("examples", [])) | session_examples
            existing_cat["examples"] = sorted(combined)
        else:
            # Ensure only session-level count is kept
            new_cat["count"] = session_count
            new_cat["examples"] = sorted(session_examples)
            existing.append(new_cat)

    return existing


def categorize_session_errors(session_errors, existing_categories, grammar_tree):
    """
    Ask the LLM to place new session errors into existing categories (or make new ones).
    """

    if not session_errors:
        return existing_categories

    examples = "\n".join(f"- {k} (x{v})" for k, v in sorted(session_errors.items(), key=lambda x: -x[1]))
    existing = json.dumps(existing_categories, indent=2, ensure_ascii=False)
    grammar_tree_json = json.dumps(grammar_tree, indent=2, ensure_ascii=False)

    prompt = f"""
You are a Korean language tutor assistant. Below are errors made by a student during today's session.
Please help organize them by:
- Matching each to an existing category if possible (based on examples or label).
- Creating a new category only if no good match exists.

## Today's Errors:
{examples}

## Existing Category Labels Only:
{[cat['label'] for cat in existing_categories]}

## Curriculum Grammar Points (for reference — not mandatory):
{grammar_tree_json}

Return the updated full category list in this format:
{{
  "categories": [
    {{
      "label": "Politeness mismatch",
      "count": 4,
      "examples": ["used plain instead of polite", "missing 요-ending"]
    }},
    ...
  ]
}}
    """

    response = sanitize_json_string(chat([{"role": "user", "content": prompt}], temperature=0.2))
    try:
        return json.loads(response)["categories"]
    except Exception as e:
        print("⚠️ Failed to parse session error categorization response:", e)
        return existing_categories


def summarize_common_errors(error_dict):
    """
    Send the full common_errors dictionary to the LLM and receive grouped categories.
    Each category includes a label, frequency, and representative examples.
    """

    if not error_dict:
        return []

    # Build examples string for prompt
    examples = "\n".join(f"- {k} (x{v})" for k, v in sorted(error_dict.items(), key=lambda x: -x[1]))

    prompt = f"""
You are an intelligent assistant helping analyze Korean learner errors. Below is a list of raw error messages collected from their recent sessions, along with how many times each occurred.

Be sure to genralize! This list is important and will be used for further teaching of the user!

Your job is to:
- Group similar error messages into clear categories.
- For each category, provide:
  - A short label (in English)
  - Total frequency (sum of errors in this group)
  - A few representative examples

Here are the raw errors:
{examples}

Return JSON in this format:
{{
  "categories": [
    {{
      "label": "Politeness mismatch",
      "count": 7,
      "examples": ["used plain instead of polite verb", "..."]
    }},
    ...
  ]
}}
"""
    print(f' ==> [Line 62]: \033[38;2;234;242;89m[prompt]\033[0m({type(prompt).__name__}) = \033[38;2;59;236;212m{prompt}\033[0m')

    response = sanitize_json_string(chat([{"role": "user", "content": prompt}], temperature=0.2))
    print(f' ==> [Line 64]: \033[38;2;223;121;144m[response]\033[0m({type(response).__name__}) = \033[38;2;254;2;107m{response}\033[0m')

    try:
        return json.loads(response)["categories"]
    except Exception as e:
        print("⚠️ Could not parse LLM response:", e)
        return []

def sanitize_json_string(s):
    s = s.strip()

    # Remove <think>...</think> and anything before first {
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL)
    
    # Keep only content between first "{" and last "}"
    if "{" in s and "}" in s:
        start = s.find("{")
        end = s.rfind("}")
        s = s[start:end+1]

    s = s.replace('"', '"').replace('"', '"').replace("'", "'")
    return s