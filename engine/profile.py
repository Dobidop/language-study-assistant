import json
from datetime import datetime, timedelta
from pathlib import Path
from engine.utils import normalize_grammar_id
import re
import shutil
import sys
import os
from pathlib import Path

# Constants for SM-2 algorithm - MORE CONSERVATIVE
MIN_EASE_FACTOR = 1.3
INITIAL_EASE = 2.5
# More conservative intervals with additional early steps
INITIAL_INTERVALS = [1, 2, 4, 8]  # Extended from [1, 6] to have more repetition early on
MAX_INTERVAL = 120  # Reduced from 180 to 120 days (4 months max)
MAX_EASE_FACTOR = 2.8  # Reduced from 3.0 to prevent too-rapid advancement

DEFAULT_PROFILE = {
  "user_id": "user_001",
  "user_level": "beginner",
  "level": "beginner",
  "native_language": "English",
  "target_language": "Korean",
  "instruction_language": "English",
  "task_language": "Korean",
  "session_tracking": {
    "last_session_date": "",
    "exercises_completed": 0,
    "correct_ratio_last_10": 0.0,
    "grammar_points_seen": []
  },
  "learning_preferences": {
    "preferred_formality": "polite informal",
    "max_new_words_per_session": 2,
    "preferred_exercise_types": ["fill_in_blank", "translation"],
    "prefers_korean_prompts": False,
    "allow_open_tasks": True,
    "reviews_per_session": 15,  # Increased from 10
    "new_grammar_per_session": 1,  # Reduced from 2
    "new_vocab_per_session": 3,   # Reduced from 5
    # NEW: Mastery-related preferences
    "grammar_mastery_threshold": 0.75,  # 75% accuracy needed for mastery
    "min_exposures_before_new": 5,      # Minimum exposures before introducing new grammar
    "min_consecutive_correct": 3,       # Consecutive correct answers needed
    "mastery_focus": True               # Prioritize mastery over speed
  },
  "grammar_summary": {},
  "vocab_summary": {}
}


def load_user_profile(path: str) -> dict:
    """
    Load user profile with automatic grammar ID migration.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
        
        # Perform automatic migration
        migrated_profile, migration_performed, migration_log = migrate_grammar_profile_data(profile)
        
        if migration_performed:
            print(f"🔄 Auto-migrated {len(migration_log)} grammar ID changes in profile")
            print(f"   Details: {migration_log[:3]}{'...' if len(migration_log) > 3 else ''}")
            
            # Save the migrated profile back to disk
            save_user_profile(migrated_profile, path)
            print(f"💾 Saved migrated profile to {path}")
        
        return migrated_profile
        
    except FileNotFoundError:
        # first-run: write out a blank/default profile
        save_user_profile(DEFAULT_PROFILE, path)
        # make sure we return a fresh copy
        return DEFAULT_PROFILE.copy()


def save_user_profile(profile: dict, path: str = 'user_profile.json') -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

# Add migration functionality
def migrate_grammar_profile_data(profile: dict) -> tuple:
    """
    Migrate existing profile to use consistent grammar IDs.
    This is called automatically when loading profiles.
    
    Returns:
        tuple: (updated_profile, migration_performed, migration_log)
    """
    migration_log = []
    migration_performed = False
    
    if 'grammar_summary' not in profile:
        return profile, migration_performed, migration_log
    
    old_grammar_summary = profile['grammar_summary'].copy()
    new_grammar_summary = {}
    
    for old_id, data in old_grammar_summary.items():
        new_id = normalize_grammar_id(old_id)
        
        if old_id != new_id:
            migration_performed = True
            migration_log.append(f"Migrated: '{old_id}' -> '{new_id}'")
            
            # If the new_id already exists, merge the data intelligently
            if new_id in new_grammar_summary:
                migration_log.append(f"Merging duplicate: '{new_id}'")
                # Keep the data with more repetitions (more advanced SRS state)
                existing_data = new_grammar_summary[new_id]
                if data.get('reps', 0) > existing_data.get('reps', 0):
                    new_grammar_summary[new_id] = data
                    migration_log.append(f"  Used data from '{old_id}' (more reps: {data.get('reps', 0)})")
                else:
                    migration_log.append(f"  Kept existing data (more reps: {existing_data.get('reps', 0)})")
            else:
                new_grammar_summary[new_id] = data
        else:
            # ID was already normalized
            new_grammar_summary[new_id] = data
    
    profile['grammar_summary'] = new_grammar_summary
    
    # Add migration metadata
    if migration_performed:
        profile.setdefault('_migration_history', []).append({
            'timestamp': datetime.now().isoformat(),
            'type': 'grammar_id_normalization',
            'changes': len(migration_log),
            'log': migration_log
        })
    
    return profile, migration_performed, migration_log

def _apply_sm2(item: dict, correct: bool) -> None:
    """
    Applies a MORE CONSERVATIVE SM-2 update to a single item (grammar or vocab).
    Mutates item in-place to update interval, ease_factor, srs_level, lapses, next_review_date.
    
    Changes from original:
    - More conservative intervals: [1, 2, 4, 8] instead of [1, 6]
    - Smaller ease factor adjustments
    - Track consecutive correct answers
    - Slower progression to prevent rushing
    """
    today = datetime.now().date()

    # Initialize fields if missing
    item.setdefault('ease_factor', INITIAL_EASE)
    item.setdefault('interval', INITIAL_INTERVALS[0])
    item.setdefault('reps', 0)
    item.setdefault('lapses', 0)
    item.setdefault('consecutive_correct', 0)  # NEW: Track consecutive correct
    item.setdefault('total_attempts', 0)      # NEW: Track total attempts
    item.setdefault('recent_accuracy', 0.0)   # NEW: Track recent performance

    # Update tracking metrics
    item['total_attempts'] += 1
    
    # Quality: high if correct, low if incorrect
    quality = 5 if correct else 2

    if correct:
        item['consecutive_correct'] += 1
    else:
        item['consecutive_correct'] = 0

    # Calculate recent accuracy (simple moving average of last 10 attempts)
    if item['total_attempts'] > 0:
        # Simplified accuracy calculation - in a real system you'd track recent attempts
        item['recent_accuracy'] = min(1.0, item.get('consecutive_correct', 0) / min(item['total_attempts'], 10))

    if quality < 3:
        # Failure: reset repetitions but less harshly
        item['reps'] = max(0, item['reps'] - 1)  # Only go back one step, don't reset to 0
        item['interval'] = INITIAL_INTERVALS[0]
        item['lapses'] += 1
        # Smaller ease factor penalty
        item['ease_factor'] = max(
            MIN_EASE_FACTOR,
            item['ease_factor'] - 0.15  # Reduced from 0.2 to 0.15
        )
        print(f"📉 Grammar item failed - reps: {item['reps']}, interval: {item['interval']} days")
    else:
        # Success: increment repetitions more conservatively
        item['reps'] += 1
        
        # Use extended initial intervals
        if item['reps'] <= len(INITIAL_INTERVALS):
            item['interval'] = INITIAL_INTERVALS[item['reps'] - 1]
            print(f"📈 Grammar item success - using fixed interval: {item['interval']} days (rep {item['reps']})")
        else:
            # From 5th repetition on, use ease factor but more conservatively
            # Apply a "brake" to prevent too-rapid advancement
            conservative_ease = min(item['ease_factor'], 2.2)  # Cap the ease factor
            new_interval = round(item['interval'] * conservative_ease)
            
            # Additional conservative constraint: never more than double the previous interval
            max_growth = item['interval'] * 2
            item['interval'] = min(new_interval, max_growth, MAX_INTERVAL)
            print(f"📈 Grammar item success - calculated interval: {item['interval']} days (ease: {conservative_ease:.2f})")
        
        # Smaller ease factor adjustments
        delta = (0.05 - (5 - quality) * (0.04 + (5 - quality) * 0.01))  # Reduced deltas
        new_ease = item['ease_factor'] + delta
        item['ease_factor'] = max(MIN_EASE_FACTOR, min(new_ease, MAX_EASE_FACTOR))

    item['srs_level'] = item['reps']
    # Schedule next review
    item['next_review_date'] = (today + timedelta(days=item['interval'])).isoformat()
    
    print(f"🔄 SRS Update: reps={item['reps']}, interval={item['interval']}d, ease={item['ease_factor']:.2f}, next={item['next_review_date']}")


def fix_corrupted_srs_data(profile: dict) -> dict:
    """
    Fix any corrupted SRS data with extreme intervals or dates.
    """
    fixed_count = 0
    today = datetime.now().date()
    
    # Fix grammar summary
    for gid, data in profile.get('grammar_summary', {}).items():
        needs_fix = False
        
        # Check for extreme intervals
        if data.get('interval', 0) > MAX_INTERVAL:
            data['interval'] = MAX_INTERVAL
            needs_fix = True
        
        # Check for extreme ease factors
        if data.get('ease_factor', INITIAL_EASE) > MAX_EASE_FACTOR:
            data['ease_factor'] = MAX_EASE_FACTOR
            needs_fix = True
        
        # Check for dates in the far future (more than 6 months from now)
        next_review = data.get('next_review_date', '')
        if next_review:
            try:
                review_date = datetime.fromisoformat(next_review).date()
                if review_date > today + timedelta(days=180):  # Reduced from 365 to 180
                    # Reset to a reasonable interval
                    reps = data.get('reps', 0)
                    if reps < len(INITIAL_INTERVALS):
                        new_interval = INITIAL_INTERVALS[reps] if reps > 0 else INITIAL_INTERVALS[0]
                    else:
                        new_interval = min(INITIAL_INTERVALS[-1] * 2, MAX_INTERVAL)
                    
                    data['interval'] = new_interval
                    data['next_review_date'] = (today + timedelta(days=new_interval)).isoformat()
                    needs_fix = True
            except ValueError:
                # Invalid date format, reset
                data['next_review_date'] = today.isoformat()
                data['interval'] = INITIAL_INTERVALS[0]
                needs_fix = True
        
        if needs_fix:
            fixed_count += 1
            print(f"🔧 Fixed corrupted SRS data for grammar: {gid}")
    
    # Fix vocab summary (same logic)
    for word, data in profile.get('vocab_summary', {}).items():
        needs_fix = False
        
        if data.get('interval', 0) > MAX_INTERVAL:
            data['interval'] = MAX_INTERVAL
            needs_fix = True
        
        if data.get('ease_factor', INITIAL_EASE) > MAX_EASE_FACTOR:
            data['ease_factor'] = MAX_EASE_FACTOR
            needs_fix = True
        
        next_review = data.get('next_review_date', '')
        if next_review:
            try:
                review_date = datetime.fromisoformat(next_review).date()
                if review_date > today + timedelta(days=180):
                    reps = data.get('reps', 0)
                    if reps < len(INITIAL_INTERVALS):
                        new_interval = INITIAL_INTERVALS[reps] if reps > 0 else INITIAL_INTERVALS[0]
                    else:
                        new_interval = min(INITIAL_INTERVALS[-1] * 2, MAX_INTERVAL)
                    
                    data['interval'] = new_interval
                    data['next_review_date'] = (today + timedelta(days=new_interval)).isoformat()
                    needs_fix = True
            except ValueError:
                data['next_review_date'] = today.isoformat()
                data['interval'] = INITIAL_INTERVALS[0]
                needs_fix = True
        
        if needs_fix:
            fixed_count += 1
            print(f"🔧 Fixed corrupted SRS data for vocab: {word}")
    
    if fixed_count > 0:
        print(f"✅ Fixed {fixed_count} corrupted SRS entries")
    
    return profile


def update_user_profile(profile: dict, session_exercises: list) -> dict:
    """
    Updates the user profile based on session exercises.
    Enhanced to ensure all grammar IDs are properly normalized.
    
    Each exercise in session_exercises must have keys:
      - 'grammar_focus': list of grammar IDs
      - 'vocab_used': list of vocabulary strings  
      - 'is_correct': bool
    Returns updated profile.
    """
    # Fix any existing corrupted data first
    profile = fix_corrupted_srs_data(profile)
    
    # Ensure necessary sections exist
    profile.setdefault('grammar_summary', {})
    profile.setdefault('vocab_summary', {})

    for ex in session_exercises:
        correct = ex.get('is_correct', False)
        
        # Update grammar items - ALWAYS NORMALIZE ALL GRAMMAR IDs
        for gid in ex.get('grammar_focus', []):
            # ✅ NORMALIZE THE GRAMMAR ID BEFORE USING IT
            normalized_gid = normalize_grammar_id(gid)
            
            gsum = profile['grammar_summary'].setdefault(
                normalized_gid, {
                    'exposure': 0, 
                    'reps': 0, 
                    'ease_factor': INITIAL_EASE,
                    'interval': INITIAL_INTERVALS[0], 
                    'lapses': 0,
                    'consecutive_correct': 0,
                    'total_attempts': 0,
                    'recent_accuracy': 0.0,
                    'first_seen': datetime.now().date().isoformat(),
                    'last_reviewed': datetime.now().date().isoformat()
                }
            )
            # Increment exposure
            gsum['exposure'] = gsum.get('exposure', 0) + 1
            gsum['last_reviewed'] = datetime.now().date().isoformat()
            
            # Apply conservative SM-2
            _apply_sm2(gsum, correct)

        # Update vocabulary items (these don't need normalization)
        for word in ex.get('vocab_used', []):
            vsum = profile['vocab_summary'].setdefault(
                word, {
                    'reps': 0, 
                    'ease_factor': INITIAL_EASE,
                    'interval': INITIAL_INTERVALS[0], 
                    'lapses': 0,
                    'consecutive_correct': 0,
                    'total_attempts': 0,
                    'recent_accuracy': 0.0
                }
            )
            _apply_sm2(vsum, correct)

    return profile

def calculate_mastery_level(grammar_data: dict) -> str:
    """
    Calculate the mastery level of a grammar point based on various metrics.
    
    Returns: "new", "learning", "reviewing", "mastered"
    """
    reps = grammar_data.get('reps', 0)
    exposures = grammar_data.get('exposure', 0)
    consecutive_correct = grammar_data.get('consecutive_correct', 0)
    recent_accuracy = grammar_data.get('recent_accuracy', 0.0)
    
    if exposures == 0:
        return "new"
    elif reps < 3 or consecutive_correct < 2:
        return "learning"
    elif reps < 5 or recent_accuracy < 0.75:
        return "reviewing"
    else:
        return "mastered"

def get_grammar_mastery_stats(profile: dict) -> dict:
    """
    Get statistics about grammar mastery levels.
    """
    grammar_summary = profile.get('grammar_summary', {})
    stats = {"new": 0, "learning": 0, "reviewing": 0, "mastered": 0}
    
    for gid, data in grammar_summary.items():
        mastery_level = calculate_mastery_level(data)
        stats[mastery_level] += 1
    
    return stats

def validate_profile_grammar_ids(profile: dict) -> dict:
    """
    Validate all grammar IDs in a profile and report any issues.
    
    Returns:
        dict: {
            'valid_count': int,
            'invalid_ids': [list of invalid IDs],
            'inconsistent_ids': [list of IDs that should be normalized],
            'duplicates': [list of potential duplicates]
        }
    """
    grammar_summary = profile.get('grammar_summary', {})
    all_ids = list(grammar_summary.keys())
    
    valid_count = 0
    invalid_ids = []
    inconsistent_ids = []
    
    # Check each ID
    for gid in all_ids:
        normalized = normalize_grammar_id(gid)
        
        # Check if it's already properly normalized
        if gid == normalized:
            # Check if it follows our standard pattern
            if re.match(r'^-[가-힣_]+$', gid) or re.match(r'^-[a-z_]+$', gid):
                valid_count += 1
            else:
                invalid_ids.append(gid)
        else:
            inconsistent_ids.append(f"'{gid}' -> '{normalized}'")
    
    # Find potential duplicates (IDs that normalize to the same thing)
    normalized_groups = {}
    for gid in all_ids:
        normalized = normalize_grammar_id(gid)
        if normalized not in normalized_groups:
            normalized_groups[normalized] = []
        normalized_groups[normalized].append(gid)
    
    duplicates = []
    for normalized, original_ids in normalized_groups.items():
        if len(original_ids) > 1:
            duplicates.append({
                'normalized': normalized,
                'original_ids': original_ids
            })
    
    return {
        'total_ids': len(all_ids),
        'valid_count': valid_count,
        'invalid_ids': invalid_ids,
        'inconsistent_ids': inconsistent_ids,
        'duplicates': duplicates
    }

def clean_profile_grammar_ids(profile: dict, dry_run: bool = False) -> dict:
    """
    Clean and consolidate grammar IDs in a profile.
    
    Args:
        profile: The user profile to clean
        dry_run: If True, return what would be changed without modifying profile
        
    Returns:
        dict: Report of changes made or that would be made
    """
    if dry_run:
        # Create a copy for dry run
        test_profile = json.loads(json.dumps(profile))
        migrated_profile, migration_performed, migration_log = migrate_grammar_profile_data(test_profile)
        validation = validate_profile_grammar_ids(migrated_profile)
        
        return {
            'dry_run': True,
            'migration_performed': migration_performed,
            'migration_log': migration_log,
            'validation': validation,
            'would_save': migration_performed
        }
    else:
        # Actually perform the migration
        migrated_profile, migration_performed, migration_log = migrate_grammar_profile_data(profile)
        validation = validate_profile_grammar_ids(migrated_profile)
        
        # Update the original profile in place
        profile.update(migrated_profile)
        
        return {
            'dry_run': False,
            'migration_performed': migration_performed,
            'migration_log': migration_log,
            'validation': validation,
            'changes_applied': migration_performed
        }
    
# Additional utility function for debugging
def debug_grammar_ids(profile: dict):
    """Print debug information about grammar IDs in a profile."""
    grammar_summary = profile.get('grammar_summary', {})
    
    print(f"📊 Grammar ID Debug Report")
    print(f"{'='*40}")
    print(f"Total grammar entries: {len(grammar_summary)}")
    
    # Group by normalized form
    normalized_groups = {}
    for gid in grammar_summary.keys():
        normalized = normalize_grammar_id(gid)
        if normalized not in normalized_groups:
            normalized_groups[normalized] = []
        normalized_groups[normalized].append(gid)
    
    print(f"Unique normalized forms: {len(normalized_groups)}")
    
    # Show groups with multiple original IDs (potential duplicates)
    duplicates = [group for group in normalized_groups.values() if len(group) > 1]
    if duplicates:
        print(f"\n🔍 Potential duplicates:")
        for group in duplicates:
            print(f"  {group} -> {normalize_grammar_id(group[0])}")
    
    # Show normalization examples
    print(f"\n📝 Normalization examples:")
    examples = list(grammar_summary.keys())[:5]
    for gid in examples:
        normalized = normalize_grammar_id(gid)
        if gid != normalized:
            print(f"  '{gid}' -> '{normalized}'")
        else:
            print(f"  '{gid}' (already normalized)")
    
    # Show SRS stats for top grammar points
    print(f"\n📈 SRS Status (top 5 by reps):")
    sorted_grammar = sorted(
        grammar_summary.items(), 
        key=lambda x: x[1].get('reps', 0), 
        reverse=True
    )[:5]
    
    for gid, data in sorted_grammar:
        reps = data.get('reps', 0)
        interval = data.get('interval', 0)
        next_review = data.get('next_review_date', 'N/A')
        mastery = calculate_mastery_level(data)
        print(f"  {gid}: {reps} reps, {interval}d interval, next: {next_review}, mastery: {mastery}")


if __name__ == '__main__':
    """Test the updated conservative profile system"""
    print("🧪 Testing conservative profile system...")
    
    # Test with a sample profile that has inconsistent grammar IDs
    test_profile = {
        'user_id': 'test_user',
        'grammar_summary': {
            '은는': {'reps': 5, 'ease_factor': 2.5, 'interval': 10, 'exposure': 8},
            '-은_는': {'reps': 3, 'ease_factor': 2.3, 'interval': 6, 'exposure': 5},  # Duplicate!
            '이에요/예요': {'reps': 2, 'ease_factor': 2.5, 'interval': 3, 'exposure': 4},
            '-아요-어요': {'reps': 4, 'ease_factor': 2.7, 'interval': 8, 'exposure': 6},
        }
    }
    
    print("\n📋 Original profile grammar IDs:")
    for gid in test_profile['grammar_summary'].keys():
        print(f"  {gid}")
    
    # Test migration
    migrated, performed, log = migrate_grammar_profile_data(test_profile)
    
    print(f"\n🔄 Migration performed: {performed}")
    if log:
        print("Migration log:")
        for entry in log:
            print(f"  {entry}")
    
    print(f"\n📋 Migrated profile grammar IDs:")
    for gid, data in migrated['grammar_summary'].items():
        mastery = calculate_mastery_level(data)
        print(f"  {gid}: {mastery} (reps: {data.get('reps', 0)}, exposure: {data.get('exposure', 0)})")
    
    # Test mastery stats
    stats = get_grammar_mastery_stats(migrated)
    print(f"\n📊 Mastery Level Distribution:")
    for level, count in stats.items():
        print(f"  {level}: {count}")
    
    # Test conservative SRS
    print(f"\n🔄 Testing conservative SRS updates...")
    test_item = {'reps': 0, 'ease_factor': 2.5, 'interval': 1, 'lapses': 0}
    
    print(f"Starting state: {test_item}")
    
    # Simulate several correct answers
    for i in range(6):
        print(f"\nSimulating correct answer #{i+1}:")
        _apply_sm2(test_item, True)
        print(f"  After update: reps={test_item['reps']}, interval={test_item['interval']}, ease={test_item['ease_factor']:.2f}")
    
    # Simulate a wrong answer
    print(f"\nSimulating incorrect answer:")
    _apply_sm2(test_item, False)
    print(f"  After failure: reps={test_item['reps']}, interval={test_item['interval']}, ease={test_item['ease_factor']:.2f}")
    
    print(f"\n✅ Conservative profile system testing complete!")