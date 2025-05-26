import json
import os
from datetime import datetime
from engine.curriculum import load_curriculum
from engine.utils import normalize_grammar_id

# Use pathlib for file paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def load_user_profile(path: str = None) -> dict:
    path = path or os.path.join(BASE_DIR, 'user_profile.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_vocab_data(path: str = None) -> dict:
    """
    Load vocabulary data and ensure it's in dictionary format.
    
    Expected format: {"word": {"translation": "...", "frequency_rank": 123, ...}}
    """
    path = path or os.path.join(BASE_DIR, 'vocab_data.json')
    with open(path, 'r', encoding='utf-8') as f:
        vocab_data = json.load(f)
    
    # Ensure dictionary format (with fallback for legacy array format)
    if isinstance(vocab_data, list):
        print("⚠️  Converting legacy array format to dictionary format...")
        vocab_dict = {}
        for entry in vocab_data:
            if isinstance(entry, dict) and 'vocab' in entry:
                vocab_word = entry['vocab']
                vocab_info = {k: v for k, v in entry.items() if k != 'vocab'}
                vocab_dict[vocab_word] = vocab_info
        return vocab_dict
    elif isinstance(vocab_data, dict):
        return vocab_data
    else:
        raise ValueError(f"Invalid vocab_data format: {type(vocab_data)}")


def select_review_and_new_items(
    profile_path: str = None,
    curriculum_path: str = None,
    vocab_data_path: str = None
) -> dict:
    """
    Selects SRS review items (grammar & vocab due), then new items within user preferences.
    Returns dict with keys:
      - 'review_grammar': list of grammar IDs due for review
      - 'review_vocab': list of vocab words due for review
      - 'new_grammar': list of new grammar IDs to introduce
      - 'new_vocab': list of new vocab words to introduce
    """
    # Load data
    profile = load_user_profile(profile_path)
    curriculum = load_curriculum()  # ignore path, use default
    vocab_data = load_vocab_data(vocab_data_path)

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

    # 4. New vocab: from vocab_data by frequency, not yet in profile
    # SIMPLIFIED: vocab_data is now always a dictionary
    all_words = list(vocab_data.keys())
    seen_vocab = set(profile.get('vocab_summary', {}).keys())
    unseen_vocab = [w for w in all_words if w not in seen_vocab]
    
    # Sort unseen_vocab by frequency_rank if available
    def freq_rank(word):
        return vocab_data[word].get('frequency_rank', float('inf'))
    
    unseen_vocab.sort(key=freq_rank)
    new_vocab = unseen_vocab[:new_vocab_per_session]

    return {
        'review_grammar': review_grammar,
        'review_vocab': review_vocab,
        'new_grammar': new_grammar,
        'new_vocab': new_vocab
    }