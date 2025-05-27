"""
Centralized Vocabulary Management System

This module provides a singleton-pattern vocabulary manager that:
1. Loads vocabulary data once and caches it in memory
2. Handles format conversion from legacy array to dict format
3. Provides efficient access methods for different use cases
4. Eliminates redundant file reads across the application

File: engine/vocab_manager.py
"""

import json
import os
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VocabEntry:
    """Structured representation of a vocabulary entry"""
    word: str
    translation: str
    frequency_rank: Optional[int] = None
    topik_level: Optional[str] = None
    vocab_rom: Optional[str] = None
    tags: Optional[str] = None
    ease: float = 0.0
    lapses: int = 0
    reps: int = 0


class VocabularyManager:
    """
    Singleton vocabulary manager that centralizes all vocabulary operations.
    
    Features:
    - Single source of truth for vocabulary data
    - Efficient caching and memory management
    - Format conversion handling
    - Fast lookups and filtering
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VocabularyManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not VocabularyManager._initialized:
            self._vocab_data: Dict[str, Dict] = {}
            self._vocab_entries: Dict[str, VocabEntry] = {}
            self._base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            self._vocab_file_path = os.path.join(self._base_dir, 'vocab_data.json')
            self._load_vocabulary()
            VocabularyManager._initialized = True
    
    def _load_vocabulary(self) -> None:
        """Load and process vocabulary data from file"""
        try:
            with open(self._vocab_file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            # Handle format conversion
            if isinstance(raw_data, list):
                print("🔄 Converting vocabulary from array to dictionary format...")
                self._vocab_data = self._convert_array_to_dict(raw_data)
                print(f"✅ Converted {len(self._vocab_data)} vocabulary entries")
                
                # Optionally save the converted format back to file
                self._save_converted_format()
            elif isinstance(raw_data, dict):
                self._vocab_data = raw_data
                print(f"✅ Loaded {len(self._vocab_data)} vocabulary entries")
            else:
                raise ValueError(f"Invalid vocab_data format: {type(raw_data)}")
            
            # Create structured entries for easier access
            self._create_vocab_entries()
            
        except FileNotFoundError:
            print(f"⚠️  Vocabulary file not found: {self._vocab_file_path}")
            self._vocab_data = {}
            self._vocab_entries = {}
        except Exception as e:
            print(f"❌ Error loading vocabulary: {e}")
            self._vocab_data = {}
            self._vocab_entries = {}
    
    def _convert_array_to_dict(self, array_data: List[Dict]) -> Dict[str, Dict]:
        """Convert legacy array format to dictionary format"""
        vocab_dict = {}
        for entry in array_data:
            if isinstance(entry, dict) and 'vocab' in entry:
                vocab_word = entry['vocab']
                vocab_info = {k: v for k, v in entry.items() if k != 'vocab'}
                vocab_dict[vocab_word] = vocab_info
            else:
                print(f"⚠️  Skipping invalid entry: {entry}")
        return vocab_dict
    
    def _save_converted_format(self) -> None:
        """Save the converted dictionary format back to file"""
        try:
            # Create backup of original file
            backup_path = self._vocab_file_path + '.backup'
            if not os.path.exists(backup_path):
                import shutil
                shutil.copy2(self._vocab_file_path, backup_path)
                print(f"📦 Created backup: {backup_path}")
            
            # Save converted format
            with open(self._vocab_file_path, 'w', encoding='utf-8') as f:
                json.dump(self._vocab_data, f, ensure_ascii=False, indent=2)
            print("💾 Saved converted vocabulary format to file")
            
        except Exception as e:
            print(f"⚠️  Could not save converted format: {e}")
    
    def _create_vocab_entries(self) -> None:
        """Create structured VocabEntry objects for easier access"""
        self._vocab_entries = {}
        for word, data in self._vocab_data.items():
            try:
                entry = VocabEntry(
                    word=word,
                    translation=data.get('translation', ''),
                    frequency_rank=data.get('frequency_rank'),
                    topik_level=data.get('topik_level'),
                    vocab_rom=data.get('vocab_rom'),
                    tags=data.get('tags'),
                    ease=data.get('ease', 0.0),
                    lapses=data.get('lapses', 0),
                    reps=data.get('reps', 0)
                )
                self._vocab_entries[word] = entry
            except Exception as e:
                print(f"⚠️  Error creating entry for '{word}': {e}")
    
    # Public API methods
    
    def get_all_words(self) -> List[str]:
        """Get list of all vocabulary words"""
        return list(self._vocab_data.keys())
    
    def get_word_data(self, word: str) -> Optional[Dict]:
        """Get raw data for a specific word"""
        return self._vocab_data.get(word)
    
    def get_word_entry(self, word: str) -> Optional[VocabEntry]:
        """Get structured entry for a specific word"""
        return self._vocab_entries.get(word)
    
    def get_words_by_frequency(self, limit: Optional[int] = None) -> List[str]:
        """Get words sorted by frequency rank (most frequent first)"""
        words_with_freq = [
            (word, data.get('frequency_rank', float('inf')))
            for word, data in self._vocab_data.items()
            if data.get('frequency_rank') is not None
        ]
        words_with_freq.sort(key=lambda x: x[1])
        words = [word for word, _ in words_with_freq]
        
        if limit:
            return words[:limit]
        return words
    
    def get_words_by_level(self, level: str) -> List[str]:
        """Get words filtered by TOPIK level"""
        return [
            word for word, data in self._vocab_data.items()
            if data.get('topik_level') == level
        ]
    
    def get_words_by_tags(self, tags: str) -> List[str]:
        """Get words filtered by tags (e.g., 'Beginner', 'Intermediate')"""
        return [
            word for word, data in self._vocab_data.items()
            if data.get('tags') == tags
        ]
    
    def get_new_words_for_user(self, known_words: Set[str], limit: int = 10, 
                              prefer_frequent: bool = True) -> List[str]:
        """
        Get new words for a user to learn, excluding already known words.
        
        Args:
            known_words: Set of words the user already knows
            limit: Maximum number of words to return
            prefer_frequent: Whether to prioritize high-frequency words
            
        Returns:
            List of new words to learn
        """
        available_words = [
            word for word in self._vocab_data.keys()
            if word not in known_words
        ]
        
        if prefer_frequent:
            # Sort by frequency rank (lower rank = more frequent)
            available_words.sort(
                key=lambda w: self._vocab_data[w].get('frequency_rank', float('inf'))
            )
        
        return available_words[:limit]
    
    def get_words_for_level(self, user_level: str, known_words: Set[str], 
                           limit: int = 5) -> List[str]:
        """
        Get appropriate words for a user's level, excluding known words.
        
        Args:
            user_level: User's proficiency level ('beginner', 'intermediate', etc.)
            known_words: Set of words the user already knows
            limit: Maximum number of words to return
            
        Returns:
            List of level-appropriate words
        """
        # Map user levels to TOPIK levels and tags
        level_mapping = {
            'beginner': {'topik_levels': ['1'], 'tags': ['Beginner']},
            'intermediate': {'topik_levels': ['1', '2'], 'tags': ['Beginner', 'Intermediate']},
            'advanced': {'topik_levels': ['1', '2', '3'], 'tags': ['Beginner', 'Intermediate', 'Advanced']}
        }
        
        level_config = level_mapping.get(user_level, level_mapping['beginner'])
        
        # Get words matching the level criteria
        level_words = []
        for word, data in self._vocab_data.items():
            if word in known_words:
                continue
                
            topik_level = data.get('topik_level', '').strip()
            tags = data.get('tags', '').strip()
            
            # Check if word matches level criteria
            matches_topik = any(topik_level.startswith(level) for level in level_config['topik_levels'])
            matches_tags = tags in level_config['tags']
            
            if matches_topik or matches_tags:
                level_words.append(word)
        
        # Sort by frequency and return limited set
        level_words.sort(
            key=lambda w: self._vocab_data[w].get('frequency_rank', float('inf'))
        )
        
        return level_words[:limit]
    
    def search_words(self, query: str, limit: int = 10) -> List[str]:
        """Search words by Korean text or translation"""
        query_lower = query.lower()
        matches = []
        
        for word, data in self._vocab_data.items():
            # Search in Korean word
            if query_lower in word.lower():
                matches.append((word, 0))  # Exact match priority
                continue
            
            # Search in translation
            translation = data.get('translation', '').lower()
            if query_lower in translation:
                matches.append((word, 1))  # Translation match
                continue
            
            # Search in romanization
            vocab_rom = data.get('vocab_rom', '').lower()
            if vocab_rom and query_lower in vocab_rom:
                matches.append((word, 2))  # Romanization match
        
        # Sort by match priority and return words only
        matches.sort(key=lambda x: x[1])
        return [word for word, _ in matches[:limit]]
    
    def get_stats(self) -> Dict[str, any]:
        """Get vocabulary database statistics"""
        if not self._vocab_data:
            return {}
        
        # Count by levels
        level_counts = {}
        tag_counts = {}
        freq_available = 0
        
        for data in self._vocab_data.values():
            # Count TOPIK levels
            topik_level = data.get('topik_level', 'Unknown')
            level_counts[topik_level] = level_counts.get(topik_level, 0) + 1
            
            # Count tags
            tags = data.get('tags', 'Unknown')
            tag_counts[tags] = tag_counts.get(tags, 0) + 1
            
            # Count frequency data availability
            if data.get('frequency_rank') is not None:
                freq_available += 1
        
        return {
            'total_words': len(self._vocab_data),
            'by_topik_level': level_counts,
            'by_tags': tag_counts,
            'with_frequency_rank': freq_available,
            'frequency_coverage': f"{freq_available/len(self._vocab_data)*100:.1f}%"
        }
    
    def reload(self) -> None:
        """Reload vocabulary data from file (useful for development)"""
        print("🔄 Reloading vocabulary data...")
        self._load_vocabulary()
    
    # Context manager support for testing
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


# Global instance - use this for all vocabulary operations
vocab_manager = VocabularyManager()


# Convenience functions for backward compatibility
def load_vocab_data(path: str = None) -> Dict[str, Dict]:
    """
    Legacy function for backward compatibility.
    Now returns cached data from VocabularyManager.
    """
    return vocab_manager._vocab_data


def get_vocab_manager() -> VocabularyManager:
    """Get the global vocabulary manager instance"""
    return vocab_manager


# Example usage and testing
if __name__ == '__main__':
    print("🧪 Testing Vocabulary Manager...")
    
    # Get manager instance
    vm = get_vocab_manager()
    
    # Print statistics
    stats = vm.get_stats()
    print(f"\n📊 Vocabulary Statistics:")
    print(f"Total words: {stats.get('total_words', 0)}")
    print(f"TOPIK level distribution: {stats.get('by_topik_level', {})}")
    print(f"Tag distribution: {stats.get('by_tags', {})}")
    print(f"Frequency data coverage: {stats.get('frequency_coverage', 'N/A')}")
    
    # Test word retrieval
    print(f"\n🔤 Sample Operations:")
    all_words = vm.get_all_words()
    print(f"Total words available: {len(all_words)}")
    
    # Test frequency-based retrieval
    frequent_words = vm.get_words_by_frequency(limit=5)
    print(f"Top 5 frequent words: {frequent_words}")
    
    # Test level-based retrieval
    beginner_words = vm.get_words_by_level('1')
    print(f"TOPIK Level 1 words: {len(beginner_words)} (showing first 5: {beginner_words[:5]})")
    
    # Test new word suggestions
    known_words = set(frequent_words[:3])  # Simulate user knowing top 3 words
    new_suggestions = vm.get_new_words_for_user(known_words, limit=5)
    print(f"New word suggestions: {new_suggestions}")
    
    # Test search
    search_results = vm.search_words('love', limit=3)
    print(f"Search results for 'love': {search_results}")
    
    print(f"\n✅ Vocabulary Manager testing complete!")
