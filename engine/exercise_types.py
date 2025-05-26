"""
Modular Exercise Types System

This module provides a flexible, extensible system for generating different types of language exercises.
Each exercise type has its own prompt template, validation rules, and formatting logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import json
import random
from dataclasses import dataclass


@dataclass
class ExerciseConfig:
    """Configuration for exercise generation"""
    user_profile: Dict[str, Any]
    grammar_targets: List[str]
    vocab_new: List[str]
    vocab_familiar: List[str]
    vocab_core: List[str]
    grammar_maturity_section: str
    recent_exercises: Optional[List[Dict]] = None


class BaseExerciseType(ABC):
    """Base class for all exercise types"""
    
    def __init__(self):
        self.exercise_type = self.__class__.__name__.lower().replace('exercise', '')
        self.difficulty = "medium"  # Override in subclasses
    
    @abstractmethod
    def generate_prompt(self, config: ExerciseConfig) -> str:
        """Generate the LLM prompt for this exercise type"""
        pass
    
    @abstractmethod
    def get_response_schema(self) -> Dict[str, str]:
        """Return the expected JSON schema for LLM response"""
        pass
    
    @abstractmethod
    def validate_exercise(self, exercise: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate generated exercise. Returns (is_valid, error_messages)"""
        pass
    
    def get_common_prompt_sections(self, config: ExerciseConfig) -> Dict[str, str]:
        """Get common prompt sections shared across exercise types"""
        target_lang = config.user_profile.get('target_language', 'Korean')
        native_lang = config.user_profile.get('native_language', 'English')
        instruction_lang = config.user_profile.get('instruction_language', 'English')
        task_lang = config.user_profile.get('task_language', target_lang)
        level = config.user_profile.get('level', 'beginner')
        formality = config.user_profile.get('learning_preferences', {}).get('preferred_formality', 'polite')
        
        grammar_points_formatted = "\n" + "\n".join(f"- {g}" for g in config.grammar_targets)
        
        return {
            'target_lang': target_lang,
            'native_lang': native_lang,
            'instruction_lang': instruction_lang,
            'task_lang': task_lang,
            'level': level,
            'formality': formality,
            'grammar_points': grammar_points_formatted,
            'grammar_maturity': config.grammar_maturity_section,
            'vocab_core': config.vocab_core,
            'vocab_familiar': config.vocab_familiar,
            'vocab_new': config.vocab_new,
            'recent_exercises': self._format_recent_exercises(config.recent_exercises)
        } # type: ignore
    
    def _format_recent_exercises(self, recent_exercises: Optional[List[Dict]]) -> str:
        """Format recent exercises for prompt inclusion"""
        if not recent_exercises:
            return "None"
        
        formatted = []
        for idx, ex in enumerate(recent_exercises[-5:], 1):
            formatted.append(f"- Exercise {idx}: {ex.get('exercise_type', 'unknown')}")
            formatted.append(f"  Prompt: {ex.get('prompt', 'N/A')}")
            formatted.append(f"  Result: {'correct' if ex.get('is_correct') else 'incorrect'}")
        
        return "\n".join(formatted)


class FillInBlankExercise(BaseExerciseType):
    """Single fill-in-the-blank exercise"""
    
    def __init__(self):
        super().__init__()
        self.difficulty = "easy"
    
    def generate_prompt(self, config: ExerciseConfig) -> str:
        sections = self.get_common_prompt_sections(config)
        
        return f"""/no_think
You are a {sections['target_lang']} language tutor assistant. Create a fill-in-the-blank exercise.

## User Profile:
- Proficiency: {sections['level']}
- Native language: {sections['native_lang']}
- Target language: {sections['target_lang']}
- Instructions in: {sections['instruction_lang']}
- Exercise language: {sections['task_lang']}
- Formality level: {sections['formality']} (VERY IMPORTANT!)

## Exercise Requirements:
- Exercise type: "fill_in_blank"
- Must have exactly ONE blank marked as ___
- Target these grammar points: {sections['grammar_points']}
- The blank must test one of the target grammar points
- Use {sections['formality']} formality level

## Critical Spacing Rules:
- If the answer includes particles (을/를, 이/가, etc.), blank the ENTIRE word including particle
- Correct: 저는 ___ 마셔요 (answer: 소주를)
- Incorrect: 저는 ___를 마셔요 (answer: 소주)
- No space between blank and adjacent characters when they should be connected
- The filled sentence must make grammatical sense

## Vocabulary Guidelines:
- Core vocabulary (use freely): {sections['vocab_core']}
- Familiar vocabulary (use some): {sections['vocab_familiar']}
- New vocabulary (use 1-2 max): {sections['vocab_new']}

## Grammar Maturity:
{sections['grammar_maturity']}

## Recent Session History:
{sections['recent_exercises']}
Avoid repeating similar patterns.

## Response Format:
Return ONLY a valid JSON object:
{{
  "exercise_type": "fill_in_blank",
  "prompt": "Korean sentence with exactly one ___",
  "expected_answer": "the word/phrase that fills the blank",
  "filled_sentence": "complete sentence with blank filled in",
  "glossary": {{"term": "definition in {sections['instruction_lang']}"}},
  "translated_sentence": "filled_sentence translated to {sections['instruction_lang']}",
  "grammar_focus": ["target grammar IDs"]
}}

Generate exactly one exercise. Make it meaningful and test the target grammar effectively."""
    
    def get_response_schema(self) -> Dict[str, str]:
        return {
            "exercise_type": "string",
            "prompt": "string (with exactly one ___)",
            "expected_answer": "string",
            "filled_sentence": "string",
            "glossary": "object",
            "translated_sentence": "string",
            "grammar_focus": "array"
        }
    
    def validate_exercise(self, exercise: Dict[str, Any]) -> tuple[bool, List[str]]:
        errors = []
        
        # Check required fields
        required_fields = ['prompt', 'expected_answer', 'filled_sentence', 'glossary', 'grammar_focus']
        for field in required_fields:
            if field not in exercise:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return False, errors
        
        # Check blank count
        blank_count = exercise['prompt'].count('___')
        if blank_count != 1:
            errors.append(f"Expected exactly 1 blank, found {blank_count}")
        
        # Check that answer fits the blank
        prompt = exercise['prompt']
        answer = exercise['expected_answer']
        filled = exercise['filled_sentence']
        
        expected_filled = prompt.replace('___', answer)
        if expected_filled.strip() != filled.strip():
            errors.append(f"Filled sentence doesn't match prompt + answer")
        
        # Check for common spacing issues
        if '__ ' in prompt or ' __' in prompt:
            errors.append("Spacing issue detected around blank")
        
        return len(errors) == 0, errors


class FillMultipleBlanksExercise(BaseExerciseType):
    """Multiple fill-in-the-blank exercise"""
    
    def __init__(self):
        super().__init__()
        self.difficulty = "medium"
    
    def generate_prompt(self, config: ExerciseConfig) -> str:
        sections = self.get_common_prompt_sections(config)
        
        return f"""/no_think
You are a {sections['target_lang']} language tutor assistant. Create a multiple fill-in-the-blank exercise.

## User Profile:
- Proficiency: {sections['level']}
- Formality level: {sections['formality']} (VERY IMPORTANT!)

## Exercise Requirements:
- Exercise type: "fill_multiple_blanks"
- Must have exactly 2-3 blanks marked as ___
- Each blank should test different grammar points from: {sections['grammar_points']}
- Use {sections['formality']} formality level

## Critical Rules:
- Each blank tests a specific grammar concept
- Blanks should be related but test different aspects
- Expected answers should be a list in order of appearance
- Apply same spacing rules as single blank exercises

## Vocabulary: Core: {sections['vocab_core']}, Familiar: {sections['vocab_familiar']}, New: {sections['vocab_new']}
## Grammar Maturity: {sections['grammar_maturity']}
## Recent History: {sections['recent_exercises']}

## Response Format:
{{
  "exercise_type": "fill_multiple_blanks",
  "prompt": "Korean sentence with 2-3 ___ blanks",
  "expected_answer": ["answer1", "answer2", "answer3"],
  "filled_sentence": "complete sentence with all blanks filled",
  "glossary": {{"term": "definition"}},
  "translated_sentence": "translation",
  "grammar_focus": ["grammar IDs for each blank"]
}}"""
    
    def get_response_schema(self) -> Dict[str, str]:
        return {
            "exercise_type": "string",
            "prompt": "string (with 2-3 ___)",
            "expected_answer": "array of strings",
            "filled_sentence": "string",
            "glossary": "object",
            "translated_sentence": "string", 
            "grammar_focus": "array"
        }
    
    def validate_exercise(self, exercise: Dict[str, Any]) -> tuple[bool, List[str]]:
        errors = []
        
        # Check blank count
        blank_count = exercise.get('prompt', '').count('___')
        if blank_count < 2 or blank_count > 3:
            errors.append(f"Expected 2-3 blanks, found {blank_count}")
        
        # Check answer count matches blank count  
        answers = exercise.get('expected_answer', [])
        if len(answers) != blank_count:
            errors.append(f"Answer count ({len(answers)}) doesn't match blank count ({blank_count})")
        
        return len(errors) == 0, errors


class MultipleChoiceExercise(BaseExerciseType):
    """Multiple choice exercise"""
    
    def __init__(self):
        super().__init__()
        self.difficulty = "easy"
    
    def generate_prompt(self, config: ExerciseConfig) -> str:
        sections = self.get_common_prompt_sections(config)
        
        return f"""/no_think
You are a {sections['target_lang']} language tutor assistant. Create a multiple choice exercise.

## User Profile:
- Proficiency: {sections['level']}
- Formality level: {sections['formality']} (VERY IMPORTANT!)

## Exercise Requirements:
- Exercise type: "multiple_choice"
- Create a sentence with one blank ___
- Provide 4 answer choices (A, B, C, D)
- Only one choice should be correct
- Wrong answers should be plausible but grammatically incorrect
- Test these grammar points: {sections['grammar_points']}

## Vocabulary: Core: {sections['vocab_core']}, Familiar: {sections['vocab_familiar']}, New: {sections['vocab_new']}
## Grammar Maturity: {sections['grammar_maturity']}
## Recent History: {sections['recent_exercises']}

## Response Format:
{{
  "exercise_type": "multiple_choice",
  "prompt": "Korean sentence with one ___",
  "choices": {{
    "A": "choice 1",
    "B": "choice 2", 
    "C": "choice 3",
    "D": "choice 4"
  }},
  "correct_answer": "A",
  "expected_answer": "the correct choice text",
  "filled_sentence": "complete sentence with correct answer",
  "explanation": "why this answer is correct in {sections['instruction_lang']}",
  "glossary": {{"term": "definition"}},
  "translated_sentence": "translation",
  "grammar_focus": ["grammar IDs"]
}}"""
    
    def get_response_schema(self) -> Dict[str, str]:
        return {
            "exercise_type": "string",
            "prompt": "string (with ___)",
            "choices": "object with A,B,C,D keys",
            "correct_answer": "string (A,B,C,or D)",
            "expected_answer": "string",
            "filled_sentence": "string",
            "explanation": "string",
            "glossary": "object",
            "translated_sentence": "string",
            "grammar_focus": "array"
        }
    
    def validate_exercise(self, exercise: Dict[str, Any]) -> tuple[bool, List[str]]:
        errors = []
        
        # Check choices
        choices = exercise.get('choices', {})
        if set(choices.keys()) != {'A', 'B', 'C', 'D'}:
            errors.append("Choices must have exactly keys A, B, C, D")
        
        # Check correct answer is valid
        correct = exercise.get('correct_answer', '')
        if correct not in ['A', 'B', 'C', 'D']:
            errors.append("correct_answer must be A, B, C, or D")
        
        return len(errors) == 0, errors


class ErrorCorrectionExercise(BaseExerciseType):
    """Select the grammatically correct sentence"""
    
    def __init__(self):
        super().__init__()
        self.difficulty = "hard"
    
    def generate_prompt(self, config: ExerciseConfig) -> str:
        sections = self.get_common_prompt_sections(config)
        
        return f"""/no_think
You are a {sections['target_lang']} language tutor assistant. Create an error correction exercise.

## Exercise Requirements:
- Exercise type: "error_correction"
- Create 4 similar sentences (A, B, C, D)
- Only ONE sentence should be completely correct
- Others should have subtle grammar mistakes related to: {sections['grammar_points']}
- Mistakes should be realistic learner errors
- Use {sections['formality']} formality level

## Response Format:
{{
  "exercise_type": "error_correction",
  "prompt": "Choose the grammatically correct sentence:",
  "sentences": {{
    "A": "sentence with error",
    "B": "correct sentence",
    "C": "sentence with error", 
    "D": "sentence with error"
  }},
  "correct_answer": "B",
  "expected_answer": "the correct sentence text",
  "error_explanations": {{
    "A": "explanation of error",
    "C": "explanation of error",
    "D": "explanation of error"
  }},
  "glossary": {{"term": "definition"}},
  "translated_sentence": "correct sentence translation",
  "grammar_focus": ["grammar IDs"]
}}"""
    
    def get_response_schema(self) -> Dict[str, str]:
        return {
            "exercise_type": "string",
            "prompt": "string",
            "sentences": "object with A,B,C,D keys",
            "correct_answer": "string",
            "expected_answer": "string",
            "error_explanations": "object",
            "glossary": "object", 
            "translated_sentence": "string",
            "grammar_focus": "array"
        }
    
    def validate_exercise(self, exercise: Dict[str, Any]) -> tuple[bool, List[str]]:
        errors = []
        
        sentences = exercise.get('sentences', {})
        if set(sentences.keys()) != {'A', 'B', 'C', 'D'}:
            errors.append("Sentences must have exactly keys A, B, C, D")
        
        return len(errors) == 0, errors


class SentenceBuildingExercise(BaseExerciseType):
    """Arrange words/phrases in correct order"""
    
    def __init__(self):
        super().__init__()
        self.difficulty = "medium"
    
    def generate_prompt(self, config: ExerciseConfig) -> str:
        sections = self.get_common_prompt_sections(config)
        
        return f"""/no_think
Create a sentence building exercise where the user arranges Korean words/phrases in correct order.

## Exercise Requirements:
- Exercise type: "sentence_building"  
- Provide 5-7 Korean words/phrases in random order
- User must arrange them to form a grammatically correct sentence
- Test grammar points: {sections['grammar_points']}
- Use {sections['formality']} formality level

## Response Format:
{{
  "exercise_type": "sentence_building",
  "prompt": "Arrange these words to form a correct sentence:",
  "word_pieces": ["word1", "word2", "word3", "word4", "word5"],
  "expected_answer": ["word2", "word1", "word4", "word5", "word3"],
  "filled_sentence": "correct sentence formed by arranging pieces",
  "glossary": {{"term": "definition"}},
  "translated_sentence": "translation",
  "grammar_focus": ["grammar IDs"]
}}"""
    
    def get_response_schema(self) -> Dict[str, str]:
        return {
            "exercise_type": "string",
            "prompt": "string",
            "word_pieces": "array of strings",
            "expected_answer": "array of strings (correct order)",
            "filled_sentence": "string",
            "glossary": "object",
            "translated_sentence": "string",
            "grammar_focus": "array"
        }
    
    def validate_exercise(self, exercise: Dict[str, Any]) -> tuple[bool, List[str]]:
        errors = []
        
        pieces = exercise.get('word_pieces', [])
        answer = exercise.get('expected_answer', [])
        
        if set(pieces) != set(answer):
            errors.append("Expected answer must contain same words as word_pieces")
        
        return len(errors) == 0, errors


class TranslationExercise(BaseExerciseType):
    """Translation exercise from instruction language to target language"""
    
    def __init__(self):
        super().__init__()
        self.difficulty = "medium"
    
    def generate_prompt(self, config: ExerciseConfig) -> str:
        sections = self.get_common_prompt_sections(config)
        
        return f"""/no_think
You are a {sections['target_lang']} language tutor assistant. Create a translation exercise.

## User Profile:
- Proficiency: {sections['level']}
- Native language: {sections['native_lang']}
- Target language: {sections['target_lang']}
- Instructions in: {sections['instruction_lang']}
- Formality level: {sections['formality']} (VERY IMPORTANT!)

## Exercise Requirements:
- Exercise type: "translation"
- Provide a sentence in {sections['instruction_lang']} for the user to translate into {sections['target_lang']}
- Target these grammar points: {sections['grammar_points']}
- Use {sections['formality']} formality level in the expected translation
- Sentence should be at {sections['level']} difficulty level

## Vocabulary Guidelines:
- Core vocabulary (use freely): {sections['vocab_core']}
- Familiar vocabulary (use some): {sections['vocab_familiar']}
- New vocabulary (use 1-2 max): {sections['vocab_new']}

## Grammar Maturity:
{sections['grammar_maturity']}

## Recent Session History:
{sections['recent_exercises']}
Avoid repeating similar patterns.

## Response Format:
Return ONLY a valid JSON object:
{{
  "exercise_type": "translation",
  "prompt": "{sections['instruction_lang']} sentence to translate",
  "expected_answer": "correct {sections['target_lang']} translation",
  "filled_sentence": "same as expected_answer",
  "glossary": {{"term": "definition in {sections['instruction_lang']}"}},
  "translated_sentence": "same as prompt",
  "grammar_focus": ["target grammar IDs"]
}}

Generate exactly one translation exercise that effectively tests the target grammar points."""
    
    def get_response_schema(self) -> Dict[str, str]:
        return {
            "exercise_type": "string",
            "prompt": "string (sentence to translate)",
            "expected_answer": "string (correct translation)",
            "filled_sentence": "string (same as expected_answer)",
            "glossary": "object",
            "translated_sentence": "string (same as prompt)",
            "grammar_focus": "array"
        }
    
    def validate_exercise(self, exercise: Dict[str, Any]) -> tuple[bool, List[str]]:
        errors = []
        
        # Check required fields
        required_fields = ['prompt', 'expected_answer', 'filled_sentence', 'glossary', 'grammar_focus', 'translated_sentence']
        for field in required_fields:
            if field not in exercise:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return False, errors
        
        # For translation exercises, filled_sentence should be same as expected_answer
        expected = exercise.get('expected_answer', '').strip()
        filled = exercise.get('filled_sentence', '').strip()
        if expected != filled:
            errors.append("For translation exercises, filled_sentence should match expected_answer")
        
        # Translated_sentence should be same as prompt (since it's already in instruction language)
        prompt = exercise.get('prompt', '').strip()
        translated = exercise.get('translated_sentence', '').strip()
        if prompt != translated:
            errors.append("For translation exercises, translated_sentence should match prompt")
        
        # Check that prompt and expected_answer are in different languages
        # This is a basic check - could be more sophisticated
        if exercise.get('prompt', '') == exercise.get('expected_answer', ''):
            errors.append("Prompt and expected answer appear to be identical - check language difference")
        
        return len(errors) == 0, errors


class ExerciseTypeFactory:
    """Factory for creating exercise type instances"""
    
    _exercise_types = {
        'fill_in_blank': FillInBlankExercise,
        'fill_multiple_blanks': FillMultipleBlanksExercise,
        'multiple_choice': MultipleChoiceExercise,
        'error_correction': ErrorCorrectionExercise,
        'sentence_building': SentenceBuildingExercise,
        'translation': TranslationExercise,  # Now using modular system
    }
    
    @classmethod
    def create_exercise_type(cls, exercise_type: str) -> BaseExerciseType:
        """Create an instance of the specified exercise type"""
        if exercise_type not in cls._exercise_types:
            raise ValueError(f"Unknown exercise type: {exercise_type}")
        
        exercise_class = cls._exercise_types[exercise_type]
        if exercise_class is None:
            raise ValueError(f"Exercise type {exercise_type} not yet implemented in new system")
        
        return exercise_class()
    
    @classmethod
    def get_available_types(cls) -> List[str]:
        """Get list of available exercise types"""
        return [t for t, cls_ref in cls._exercise_types.items() if cls_ref is not None]
    
    @classmethod
    def get_type_info(cls) -> Dict[str, Dict[str, Any]]:
        """Get information about all exercise types"""
        info = {}
        for type_name, type_class in cls._exercise_types.items():
            if type_class is not None:
                instance = type_class()
                info[type_name] = {
                    'difficulty': instance.difficulty,
                    'class_name': type_class.__name__
                }
        return info


def generate_exercise_with_type(exercise_type: str, config: ExerciseConfig) -> Dict[str, Any]:
    """
    Generate an exercise using the new modular system.
    
    Args:
        exercise_type: Type of exercise to generate
        config: Exercise configuration
        
    Returns:
        Generated exercise dictionary
    """
    # Create exercise type instance
    exercise_generator = ExerciseTypeFactory.create_exercise_type(exercise_type)
    
    # Generate prompt
    prompt = exercise_generator.generate_prompt(config)
    
    # Return prompt and metadata for LLM call
    return {
        'prompt': prompt,
        'exercise_type': exercise_type,
        'schema': exercise_generator.get_response_schema(),
        'validator': exercise_generator.validate_exercise,
        'difficulty': exercise_generator.difficulty
    }