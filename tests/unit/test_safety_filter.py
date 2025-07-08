"""
Unit tests for safety filter system.
"""

import pytest
from storyteller.utils.safety_filter import SafetyFilter, SafetyViolation

@pytest.fixture
def safety_filter_en():
    """Returns a SafetyFilter instance for English."""
    return SafetyFilter(target_age=5, language="en")

@pytest.fixture
def safety_filter_tr():
    """Returns a SafetyFilter instance for Turkish."""
    return SafetyFilter(target_age=5, language="tr")

def test_initialization(safety_filter_en):
    """Test safety filter initialization."""
    assert safety_filter_en.target_age == 5
    assert safety_filter_en.language == "en"
    assert len(safety_filter_en.forbidden_words) > 0

@pytest.mark.asyncio
async def test_safe_prompt(safety_filter_en):
    """Test a safe prompt."""
    prompt = "A story about a friendly cat."
    filtered_prompt = await safety_filter_en.validate_and_filter_prompt(prompt)
    assert prompt in filtered_prompt

@pytest.mark.asyncio
async def test_unsafe_prompt_with_replacement(safety_filter_en):
    """Test an unsafe prompt that can be filtered."""
    prompt = "A story about a scary monster."
    filtered_prompt = await safety_filter_en.validate_and_filter_prompt(prompt)
    assert "scary" not in filtered_prompt
    assert "monster" not in filtered_prompt
    assert "fun" in filtered_prompt or "cute animal" in filtered_prompt

@pytest.mark.asyncio
async def test_unsafe_prompt_with_high_severity_violation(safety_filter_en):
    """Test an unsafe prompt that will be rejected."""
    prompt = "A story about a violent fight."
    with pytest.raises(ValueError, match="high-severity"):
        await safety_filter_en.validate_and_filter_prompt(prompt)

@pytest.mark.asyncio
async def test_safe_generated_content(safety_filter_en):
    """Test validation of safe generated content."""
    content = "The little cat played in the garden. It was a beautiful day."
    is_safe = await safety_filter_en.validate_generated_content(content)
    assert is_safe is True

@pytest.mark.asyncio
async def test_unsafe_generated_content(safety_filter_en):
    """Test validation of unsafe generated content."""
    content = "The scary monster attacked the village with violence."
    is_safe = await safety_filter_en.validate_generated_content(content)
    assert is_safe is False

def test_get_content_rating(safety_filter_en):
    """Test the content rating system."""
    safe_content = "A happy story about friendship and sharing."
    unsafe_content = "A story about a scary monster and a fight."

    safe_rating = safety_filter_en.get_content_rating(safe_content)
    unsafe_rating = safety_filter_en.get_content_rating(unsafe_content)

    assert safe_rating["safety_score"] > unsafe_rating["safety_score"]
    assert safe_rating["is_safe"] is True
    assert unsafe_rating["is_safe"] is False
    assert len(unsafe_rating["details"]["violations_found"]) > 0

@pytest.mark.asyncio
async def test_turkish_safe_prompt(safety_filter_tr):
    """Test a safe Turkish prompt."""
    prompt = "Arkadaş canlısı bir kedi hakkında bir hikaye."
    filtered_prompt = await safety_filter_tr.validate_and_filter_prompt(prompt)
    assert prompt in filtered_prompt

@pytest.mark.asyncio
async def test_turkish_unsafe_prompt(safety_filter_tr):
    """Test an unsafe Turkish prompt."""
    prompt = "Korkunç bir canavar hakkında bir hikaye."
    filtered_prompt = await safety_filter_tr.validate_and_filter_prompt(prompt)
    assert "korkunç" not in filtered_prompt
    assert "canavar" not in filtered_prompt
    assert "eğlenceli" in filtered_prompt or "sevimli hayvan" in filtered_prompt
