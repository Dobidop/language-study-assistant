"""
Enhanced Exercise Difficulty System for Language Learning

This module extends the existing exercise system with difficulty-based progression
and SRS integration for more effective learning.

Key Features:
1. Exercise difficulty ranking and progression
2. Grammar-specific difficulty tracking
3. SRS integration with exercise type progression
4. Adaptive difficulty selection based on mastery
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime, timedelta

class ExerciseDifficulty(Enum):
    """Exercise difficulty levels in ascending order"""
    RECOGNITION = 1      # Multiple choice, error correction
    GUIDED_PRODUCTION = 2  # Fill in blank (single)
    STRUCTURED_PRODUCTION = 3  # Fill multiple blanks, sentence building
    FREE_PRODUCTION = 4   # Translation, open-ended

    @classmethod
    def from_exercise_type(cls, exercise_type: str) -> 'ExerciseDifficulty':
        """Map exercise types to difficulty levels"""
        mapping = {
            'multiple_choice': cls.RECOGNITION,
            'error_correction': cls.RECOGNITION,
            'fill_in_blank': cls.GUIDED_PRODUCTION,
            'fill_multiple_blanks': cls.STRUCTURED_PRODUCTION,
            'sentence_building': cls.STRUCTURED_PRODUCTION,
            'translation': cls.FREE_PRODUCTION
        }
        return mapping.get(exercise_type, cls.GUIDED_PRODUCTION)

    def get_exercise_types(self) -> List[str]:
        """Get exercise types for this difficulty level"""
        mapping = {
            self.RECOGNITION: ['multiple_choice', 'error_correction'],
            self.GUIDED_PRODUCTION: ['fill_in_blank'],
            self.STRUCTURED_PRODUCTION: ['fill_multiple_blanks', 'sentence_building'],
            self.FREE_PRODUCTION: ['translation']
        }
        return mapping[self]


@dataclass
class GrammarDifficultyProgress:
    """Track difficulty progression for a specific grammar point"""
    grammar_id: str
    difficulty_mastery: Dict[ExerciseDifficulty, Dict] = None  # SRS data per difficulty
    current_max_difficulty: ExerciseDifficulty = ExerciseDifficulty.RECOGNITION
    unlocked_difficulties: List[ExerciseDifficulty] = None
    
    def __post_init__(self):
        if self.difficulty_mastery is None:
            self.difficulty_mastery = {}
        if self.unlocked_difficulties is None:
            self.unlocked_difficulties = [ExerciseDifficulty.RECOGNITION]


class DifficultyProgressionManager:
    """Manages exercise difficulty progression using SRS principles"""
    
    def __init__(self):
        # Mastery thresholds for advancing to next difficulty
        self.mastery_thresholds = {
            'min_reps': 3,              # Minimum SRS repetitions
            'min_accuracy': 0.8,        # 80% accuracy required
            'min_consecutive': 3,       # 3 consecutive correct
            'min_total_attempts': 5     # Minimum total attempts
        }
        
        # How long to wait before unlocking next difficulty
        self.unlock_delay_days = 1  # Wait 1 day after mastery before unlocking
    
    def get_grammar_difficulty_progress(self, profile: dict, grammar_id: str) -> GrammarDifficultyProgress:
        """Get or create difficulty progress for a grammar point"""
        
        # Check if we have difficulty tracking data
        difficulty_data = profile.get('grammar_difficulty_progress', {}).get(grammar_id)
        
        if difficulty_data:
            # Convert stored data back to progress object
            progress = GrammarDifficultyProgress(
                grammar_id=grammar_id,
                current_max_difficulty=ExerciseDifficulty(difficulty_data['current_max_difficulty']),
                unlocked_difficulties=[ExerciseDifficulty(d) for d in difficulty_data['unlocked_difficulties']]
            )
            
            # Reconstruct difficulty mastery data
            for diff_level, srs_data in difficulty_data.get('difficulty_mastery', {}).items():
                progress.difficulty_mastery[ExerciseDifficulty(int(diff_level))] = srs_data
                
            return progress
        else:
            # Create new progress starting at recognition level
            return GrammarDifficultyProgress(grammar_id=grammar_id)
    
    def is_difficulty_mastered(self, srs_data: dict) -> bool:
        """Check if a difficulty level is mastered for a grammar point"""
        if not srs_data:
            return False
            
        reps = srs_data.get('reps', 0)
        accuracy = srs_data.get('recent_accuracy', 0.0)
        consecutive = srs_data.get('consecutive_correct', 0)
        attempts = srs_data.get('total_attempts', 0)
        
        return (
            reps >= self.mastery_thresholds['min_reps'] and
            accuracy >= self.mastery_thresholds['min_accuracy'] and
            consecutive >= self.mastery_thresholds['min_consecutive'] and
            attempts >= self.mastery_thresholds['min_total_attempts']
        )
    
    def can_unlock_next_difficulty(self, progress: GrammarDifficultyProgress) -> bool:
        """Check if the next difficulty level can be unlocked"""
        current_max = progress.current_max_difficulty
        
        # Check if there's a next level
        try:
            next_difficulty = ExerciseDifficulty(current_max.value + 1)
        except ValueError:
            return False  # Already at max difficulty
        
        # Check if current level is mastered
        current_srs_data = progress.difficulty_mastery.get(current_max, {})
        if not self.is_difficulty_mastered(current_srs_data):
            return False
        
        # Check if enough time has passed since mastery
        last_mastered = current_srs_data.get('mastery_date')
        if last_mastered:
            mastery_date = datetime.fromisoformat(last_mastered).date()
            days_since_mastery = (datetime.now().date() - mastery_date).days
            if days_since_mastery < self.unlock_delay_days:
                return False
        
        return True
    
    def unlock_next_difficulty(self, progress: GrammarDifficultyProgress) -> bool:
        """Unlock the next difficulty level if conditions are met"""
        if not self.can_unlock_next_difficulty(progress):
            return False
        
        try:
            next_difficulty = ExerciseDifficulty(progress.current_max_difficulty.value + 1)
            progress.current_max_difficulty = next_difficulty
            if next_difficulty not in progress.unlocked_difficulties:
                progress.unlocked_difficulties.append(next_difficulty)
            return True
        except ValueError:
            return False
    
    def select_appropriate_difficulty(self, progress: GrammarDifficultyProgress, 
                                    preferred_difficulty: Optional[ExerciseDifficulty] = None) -> ExerciseDifficulty:
        """Select the most appropriate difficulty for practice"""
        
        # Try to unlock next difficulty if possible
        self.unlock_next_difficulty(progress)
        
        # If user has a preference and it's unlocked, use it
        if preferred_difficulty and preferred_difficulty in progress.unlocked_difficulties:
            return preferred_difficulty
        
        # Find the best difficulty to practice
        for difficulty in reversed(progress.unlocked_difficulties):
            srs_data = progress.difficulty_mastery.get(difficulty, {})
            
            # If this difficulty needs review or isn't mastered, practice it
            if not self.is_difficulty_mastered(srs_data):
                return difficulty
            
            # Check if it's due for review
            next_review = srs_data.get('next_review_date')
            if next_review:
                review_date = datetime.fromisoformat(next_review).date()
                if review_date <= datetime.now().date():
                    return difficulty
        
        # Default to current max difficulty for maintenance
        return progress.current_max_difficulty
    
    def get_exercise_type_for_difficulty(self, difficulty: ExerciseDifficulty, 
                                       user_preferences: List[str] = None) -> str:
        """Get a suitable exercise type for the given difficulty"""
        available_types = difficulty.get_exercise_types()
        
        # Filter by user preferences if provided
        if user_preferences:
            preferred_types = [t for t in available_types if t in user_preferences]
            if preferred_types:
                available_types = preferred_types
        
        # For now, return the first available type
        # Could be enhanced with randomization or rotation
        return available_types[0] if available_types else 'fill_in_blank'
    
    def update_difficulty_progress(self, profile: dict, grammar_id: str, 
                                 exercise_type: str, is_correct: bool) -> dict:
        """Update difficulty progress after an exercise attempt"""
        
        difficulty = ExerciseDifficulty.from_exercise_type(exercise_type)
        progress = self.get_grammar_difficulty_progress(profile, grammar_id)
        
        # Initialize SRS data for this difficulty if needed
        if difficulty not in progress.difficulty_mastery:
            progress.difficulty_mastery[difficulty] = {
                'reps': 0,
                'ease_factor': 2.3,
                'interval': 1,
                'lapses': 0,
                'consecutive_correct': 0,
                'total_attempts': 0,
                'recent_accuracy': 0.0,
                'first_seen': datetime.now().date().isoformat(),
                'last_reviewed': datetime.now().date().isoformat()
            }
        
        # Update SRS data (reuse existing SM-2 logic)
        srs_data = progress.difficulty_mastery[difficulty]
        self._apply_sm2_difficulty(srs_data, is_correct)
        
        # Mark mastery date if just achieved
        if is_correct and self.is_difficulty_mastered(srs_data) and 'mastery_date' not in srs_data:
            srs_data['mastery_date'] = datetime.now().date().isoformat()
        
        # Save progress back to profile
        profile.setdefault('grammar_difficulty_progress', {})[grammar_id] = {
            'current_max_difficulty': progress.current_max_difficulty.value,
            'unlocked_difficulties': [d.value for d in progress.unlocked_difficulties],
            'difficulty_mastery': {
                str(d.value): data for d, data in progress.difficulty_mastery.items()
            }
        }
        
        return profile
    
    def _apply_sm2_difficulty(self, srs_data: dict, correct: bool) -> None:
        """Apply SM-2 algorithm specifically for difficulty progression"""
        # This is a simplified version - you could reuse your existing SM-2 implementation
        srs_data['total_attempts'] += 1
        
        if correct:
            srs_data['consecutive_correct'] += 1
            srs_data['reps'] += 1
        else:
            srs_data['consecutive_correct'] = 0
            srs_data['lapses'] += 1
        
        # Calculate recent accuracy
        total_attempts = srs_data['total_attempts']
        if total_attempts > 0:
            recent_window = min(total_attempts, 8)
            srs_data['recent_accuracy'] = min(1.0, srs_data['consecutive_correct'] / recent_window)
        
        # Set next review date (simplified)
        interval = max(1, srs_data['reps'])
        srs_data['next_review_date'] = (datetime.now().date() + timedelta(days=interval)).isoformat()
        srs_data['last_reviewed'] = datetime.now().date().isoformat()
    
    def get_difficulty_summary(self, profile: dict, grammar_id: str) -> dict:
        """Get a summary of difficulty progression for a grammar point"""
        progress = self.get_grammar_difficulty_progress(profile, grammar_id)
        
        summary = {
            'grammar_id': grammar_id,
            'current_max_difficulty': progress.current_max_difficulty.name,
            'unlocked_difficulties': [d.name for d in progress.unlocked_difficulties],
            'mastery_by_difficulty': {},
            'can_unlock_next': self.can_unlock_next_difficulty(progress)
        }
        
        for difficulty in ExerciseDifficulty:
            if difficulty in progress.difficulty_mastery:
                srs_data = progress.difficulty_mastery[difficulty]
                summary['mastery_by_difficulty'][difficulty.name] = {
                    'is_mastered': self.is_difficulty_mastered(srs_data),
                    'reps': srs_data.get('reps', 0),
                    'accuracy': srs_data.get('recent_accuracy', 0.0),
                    'consecutive_correct': srs_data.get('consecutive_correct', 0)
                }
            else:
                summary['mastery_by_difficulty'][difficulty.name] = {
                    'is_mastered': False,
                    'reps': 0,
                    'accuracy': 0.0,
                    'consecutive_correct': 0
                }
        
        return summary


# Integration functions for existing system

def integrate_with_exercise_generator(profile: dict, grammar_targets: list, 
                                    preferred_exercise_type: str = None) -> Tuple[str, ExerciseDifficulty]:
    """
    Integrate difficulty progression with exercise generation.
    Returns the recommended exercise type and difficulty level.
    """
    
    manager = DifficultyProgressionManager()
    
    # Find the grammar point that needs the most attention
    target_grammar = None
    target_difficulty = None
    
    for grammar_id in grammar_targets:
        progress = manager.get_grammar_difficulty_progress(profile, grammar_id)
        
        # Select appropriate difficulty for this grammar
        difficulty = manager.select_appropriate_difficulty(progress)
        
        # If this is a struggling grammar point, prioritize it
        current_srs = progress.difficulty_mastery.get(difficulty, {})
        if current_srs.get('consecutive_correct', 0) == 0:
            target_grammar = grammar_id
            target_difficulty = difficulty
            break
    
    # If no struggling grammar, use the first one
    if target_grammar is None and grammar_targets:
        target_grammar = grammar_targets[0]
        progress = manager.get_grammar_difficulty_progress(profile, target_grammar)
        target_difficulty = manager.select_appropriate_difficulty(progress)
    
    # Get appropriate exercise type for the difficulty
    if target_difficulty:
        user_prefs = profile.get('learning_preferences', {}).get('preferred_exercise_types', [])
        exercise_type = manager.get_exercise_type_for_difficulty(target_difficulty, user_prefs)
        
        # Override with user preference if specified and appropriate
        if preferred_exercise_type:
            pref_difficulty = ExerciseDifficulty.from_exercise_type(preferred_exercise_type)
            progress = manager.get_grammar_difficulty_progress(profile, target_grammar)
            if pref_difficulty in progress.unlocked_difficulties:
                exercise_type = preferred_exercise_type
                target_difficulty = pref_difficulty
        
        return exercise_type, target_difficulty
    
    # Fallback
    return preferred_exercise_type or 'fill_in_blank', ExerciseDifficulty.GUIDED_PRODUCTION


def update_profile_with_difficulty_progress(profile: dict, session_exercises: list) -> dict:
    """
    Update the user profile with difficulty progression after a session.
    Integrates with existing profile update logic.
    """
    
    manager = DifficultyProgressionManager()
    
    for exercise in session_exercises:
        grammar_focus = exercise.get('grammar_focus', [])
        exercise_type = exercise.get('exercise_type', 'fill_in_blank')
        is_correct = exercise.get('is_correct', False)
        
        # Update difficulty progress for each grammar point
        for grammar_id in grammar_focus:
            profile = manager.update_difficulty_progress(
                profile, grammar_id, exercise_type, is_correct
            )
    
    return profile


# Example usage and testing
if __name__ == '__main__':
    print("🧪 Testing Exercise Difficulty System...")
    
    # Create a sample profile
    test_profile = {
        'grammar_summary': {
            '-이에요_예요': {
                'reps': 5,
                'recent_accuracy': 0.9,
                'consecutive_correct': 4,
                'total_attempts': 8
            }
        }
    }
    
    manager = DifficultyProgressionManager()
    
    # Test progression for a grammar point
    grammar_id = '-이에요_예요'
    
    print(f"\n📊 Testing progression for {grammar_id}")
    
    # Simulate some exercises at different difficulties
    exercises = [
        ('multiple_choice', True),
        ('multiple_choice', True),
        ('multiple_choice', True),
        ('fill_in_blank', False),
        ('fill_in_blank', True),
        ('fill_in_blank', True),
    ]
    
    for exercise_type, is_correct in exercises:
        difficulty = ExerciseDifficulty.from_exercise_type(exercise_type)
        print(f"  {exercise_type} ({difficulty.name}): {'✅' if is_correct else '❌'}")
        
        test_profile = manager.update_difficulty_progress(
            test_profile, grammar_id, exercise_type, is_correct
        )
    
    # Show final summary
    summary = manager.get_difficulty_summary(test_profile, grammar_id)
    print(f"\n📈 Final Summary for {grammar_id}:")
    print(f"  Max difficulty: {summary['current_max_difficulty']}")
    print(f"  Unlocked: {summary['unlocked_difficulties']}")
    print(f"  Can unlock next: {summary['can_unlock_next']}")
    
    for diff_name, mastery_info in summary['mastery_by_difficulty'].items():
        status = "✅ Mastered" if mastery_info['is_mastered'] else "🔄 Learning"
        print(f"  {diff_name}: {status} (reps: {mastery_info['reps']}, acc: {mastery_info['accuracy']:.1%})")
    
    # Test exercise selection
    print(f"\n🎯 Exercise Selection Test:")
    exercise_type, difficulty = integrate_with_exercise_generator(
        test_profile, [grammar_id]
    )
    print(f"  Recommended: {exercise_type} ({difficulty.name})")
    
    print(f"\n✅ Difficulty system testing complete!")
