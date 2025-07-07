"""
Unit tests for safety filter system.
"""

import pytest
from unittest.mock import patch, MagicMock

from storyteller.utils.safety_filter import SafetyFilter, ContentSafetyError


class TestSafetyFilter:
    """Test the content safety filtering system."""
    
    def test_initialization(self):
        """Test safety filter initialization."""
        filter = SafetyFilter(target_age=5, language="tr")
        
        assert filter.target_age == 5
        assert filter.language == "tr"
        assert filter.enabled is True
    
    def test_initialization_with_custom_rules(self):
        """Test initialization with custom forbidden words."""
        custom_words = ["bad", "scary", "fight"]
        filter = SafetyFilter(
            target_age=5,
            language="en",
            forbidden_words=custom_words
        )
        
        assert "bad" in filter.forbidden_words
        assert "scary" in filter.forbidden_words
        assert "fight" in filter.forbidden_words
    
    def test_safe_content_english(self):
        """Test safe English content."""
        filter = SafetyFilter(target_age=5, language="en")
        
        safe_texts = [
            "Once upon a time, there was a little cat.",
            "The cat played in the beautiful garden.",
            "All the animals were happy and friendly.",
            "They lived happily ever after."
        ]
        
        for text in safe_texts:
            assert filter.is_content_safe(text) is True
            assert filter.get_safety_score(text) > 0.7
    
    def test_safe_content_turkish(self):
        """Test safe Turkish content."""
        filter = SafetyFilter(target_age=5, language="tr")
        
        safe_texts = [
            "Bir zamanlar küçük bir kedi varmış.",
            "Kedi güzel bahçede oynarmış.",
            "Tüm hayvanlar mutlu ve arkadaş canlısıymış.",
            "Sonra hep birlikte mutlu yaşamışlar."
        ]
        
        for text in safe_texts:
            assert filter.is_content_safe(text) is True
            assert filter.get_safety_score(text) > 0.7
    
    def test_unsafe_content_detection(self):
        """Test detection of unsafe content."""
        filter = SafetyFilter(target_age=5, language="en")
        
        unsafe_texts = [
            "The monster was very scary and dangerous.",
            "There was violence and fighting everywhere.",
            "The children were in terrible danger.",
            "Blood was everywhere in the dark forest."
        ]
        
        for text in unsafe_texts:
            assert filter.is_content_safe(text) is False
            assert filter.get_safety_score(text) < 0.5
    
    def test_turkish_unsafe_content(self):
        """Test detection of unsafe Turkish content."""
        filter = SafetyFilter(target_age=5, language="tr")
        
        unsafe_texts = [
            "Canavar çok korkunç ve tehlikeliydi.",
            "Her yerde şiddet ve kavga vardı.",
            "Çocuklar büyük tehlike içindeydi.",
            "Karanlık ormanda kan vardı."
        ]
        
        for text in unsafe_texts:
            assert filter.is_content_safe(text) is False
            assert filter.get_safety_score(text) < 0.5
    
    def test_content_filtering_replacement(self):
        """Test content filtering with replacement."""
        filter = SafetyFilter(target_age=5, language="en")
        
        unsafe_text = "The scary monster attacked the village."
        filtered_text = filter.filter_content(unsafe_text)
        
        # Should replace inappropriate words
        assert "scary" not in filtered_text.lower()
        assert "monster" not in filtered_text.lower()
        assert "attacked" not in filtered_text.lower()
        assert len(filtered_text) > 0  # Should have replacement content
    
    def test_turkish_content_filtering(self):
        """Test Turkish content filtering."""
        filter = SafetyFilter(target_age=5, language="tr")
        
        unsafe_text = "Korkunç canavar köyü saldırdı."
        filtered_text = filter.filter_content(unsafe_text)
        
        # Should replace inappropriate words
        assert "korkunç" not in filtered_text.lower()
        assert "canavar" not in filtered_text.lower()
        assert "saldır" not in filtered_text.lower()
        assert len(filtered_text) > 0
    
    def test_age_appropriate_content_levels(self):
        """Test different age levels have different safety criteria."""
        text = "There was a small conflict between the characters."
        
        filter_3 = SafetyFilter(target_age=3, language="en")
        filter_8 = SafetyFilter(target_age=8, language="en")
        
        # Younger age should be more restrictive
        score_3 = filter_3.get_safety_score(text)
        score_8 = filter_8.get_safety_score(text)
        
        assert score_8 >= score_3  # Older age more permissive
    
    def test_empty_and_none_content(self):
        """Test handling of empty or None content."""
        filter = SafetyFilter(target_age=5, language="en")
        
        # Empty string
        assert filter.is_content_safe("") is True
        assert filter.get_safety_score("") == 1.0
        
        # None content should raise error or return safe default
        with pytest.raises((ValueError, TypeError)):
            filter.is_content_safe(None)
    
    def test_very_long_content(self):
        """Test handling of very long content."""
        filter = SafetyFilter(target_age=5, language="en")
        
        # Create very long safe content
        long_safe_text = "The cat played happily in the garden. " * 100
        assert filter.is_content_safe(long_safe_text) is True
        
        # Create very long unsafe content
        long_unsafe_text = "The scary monster attacked everyone. " * 100
        assert filter.is_content_safe(long_unsafe_text) is False
    
    def test_mixed_language_content(self):
        """Test handling of mixed language content."""
        filter = SafetyFilter(target_age=5, language="tr")
        
        mixed_text = "Hello, merhaba! The cat kedi played oynadı."
        
        # Should still be able to evaluate mixed content
        safety_score = filter.get_safety_score(mixed_text)
        assert 0.0 <= safety_score <= 1.0
    
    def test_special_characters_and_punctuation(self):
        """Test handling of special characters and punctuation."""
        filter = SafetyFilter(target_age=5, language="en")
        
        texts_with_special_chars = [
            "The cat said, 'Meow!' and jumped.",
            "Numbers: 123, symbols: @#$%",
            "Emoji-like text: :) :( :D",
            "Quotes: \"Hello,\" she said."
        ]
        
        for text in texts_with_special_chars:
            # Should not crash and should return valid scores
            score = filter.get_safety_score(text)
            assert 0.0 <= score <= 1.0
    
    def test_disabled_filter(self):
        """Test behavior when filter is disabled."""
        filter = SafetyFilter(target_age=5, language="en", enabled=False)
        
        unsafe_text = "Very scary monster attacks everyone violently."
        
        # When disabled, should pass everything
        assert filter.is_content_safe(unsafe_text) is True
        assert filter.get_safety_score(unsafe_text) == 1.0
        assert filter.filter_content(unsafe_text) == unsafe_text
    
    def test_custom_forbidden_words(self):
        """Test custom forbidden words."""
        custom_words = ["banana", "purple", "specific_word"]
        filter = SafetyFilter(
            target_age=5,
            language="en",
            forbidden_words=custom_words
        )
        
        # Should detect custom forbidden words
        assert filter.is_content_safe("I like banana pie.") is False
        assert filter.is_content_safe("The purple dragon flew.") is False
        assert filter.is_content_safe("This has specific_word in it.") is False
        
        # Safe content should still pass
        assert filter.is_content_safe("The cat played in the garden.") is True
    
    def test_case_insensitive_filtering(self):
        """Test that filtering is case insensitive."""
        filter = SafetyFilter(target_age=5, language="en")
        
        variations = [
            "SCARY monster",
            "Scary Monster",
            "scary MONSTER",
            "ScArY mOnStEr"
        ]
        
        for text in variations:
            assert filter.is_content_safe(text) is False
    
    def test_word_boundary_detection(self):
        """Test that word boundaries are respected in filtering."""
        filter = SafetyFilter(target_age=5, language="en")
        
        # "scar" should not trigger "scary" filter
        assert filter.is_content_safe("The cat had a small scar.") is True
        
        # But "scary" should trigger
        assert filter.is_content_safe("The scary cat ran away.") is False
    
    def test_safety_score_consistency(self):
        """Test that safety scores are consistent."""
        filter = SafetyFilter(target_age=5, language="en")
        
        text = "The little cat played in the garden."
        
        # Multiple calls should return the same score
        score1 = filter.get_safety_score(text)
        score2 = filter.get_safety_score(text)
        score3 = filter.get_safety_score(text)
        
        assert score1 == score2 == score3
    
    def test_content_safety_error(self):
        """Test ContentSafetyError exception."""
        error = ContentSafetyError("Unsafe content detected", safety_score=0.2)
        
        assert str(error) == "Unsafe content detected"
        assert error.safety_score == 0.2
    
    def test_filter_with_exception_on_unsafe(self):
        """Test filter configured to raise exception on unsafe content."""
        filter = SafetyFilter(target_age=5, language="en", strict_mode=True)
        
        unsafe_text = "The scary monster attacked everyone."
        
        # In strict mode, should raise exception
        with pytest.raises(ContentSafetyError):
            filter.filter_content(unsafe_text)
    
    def test_performance_with_large_content(self, performance_monitor):
        """Test performance with large content."""
        filter = SafetyFilter(target_age=5, language="en")
        
        # Create large content (10KB)
        large_content = "The cat played happily in the beautiful garden. " * 200
        
        performance_monitor.start()
        
        # Should complete within reasonable time
        result = filter.is_content_safe(large_content)
        
        metrics = performance_monitor.stop()
        
        assert result is True
        assert metrics["duration"] < 1.0  # Should complete within 1 second
    
    def test_thread_safety(self):
        """Test that safety filter is thread-safe."""
        import threading
        import time
        
        filter = SafetyFilter(target_age=5, language="en")
        results = []
        
        def test_worker():
            for i in range(10):
                result = filter.is_content_safe("The cat played in the garden.")
                results.append(result)
                time.sleep(0.01)  # Small delay to encourage race conditions
        
        # Run multiple threads
        threads = [threading.Thread(target=test_worker) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # All results should be True and consistent
        assert all(results)
        assert len(results) == 30  # 3 threads * 10 iterations


if __name__ == "__main__":
    pytest.main([__file__])