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


def select_review_and_new_items(
    profile_path: str = None,
    curriculum_path: str = None,
    vocab_data_path: str = None  # This parameter is now ignored but kept for compatibility
) -> dict:
    """
    Selects SRS review items (grammar & vocab due), then new items within user preferences.
    Now uses centralized vocabulary manager instead of loading vocab data from file.
    
    Returns dict with keys:
      - 'review_grammar': list of grammar IDs due for review
      - 'review_vocab': list of vocab words due for review
      - 'new_grammar': list of new grammar IDs to introduce
      - 'new_vocab': list of new vocab words to introduce
    """
    # Load data
    profile = load_user_profile(profile_path)
    curriculum = load_curriculum()  # ignore path, use default
    # vocab_data now comes from vocabulary manager instead of file loading

    # Preferences with defaults
    prefs = profile.get('learning_preferences', {})
    reviews_per_session = prefs.get('reviews_per_session', 10)
    new_grammar_per_session = prefs.get('new_grammar_per_session', 2)
    new_vocab_per_session = prefs.get('new_vocab_per_session', 5)

    today = datetime.now().date().isoformat()

    # 1. Review due grammar
    grammar_summary = profile.get('grammar_summary', {})
    due_grammar = [gid for gid, data in grammar_summary.items()
                   if data.get('next_review_date', '') <= today]
    due_grammar.sort(key=lambda gid: grammar_summary[gid]['next_review_date'])
    review_grammar = due_grammar[:reviews_per_session]

    # 2. Review due vocab
    vocab_summary = profile.get('vocab_summary', {})
    due_vocab = [w for w, data in vocab_summary.items()
                 if data.get('next_review_date', '') <= today]
    due_vocab.sort(key=lambda w: vocab_summary[w]['next_review_date'])
    review_vocab = due_vocab[:reviews_per_session]

    # 3. New grammar: from curriculum by user level
    user_level = profile.get('user_level', 'beginner')
    level_points = [pt for pt in curriculum.get('grammar_points', []) if pt.get('level') == user_level]
    # Filter out seen grammar using normalized IDs
    seen = {normalize_grammar_id(gid) for gid in grammar_summary.keys()}
    unseen = [pt for pt in level_points if normalize_grammar_id(pt['id']) not in seen]
    unseen.sort(key=lambda x: x.get('learning_order', float('inf')))
    new_grammar = [pt['id'] for pt in unseen[:new_grammar_per_session]]

    # 4. New vocab: Use vocabulary manager to get level-appropriate words
    seen_vocab = set(profile.get('vocab_summary', {}).keys())
    
    # Get new vocabulary suggestions using the vocabulary manager
    # This is much more efficient and intelligent than the old approach
    new_vocab = vocab_manager.get_words_for_level(
        user_level=user_level,
        known_words=seen_vocab,
        limit=new_vocab_per_session * 2  # Get more candidates
    )
    
    # If we don't have enough level-appropriate words, supplement with high-frequency words
    if len(new_vocab) < new_vocab_per_session:
        additional_words = vocab_manager.get_new_words_for_user(
            known_words=seen_vocab.union(set(new_vocab)),
            limit=new_vocab_per_session,
            prefer_frequent=True
        )
        new_vocab.extend(additional_words)
    
    # Limit to requested amount
    new_vocab = new_vocab[:new_vocab_per_session]
    
    # Debug output for vocabulary selection
    print(f"📚 Vocabulary Selection Debug:")
    print(f"  User level: {user_level}")
    print(f"  Known words: {len(seen_vocab)}")
    print(f"  New vocab candidates: {len(new_vocab)} - {new_vocab}")
    
    # Get some stats from vocabulary manager for debugging
    vocab_stats = vocab_manager.get_stats()
    print(f"  Vocabulary DB stats: {vocab_stats['total_words']} total words")
    print(f"  Level distribution: {vocab_stats.get('by_tags', {})}")

    return {
        'review_grammar': review_grammar,
        'review_vocab': review_vocab,
        'new_grammar': new_grammar,
        'new_vocab': new_vocab
    }


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


if __name__ == '__main__':
    """Test the updated planner with vocabulary manager"""
    print("🧪 Testing updated planner with vocabulary manager...")
    
    # Print vocabulary stats
    stats = vocab_manager.get_stats()
    print(f"\n📊 Vocabulary Manager Stats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Test the selection process
    print(f"\n🎯 Testing item selection...")
    selections = select_review_and_new_items()
    
    print(f"\nSelection Results:")
    print(f"  Review Grammar: {selections['review_grammar']}")
    print(f"  New Grammar: {selections['new_grammar']}")
    print(f"  Review Vocab: {selections['review_vocab']}")
    print(f"  New Vocab: {selections['new_vocab']}")
    
    # Test additional helper functions
    print(f"\n🔤 Testing vocab suggestions...")
    known_words = set(['사랑', '방', '소주'])  # Sample known words
    
    level_suggestions = get_vocab_suggestions_for_grammar(
        grammar_targets=['-이에요_예요', '-아요_어요'],
        user_level='beginner',
        known_words=known_words,
        limit=5
    )
    print(f"  Grammar-based suggestions: {level_suggestions}")
    
    freq_suggestions = get_vocab_by_frequency_for_level(
        user_level='beginner',
        known_words=known_words,
        limit=5
    )
    print(f"  Frequency-based suggestions: {freq_suggestions}")
    
    print(f"\n✅ Planner testing complete!")