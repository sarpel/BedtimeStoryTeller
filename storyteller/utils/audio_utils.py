"""
Audio processing utilities.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def calculate_audio_duration(audio_data: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> float:
    """
    Calculate audio duration in seconds.
    
    Args:
        audio_data: Raw audio data
        sample_rate: Sample rate in Hz
        channels: Number of audio channels
        sample_width: Sample width in bytes (2 for 16-bit)
        
    Returns:
        float: Duration in seconds
    """
    try:
        total_samples = len(audio_data) // (channels * sample_width)
        duration = total_samples / sample_rate
        return duration
    except ZeroDivisionError:
        return 0.0


def validate_audio_format(audio_data: bytes, expected_format: str = "pcm_16") -> bool:
    """
    Validate audio data format.
    
    Args:
        audio_data: Raw audio data
        expected_format: Expected audio format
        
    Returns:
        bool: True if format is valid
    """
    try:
        if not audio_data:
            return False
        
        # Basic validation - check if data length is reasonable
        if len(audio_data) < 100:  # Too short
            return False
        
        # For PCM 16-bit, data length should be even
        if expected_format == "pcm_16" and len(audio_data) % 2 != 0:
            return False
        
        return True
        
    except Exception as e:
        logger.warning(f"Audio format validation failed: {e}")
        return False