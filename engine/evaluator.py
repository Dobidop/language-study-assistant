import json
from engine.llm_client import chat
from engine.generator import sanitize_json_string

def evaluate_answer(prompt, user_answer, expected_answer, grammar_focus, target_language="Korean"):
    """
    Send user answer to GPT along with prompt and expected answer for structured feedback.
    """

    evaluation_prompt = f"""/no_think
You are a {target_language} language tutor assistant.
Evaluate the user's answer to a language exercise and explain any mistakes.

## Exercise:
Prompt (note that this might contain a missplaced space between '___' and a word/particle!): {prompt}
Expected answer: {expected_answer}
User answer: {user_answer}

Be sure to take into account the potential prompt formatting issue when evaluating the result.
If this seems to be the case, then mark the question as correct ("is_correct": true)

## Instructions:
Return your evaluation in the following JSON format:

{{
  "is_correct": true/false,
  "corrected_answer": "...",
  "error_analysis": ["...", "..."],
  "grammar_focus": {grammar_focus},
  "explanation_summary": "..."
}}
    """

    print(f' ==> [Line 10]: \033[38;2;15;179;254m[evaluation_prompt]\033[0m({type(evaluation_prompt).__name__}) = \033[38;2;73;189;127m{evaluation_prompt}\033[0m')

    response_text = chat(
        messages=[
            {"role": "system", "content": f"""You are a helpful {target_language} tutor assistant."""},
            {"role": "user", "content": evaluation_prompt.strip()}
        ],
        temperature=0.2
    )

    print(f' ==> [Line 39]: \033[38;2;24;247;188m[response_text]\033[0m({type(response_text).__name__}) = \033[38;2;243;132;71m{response_text}\033[0m')
    
    try:
        return json.loads(sanitize_json_string(response_text))
    except json.JSONDecodeError:
        print("⚠️ GPT response was not valid JSON:")
        print(response_text)
        return {
            "is_correct": False,
            "corrected_answer": expected_answer,
            "error_analysis": ["Could not parse GPT response."],
            "grammar_focus": grammar_focus,
            "explanation_summary": "GPT response was invalid."
        }

def build_filled_sentence(prompt: str, user_response: str | list[str]) -> str:
    if isinstance(user_response, str):
        return prompt.replace("___", user_response, 1)
    elif isinstance(user_response, list):
        filled = prompt
        for fill in user_response:
            filled = filled.replace("___", fill, 1)
        return filled
    return prompt
