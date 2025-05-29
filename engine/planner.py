import json
import os
from datetime import datetime
from engine.curriculum import load_curriculum
from engine.utils import normalize_grammar_id
from engine.vocab_manager import get_vocab_manager  # NEW: Use centralized vocab manager

# Use pathlib for file paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Get the global vocabulary manager instance
vocab_manager = get_vocab_manager()


def load_user_profile(path: str = None) -> dict:
    path = path or os.path.join(BASE_DIR, 'user_profile.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def should_introduce_new_grammar(profile: dict) -> bool:
    """
    Check if user is ready for new grammar based on mastery criteria.
    
    This implements mastery gating to prevent overwhelming the learner.
    
    Returns:
        bool: True if ready for new grammar, False if should focus on current items
    """
    grammar_summary = profile.get('grammar_summary', {})
    prefs = profile.get('learning_preferences', {})
    
    # Get mastery thresholds from preferences - STRICTER DEFAULTS
    mastery_threshold = prefs.get('grammar_mastery_threshold', 0.85)  # Increased from 0.75
    min_exposures = prefs.get('min_exposures_before_new', 8)  # Increased from 5
    min_consecutive_correct = prefs.get('min_consecutive_correct', 5)  # Increased from 3
    min_total_attempts = prefs.get('min_total_attempts_before_new', 10)  # NEW requirement
    mastery_focus = prefs.get('mastery_focus', True)
    
    if not grammar_summary:
        print("🎯 No grammar history - introducing first grammar point")
        return True  # First grammar point
    
    # MUCH MORE CONSERVATIVE: Require mastery of existing grammar before adding new
    if len(grammar_summary) == 1:
        # For the very first grammar point, require SOLID mastery
        first_grammar = list(grammar_summary.values())[0]
        exposures = first_grammar.get('exposure', 0)
        consecutive_correct = first_grammar.get('consecutive_correct', 0)
        recent_accuracy = first_grammar.get('recent_accuracy', 0.0)
        total_attempts = first_grammar.get('total_attempts', 0)
        reps = first_grammar.get('reps', 0)
        
        is_mastered = (
            exposures >= min_exposures and
            consecutive_correct >= min_consecutive_correct and
            recent_accuracy >= mastery_threshold and
            total_attempts >= min_total_attempts and
            reps >= 4  # Must have progressed through SRS levels
        )
        
        if not is_mastered:
            print(f"🚫 First grammar not mastered yet:")
            print(f"   Exposures: {exposures}/{min_exposures}")
            print(f"   Consecutive correct: {consecutive_correct}/{min_consecutive_correct}")
            print(f"   Accuracy: {recent_accuracy:.1%}/{mastery_threshold:.1%}")
            print(f"   Total attempts: {total_attempts}/{min_total_attempts}")
            print(f"   SRS reps: {reps}/4")
            return False
        else:
            print(f"✅ First grammar mastered - ready for second")
            return True
    
    # For 2-4 grammar points: Require most to be well-mastered
    if len(grammar_summary) <= 4:
        mastered_count = 0
        struggling_count = 0
        
        for gid, data in grammar_summary.items():
            exposures = data.get('exposure', 0)
            consecutive_correct = data.get('consecutive_correct', 0)
            recent_accuracy = data.get('recent_accuracy', 0.0)
            total_attempts = data.get('total_attempts', 0)
            reps = data.get('reps', 0)
            
            # Define "mastered" very strictly
            is_mastered = (
                exposures >= min_exposures and
                consecutive_correct >= min_consecutive_correct and
                recent_accuracy >= mastery_threshold and
                total_attempts >= min_total_attempts and
                reps >= 3
            )
            
            # Define "struggling" - needs immediate attention
            is_struggling = (
                recent_accuracy < 0.6 or
                consecutive_correct == 0 and total_attempts >= 3 or
                reps == 0 and total_attempts >= 5
            )
            
            if is_mastered:
                mastered_count += 1
                print(f"   ✅ {gid}: mastered")
            elif is_struggling:
                struggling_count += 1
                print(f"   ❌ {gid}: struggling (acc: {recent_accuracy:.1%}, streak: {consecutive_correct})")
            else:
                print(f"   🔄 {gid}: learning (acc: {recent_accuracy:.1%}, streak: {consecutive_correct})")
        
        # VERY strict requirements for early grammar
        if struggling_count > 0:
            print(f"🚫 BLOCKED: {struggling_count} grammar points are struggling")
            return False
        
        # Require at least 75% to be mastered before adding new
        mastery_rate = mastered_count / len(grammar_summary)
        if mastery_rate < 0.75:
            print(f"🚫 BLOCKED: Only {mastery_rate:.1%} mastered (need 75%)")
            return False
        
        print(f"✅ APPROVED: {mastery_rate:.1%} mastered, ready for new grammar")
        return True
    
    if not mastery_focus:
        print("🎯 Mastery focus disabled - allowing new grammar")
        return True  # User prefers speed over mastery
    
    # For 5+ grammar points: Use the existing more lenient logic
    struggling_count = 0
    learning_count = 0
    total_grammar = len(grammar_summary)
    
    print(f"\n📊 Advanced Grammar Mastery Analysis:")
    print(f"   Total grammar points: {total_grammar}")
    print(f"   Mastery threshold: {mastery_threshold*100}%")
    print(f"   Min exposures required: {min_exposures}")
    print(f"   Min consecutive correct: {min_consecutive_correct}")
    
    for gid, data in grammar_summary.items():
        exposures = data.get('exposure', 0)
        reps = data.get('reps', 0)
        consecutive_correct = data.get('consecutive_correct', 0)
        recent_accuracy = data.get('recent_accuracy', 0.0)
        total_attempts = data.get('total_attempts', 0)
        
        # Calculate if this grammar point is "mastered"
        has_enough_exposure = exposures >= min_exposures
        has_enough_reps = reps >= 3
        has_consecutive_correct = consecutive_correct >= min_consecutive_correct
        has_good_accuracy = recent_accuracy >= mastery_threshold
        has_enough_attempts = total_attempts >= min_total_attempts
        
        if not has_enough_exposure or not has_enough_attempts:
            struggling_count += 1
            print(f"   ❌ {gid}: insufficient practice ({exposures}/{min_exposures} exp, {total_attempts}/{min_total_attempts} att)")
        elif not has_enough_reps:
            learning_count += 1
            print(f"   🔄 {gid}: learning ({reps} reps, {consecutive_correct} streak)")
        elif not has_consecutive_correct:
            struggling_count += 1
            print(f"   ⚠️  {gid}: needs consistency ({consecutive_correct}/{min_consecutive_correct} correct)")
        elif not has_good_accuracy:
            struggling_count += 1
            print(f"   ⚠️  {gid}: low accuracy ({recent_accuracy:.1%} vs {mastery_threshold:.1%})")
        else:
            print(f"   ✅ {gid}: mastered ({reps} reps, {consecutive_correct} streak, {recent_accuracy:.1%} accuracy)")
    
    # More conservative decision logic for advanced learners
    max_struggling = max(1, total_grammar // 4)  # Allow only 1/4 of grammar to be struggling (was 1/3)
    max_total_unmastered = max(2, total_grammar // 3)  # Allow 1/3 to be unmastered (was 1/2)
    
    total_unmastered = struggling_count + learning_count
    
    print(f"\n🎯 Advanced Mastery Gate Decision:")
    print(f"   Struggling items: {struggling_count} (max allowed: {max_struggling})")
    print(f"   Learning items: {learning_count}")
    print(f"   Total unmastered: {total_unmastered} (max allowed: {max_total_unmastered})")
    
    if struggling_count > max_struggling:
        print(f"   🚫 BLOCKED: Too many struggling grammar points")
        return False
    
    if total_unmastered > max_total_unmastered:
        print(f"   🚫 BLOCKED: Too many unmastered grammar points total")
        return False
    
    print(f"   ✅ APPROVED: Ready for new grammar")
    return True


def get_grammar_readiness_priority(profile: dict) -> dict:
    """
    Determine which grammar points need the most attention.
    
    Returns:
        dict: {
            'urgent_review': [...],     # Points that need immediate attention
            'regular_review': [...],    # Points due for review
            'maintenance': [...]        # Well-mastered points for maintenance
        }
    """
    grammar_summary = profile.get('grammar_summary', {})
    today = datetime.now().date().isoformat()
    
    urgent_review = []
    regular_review = []
    maintenance = []
    
    for gid, data in grammar_summary.items():
        next_review = data.get('next_review_date', today)
        consecutive_correct = data.get('consecutive_correct', 0)
        recent_accuracy = data.get('recent_accuracy', 0.0)
        reps = data.get('reps', 0)
        
        # Urgent: struggling items or overdue
        if (consecutive_correct == 0 and data.get('total_attempts', 0) > 0) or \
           (recent_accuracy < 0.5) or \
           (next_review < today and reps < 3):
            urgent_review.append(gid)
        # Regular: due for review
        elif next_review <= today:
            regular_review.append(gid)
        # Maintenance: well-mastered but occasionally review
        elif reps >= 5 and recent_accuracy >= 0.8:
            maintenance.append(gid)
    
    return {
        'urgent_review': urgent_review,
        'regular_review': regular_review,
        'maintenance': maintenance
    }


def select_review_and_new_items(
    profile_path: str = None,
    curriculum_path: str = None,
    vocab_data_path: str = None
) -> dict:
    """
    MUCH MORE CONSERVATIVE selection with extended focus on mastery.
    """
    # Load data
    profile = load_user_profile(profile_path)
    curriculum = load_curriculum()

    # MUCH MORE CONSERVATIVE preferences with stricter defaults
    prefs = profile.get('learning_preferences', {})
    reviews_per_session = prefs.get('reviews_per_session', 10)  # Reduced from 15
    new_grammar_per_session = prefs.get('new_grammar_per_session', 1)  # Keep at 1 
    new_vocab_per_session = prefs.get('new_vocab_per_session', 2)      # Reduced from 3
    
    # NEW: Session intensity control
    max_new_items_per_session = prefs.get('max_new_items_per_session', 1)  # Limit total new learning
    focus_sessions_required = prefs.get('focus_sessions_required', 3)       # Sessions before adding new content

    today = datetime.now().date().isoformat()

    print(f"\n📋 CONSERVATIVE Session Planning - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Review capacity: {reviews_per_session}")
    print(f"   New grammar limit: {new_grammar_per_session}")
    print(f"   New vocab limit: {new_vocab_per_session}")
    print(f"   Max new items total: {max_new_items_per_session}")

    # Check if this is a "consolidation session" (no new content)
    session_count = profile.get('session_tracking', {}).get('exercises_completed', 0)
    last_new_content_session = profile.get('_last_new_content_session', 0)
    sessions_since_new = session_count - last_new_content_session
    
    is_consolidation_session = sessions_since_new < focus_sessions_required
    
    if is_consolidation_session:
        print(f"🔒 CONSOLIDATION SESSION: {sessions_since_new}/{focus_sessions_required} focus sessions completed")
        new_grammar_per_session = 0
        new_vocab_per_session = 0
        max_new_items_per_session = 0

    # 1. Grammar Priority Analysis (same as before)
    grammar_priority = get_grammar_readiness_priority(profile)
    
    print(f"\n📊 Grammar Priority Analysis:")
    print(f"   Urgent review: {len(grammar_priority['urgent_review'])} items")
    print(f"   Regular review: {len(grammar_priority['regular_review'])} items")
    print(f"   Maintenance: {len(grammar_priority['maintenance'])} items")

    # 2. Prioritize urgent items even more strongly
    review_grammar = grammar_priority['urgent_review'][:reviews_per_session]
    remaining_slots = reviews_per_session - len(review_grammar)
    
    # If we have urgent items, reduce new content allowance
    if grammar_priority['urgent_review']:
        max_new_items_per_session = 0  # No new content when struggling
        print(f"🚨 Urgent items detected - blocking all new content")
    
    if remaining_slots > 0:
        review_grammar.extend(grammar_priority['regular_review'][:remaining_slots])

    print(f"   Selected for review: {len(review_grammar)} grammar points")

    # 3. Review due vocab (more conservative)
    vocab_summary = profile.get('vocab_summary', {})
    due_vocab = [w for w, data in vocab_summary.items()
                 if data.get('next_review_date', '') <= today]
    due_vocab.sort(key=lambda w: vocab_summary[w]['next_review_date'])
    review_vocab = due_vocab[:reviews_per_session//2]  # Halve vocab reviews to focus on grammar

    # 4. NEW GRAMMAR WITH MUCH STRICTER MASTERY GATING
    new_grammar = []
    if max_new_items_per_session > 0:
        mastery_gate_approved = should_introduce_new_grammar(profile)
        
        if mastery_gate_approved:
            user_level = profile.get('user_level', 'beginner')
            level_points = [pt for pt in curriculum.get('grammar_points', []) if pt.get('level') == user_level]
            
            grammar_summary = profile.get('grammar_summary', {})
            seen = {normalize_grammar_id(gid) for gid in grammar_summary.keys()}
            unseen = [pt for pt in level_points if normalize_grammar_id(pt['id']) not in seen]
            unseen.sort(key=lambda x: x.get('learning_order', float('inf')))
            
            # Respect the max new items limit
            allowed_new_grammar = min(new_grammar_per_session, max_new_items_per_session)
            new_grammar = [pt['id'] for pt in unseen[:allowed_new_grammar]]
            
            if new_grammar:
                print(f"   ✅ New grammar approved: {new_grammar}")
                # Track that we added new content
                profile['_last_new_content_session'] = session_count
            else:
                print(f"   ℹ️  No new grammar available at current level")
        else:
            new_grammar = []
            print(f"   🚫 New grammar blocked by mastery gate")

    # 5. New vocab (much more conservative)
    new_vocab = []
    if max_new_items_per_session > 0 and len(new_grammar) < max_new_items_per_session:
        seen_vocab = set(profile.get('vocab_summary', {}).keys())
        user_level = profile.get('user_level', 'beginner')
        
        # Drastically limit new vocabulary when grammar is being learned
        remaining_new_slots = max_new_items_per_session - len(new_grammar)
        actual_new_vocab_limit = min(new_vocab_per_session, remaining_new_slots)
        
        if actual_new_vocab_limit > 0:
            new_vocab = vocab_manager.get_words_for_level(
                user_level=user_level,
                known_words=seen_vocab,
                limit=actual_new_vocab_limit
            )
            
            if new_vocab:
                print(f"   📚 New vocab approved: {new_vocab}")
                profile['_last_new_content_session'] = session_count
        
    # Enhanced mastery gate status
    mastery_gate_status = {
        'approved': len(new_grammar) > 0 or len(new_vocab) > 0,
        'grammar_priority': grammar_priority,
        'is_consolidation_session': is_consolidation_session,
        'sessions_since_new': sessions_since_new,
        'urgent_items_blocking': len(grammar_priority['urgent_review']) > 0,
        'max_new_items_enforced': max_new_items_per_session
    }

    result = {
        'review_grammar': review_grammar,
        'review_vocab': review_vocab,
        'new_grammar': new_grammar,
        'new_vocab': new_vocab,
        'grammar_priority': grammar_priority,
        'mastery_gate_status': mastery_gate_status
    }

    print(f"\n📋 CONSERVATIVE Final Selection:")
    print(f"   Review Grammar: {len(review_grammar)} items")
    print(f"   Review Vocab: {len(review_vocab)} items")
    print(f"   New Grammar: {len(new_grammar)} items {'✅' if new_grammar else '🚫'}")
    print(f"   New Vocab: {len(new_vocab)} items")
    print(f"   Session Type: {'🔒 Consolidation' if is_consolidation_session else '📚 Learning'}")
    
    return result

# Backward compatibility function - now uses vocabulary manager
def load_vocab_data(path: str = None) -> dict:
    """
    Legacy function for backward compatibility.
    Now returns cached data from VocabularyManager instead of reading file.
    
    Args:
        path: Ignored - kept for compatibility
        
    Returns:
        Dictionary of vocabulary data from centralized manager
    """
    return vocab_manager._vocab_data


# Additional helper functions that leverage the vocabulary manager
def get_vocab_suggestions_for_grammar(grammar_targets: list, user_level: str, known_words: set, limit: int = 5) -> list:
    """
    Get vocabulary suggestions that work well with specific grammar targets.
    
    This is a more intelligent approach than just getting random words.
    """
    # For now, use level-appropriate words
    # TODO: Could be enhanced to suggest words that specifically work with target grammar
    return vocab_manager.get_words_for_level(
        user_level=user_level,
        known_words=known_words,
        limit=limit
    )


def get_vocab_by_frequency_for_level(user_level: str, known_words: set, limit: int = 10) -> list:
    """
    Get high-frequency vocabulary appropriate for user's level.
    """
    # Get level-appropriate words
    level_words = vocab_manager.get_words_for_level(user_level, known_words, limit * 3)
    
    # Sort by frequency within the level-appropriate words
    level_words_with_freq = []
    for word in level_words:
        word_data = vocab_manager.get_word_data(word)
        freq_rank = word_data.get('frequency_rank', float('inf')) if word_data else float('inf')
        level_words_with_freq.append((word, freq_rank))
    
    # Sort by frequency and return top words
    level_words_with_freq.sort(key=lambda x: x[1])
    return [word for word, _ in level_words_with_freq[:limit]]


def analyze_session_recommendations(profile: dict) -> dict:
    """
    Provide session recommendations based on current learning state.
    
    Returns:
        dict: Recommendations for the current session
    """
    selections = select_review_and_new_items(profile_path=None)  # Use current profile
    
    grammar_priority = selections['grammar_priority']
    mastery_status = selections['mastery_gate_status']
    
    recommendations = []
    
    # Urgent items recommendation
    if grammar_priority['urgent_review']:
        recommendations.append({
            'type': 'urgent',
            'message': f"Focus on struggling grammar: {', '.join(grammar_priority['urgent_review'][:3])}",
            'priority': 'high'
        })
    
    # New grammar recommendation
    if mastery_status['approved'] and selections['new_grammar']:
        recommendations.append({
            'type': 'new_content',
            'message': f"Ready for new grammar: {selections['new_grammar'][0]}",
            'priority': 'medium'
        })
    elif not mastery_status['approved']:
        recommendations.append({
            'type': 'mastery_focus',  
            'message': "Focus on mastering current grammar before learning new concepts",
            'priority': 'high'
        })
    
    # Vocabulary recommendation
    if len(selections['new_vocab']) > 0:
        recommendations.append({
            'type': 'vocabulary',
            'message': f"Practice with {len(selections['new_vocab'])} new vocabulary words",
            'priority': 'low'
        })
    
    return {
        'recommendations': recommendations,
        'session_focus': 'mastery' if not mastery_status['approved'] else 'balanced',
        'difficulty_adjustment': 'maintain' if grammar_priority['urgent_review'] else 'normal'
    }


if __name__ == '__main__':
    """Test the updated planner with mastery gating"""
    print("🧪 Testing updated planner with mastery gating...")
    
    # Print vocabulary stats
    stats = vocab_manager.get_stats()
    print(f"\n📊 Vocabulary Manager Stats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Test the selection process
    print(f"\n🎯 Testing item selection with mastery gating...")
    selections = select_review_and_new_items()
    
    print(f"\nDetailed Selection Results:")
    print(f"  Review Grammar: {selections['review_grammar']}")
    print(f"  New Grammar: {selections['new_grammar']}")
    print(f"  Review Vocab: {len(selections['review_vocab'])} words")
    print(f"  New Vocab: {selections['new_vocab']}")
    
    # Test mastery gate status
    mastery_status = selections['mastery_gate_status']
    print(f"\n🚪 Mastery Gate Status:")
    print(f"  Approved: {mastery_status['approved']}")
    print(f"  Total Grammar Points: {mastery_status['total_grammar_points']}")
    print(f"  Urgent Items: {mastery_status['urgent_count']}")
    
    # Test priority analysis
    priority = selections['grammar_priority']
    print(f"\n📊 Grammar Priority Analysis:")
    print(f"  Urgent: {priority['urgent_review']}")
    print(f"  Regular: {priority['regular_review']}")
    print(f"  Maintenance: {priority['maintenance']}")
    
    # Test session recommendations
    print(f"\n💡 Session Recommendations:")
    recommendations = analyze_session_recommendations({})
    for rec in recommendations['recommendations']:
        priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}[rec['priority']]
        print(f"  {priority_emoji} {rec['type']}: {rec['message']}")
    
    print(f"\n✅ Mastery gating planner testing complete!")