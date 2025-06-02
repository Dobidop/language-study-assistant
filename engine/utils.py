import re
import json
from engine.llm_client import chat
from typing import Set, Dict, List, Tuple

def normalize_answer_for_comparison(text: str) -> str:
    """
    Normalize answer text for comparison by removing trailing punctuation
    and standardizing whitespace.
    
    Args:
        text: The text to normalize
        
    Returns:
        Normalized text for comparison
    """
    if not isinstance(text, str):
        return str(text)
    
    # Remove leading/trailing whitespace
    normalized = text.strip()
    
    # Remove trailing punctuation (but preserve punctuation within the text)
    # Common punctuation that might appear at the end of Korean sentences
    trailing_punct = ['!', '?', '.', '。', '！', '？']
    
    # Keep removing trailing punctuation until none left
    while normalized and any(normalized.endswith(punct) for punct in trailing_punct):
        for punct in trailing_punct:
            if normalized.endswith(punct):
                normalized = normalized[:-len(punct)].strip()
                break
    
    # Normalize internal whitespace
    normalized = ' '.join(normalized.split())
    
    return normalized

def normalize_grammar_id(raw_id: str) -> str:
    """
    Enhanced normalization that creates consistent grammar IDs.
    
    Standard format: -{korean_pattern} or -{korean_pattern1}_{korean_pattern2}
    
    Rules:
    1. Always start with '-' prefix for grammar patterns
    2. Use '_' to separate alternative forms (not '/')
    3. Keep Korean characters intact
    4. Handle complex patterns systematically
    5. Remove extra spaces and punctuation
    
    Examples:
    '이에요/예요' -> '-이에요_예요'
    '-아요/-어요' -> '-아요_어요'
    '은는' -> '-은_는'
    'topic marking particle' -> '-topic_marking_particle' (for English descriptions)
    """
    if not raw_id:
        return raw_id
    
    s = raw_id.strip()
    
    # Handle edge case: if it's purely an English description, convert to snake_case with prefix
    if re.match(r'^[a-zA-Z\s]+$', s):
        s = re.sub(r'\s+', '_', s.lower())
        return f'-{s}' if not s.startswith('-') else s
    
    # Comprehensive Korean grammar pattern detection and separation
    korean_patterns = {
        # Verb endings
        '이에요예요': '이에요_예요',
        '아요어요': '아요_어요',
        '았어요었어요': '았어요_었어요',
        '으ㄹ거예요': '으ㄹ_거예요',
        '아어야해요': '아_어야_해요',
        '아어서': '아_어서',
        '아어보다': '아_어_보다',
        '아어주세요': '아_어_주세요',
        '아어도돼요': '아_어도_돼요',
        
        # Particles
        '은는': '은_는',
        '이가': '이_가',
        '을를': '을_를',
        
        # Complex patterns
        '으ㄴ는것같다': '으ㄴ는_것_같다',
        '으ㄹ수있다없다': '으ㄹ_수_있다_없다',
        '기때문에': '기_때문에',
        '으려고하다': '으려고_하다',
        '고나서': '고_나서',
        '으ㄴ적이있다': '으ㄴ_적이_있다',
        '으ㄴ다음에': '으ㄴ_다음에',
        '기전에': '기_전에',
        '으ㄹ때': '으ㄹ_때',
        '는것': '는_것',
        '은는것': '은_는_것',
        '고있다': '고_있다',
        '고싶다': '고_싶다',
        '지않아요': '지_않아요',
        '지못하다': '지_못하다',
        '지마세요': '지_마세요',
        '밖에없다': '밖에_없다',
        '으로가다오다': '으로_가다_오다',
    }
    
    # Apply Korean pattern corrections first
    for original, replacement in korean_patterns.items():
        s = s.replace(original, replacement)
    
    # Handle slash and dash separators systematically
    # Pattern: {prefix}korean{separator}korean{suffix}
    s = re.sub(r'([가-힣]+)/([가-힣]+)', r'\1_\2', s)  # 아요/어요 -> 아요_어요
    s = re.sub(r'([가-힣]+)-([가-힣]+)', r'\1_\2', s)   # 아요-어요 -> 아요_어요
    
    # Handle prefixed patterns: -korean/-korean
    s = re.sub(r'(-[가-힣]+)/(-[가-힣]+)', r'\1_\2', s)  # -아요/-어요 -> -아요_-어요
    s = re.sub(r'(-[가-힣]+)-(-[가-힣]+)', r'\1_\2', s)   # -아요--어요 -> -아요_-어요
    
    # Clean up double prefixes: -아요_-어요 -> -아요_어요
    s = re.sub(r'_-([가-힣])', r'_\1', s)
    
    # Ensure consistent prefix for Korean grammar patterns
    if re.search(r'[가-힣]', s):  # Contains Korean characters
        if not s.startswith('-'):
            s = '-' + s
    
    # Normalize English parts to lowercase
    s = re.sub(r'[A-Z]', lambda m: m.group().lower(), s)
    
    # Clean up punctuation but preserve essential markers
    s = re.sub(r'[^\w\s가-힣_\-]', '', s)  # Keep Korean, word chars, spaces, underscores, hyphens
    s = re.sub(r'\s+', '_', s)  # Spaces to underscores
    s = re.sub(r'_+', '_', s)   # Collapse multiple underscores
    s = s.strip('_')            # Remove leading/trailing underscores
    return s

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

def migrate_grammar_profile(profile: dict) -> Tuple[dict, List[str]]:
    """
    Migrate existing profile to use consistent grammar IDs.
    
    Returns:
        tuple: (updated_profile, migration_log)
    """
    migration_log = []
    
    if 'grammar_summary' not in profile:
        return profile, migration_log
    
    old_grammar_summary = profile['grammar_summary'].copy()
    new_grammar_summary = {}
    
    for old_id, data in old_grammar_summary.items():
        new_id = normalize_grammar_id(old_id)
        
        if old_id != new_id:
            migration_log.append(f"Migrated: '{old_id}' -> '{new_id}'")
            
            # If the new_id already exists, merge the data intelligently
            if new_id in new_grammar_summary:
                migration_log.append(f"Merging duplicate: '{new_id}'")
                # Keep the data with more repetitions (more advanced SRS state)
                existing_data = new_grammar_summary[new_id]
                if data.get('reps', 0) > existing_data.get('reps', 0):
                    new_grammar_summary[new_id] = data
                    migration_log.append(f"  Used data from '{old_id}' (more reps)")
                else:
                    migration_log.append(f"  Kept existing data (more reps)")
            else:
                new_grammar_summary[new_id] = data
        else:
            # ID was already normalized
            new_grammar_summary[new_id] = data
    
    profile['grammar_summary'] = new_grammar_summary
    return profile, migration_log

def validate_grammar_ids(grammar_ids: List[str]) -> Dict[str, List[str]]:
    """
    Validate a list of grammar IDs and report issues.
    
    Returns:
        dict: {
            'valid': [list of valid IDs],
            'invalid': [list of invalid IDs],
            'normalized': [list of suggested normalizations]
        }
    """
    valid = []
    invalid = []
    normalized = []
    
    for gid in grammar_ids:
        if not gid or not isinstance(gid, str):
            invalid.append(f"Invalid type: {repr(gid)}")
            continue
            
        normalized_id = normalize_grammar_id(gid)
        
        if gid != normalized_id:
            normalized.append(f"'{gid}' -> '{normalized_id}'")
        
        # Check if it follows our standard pattern
        if re.match(r'^-[가-힣_]+$', normalized_id) or re.match(r'^-[a-z_]+$', normalized_id):
            valid.append(normalized_id)
        else:
            invalid.append(f"Doesn't match standard pattern: '{normalized_id}'")
    
    return {
        'valid': valid,
        'invalid': invalid,
        'normalized': normalized
    }

def find_grammar_duplicates(profile: dict) -> List[Tuple[str, str]]:
    """
    Find potential duplicate grammar IDs that should be the same.
    
    Returns:
        List of tuples: [(id1, id2), ...] where id1 and id2 are likely duplicates
    """
    grammar_summary = profile.get('grammar_summary', {})
    ids = list(grammar_summary.keys())
    
    # Normalize all IDs and group by normalized form
    normalized_groups = {}
    for gid in ids:
        normalized = normalize_grammar_id(gid)
        if normalized not in normalized_groups:
            normalized_groups[normalized] = []
        normalized_groups[normalized].append(gid)
    
    # Find groups with multiple original IDs
    duplicates = []
    for normalized, original_ids in normalized_groups.items():
        if len(original_ids) > 1:
            # Return all pairs in this group
            for i in range(len(original_ids)):
                for j in range(i + 1, len(original_ids)):
                    duplicates.append((original_ids[i], original_ids[j]))
    
    return duplicates

def test_normalization():
    """
    Test the normalization function with various inputs.
    """
    test_cases = [
        # Basic patterns
        ('-이에요/예요', '-이에요_예요'),
        ('-아요/-어요', '-아요_어요'),
        ('은는', '-은_는'),
        ('이가', '-이_가'),
        ('을를', '-을_를'),
        
        # Complex patterns
        ('-았어요/-었어요', '-았어요_었어요'),
        ('으ㄹ거예요', '-으ㄹ_거예요'),
        ('아요어요', '-아요_어요'),
        
        # Edge cases
        ('', ''),
        ('topic marking particle', '-topic_marking_particle'),
        ('-지_않아요', '-지_않아요'),  # Already normalized
        
        # Mixed formats
        ('이에요예요', '-이에요_예요'),
        ('-으ㄴ는것같다', '-으ㄴ는_것_같다'),
    ]
    
    print("🧪 Testing grammar ID normalization...")
    all_passed = True
    
    for input_id, expected in test_cases:
        result = normalize_grammar_id(input_id)
        if result == expected:
            print(f"✅ '{input_id}' -> '{result}'")
        else:
            print(f"❌ '{input_id}' -> '{result}' (expected '{expected}')")
            all_passed = False
    
    if all_passed:
        print("🎉 All tests passed!")
    else:
        print("⚠️ Some tests failed.")
    
    return all_passed

# Additional utility: Curriculum consistency checker
def check_curriculum_consistency(curriculum_path: str = None) -> Dict[str, any]:
    """
    Check if curriculum grammar IDs are consistently normalized.
    """
    if not curriculum_path:
        curriculum_path = 'curriculum/korean.json'
    
    try:
        with open(curriculum_path, 'r', encoding='utf-8') as f:
            curriculum = json.load(f)
    except FileNotFoundError:
        return {'error': f'Curriculum file not found: {curriculum_path}'}
    
    grammar_points = curriculum.get('grammar_points', [])
    all_ids = [gp.get('id', '') for gp in grammar_points]
    
    validation_result = validate_grammar_ids(all_ids)
    
    return {
        'total_grammar_points': len(grammar_points),
        'validation': validation_result,
        'needs_migration': len(validation_result['normalized']) > 0
    }

if __name__ == '__main__':
    # Run tests
    test_normalization()
    
    # Check curriculum consistency
    print("\n📚 Checking curriculum consistency...")
    curriculum_check = check_curriculum_consistency()
    if 'error' not in curriculum_check:
        print(f"Total grammar points: {curriculum_check['total_grammar_points']}")
        print(f"Needs migration: {curriculum_check['needs_migration']}")
        if curriculum_check['validation']['normalized']:
            print("Suggested normalizations:")
            for norm in curriculum_check['validation']['normalized']:
                print(f"  {norm}")
    else:
        print(f"Error: {curriculum_check['error']}")