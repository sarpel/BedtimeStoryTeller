"""
Unit tests for configuration system.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from storyteller.config.settings import Settings, get_settings, reload_settings
from storyteller.config.hardware_profiles import (
    detect_hardware_profile,
    PiModel,
    AudioProfile,
    GPIOProfile,
    HardwareProfile
)


class TestSettings:
    """Test the settings configuration system."""
    
    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings()
        
        assert settings.max_memory_mb == 400
        assert settings.wakeword_engine == "porcupine"
        assert settings.story_language == "tr"
        assert settings.story_age_rating == "5+"
        assert settings.story_max_paragraphs == 10
        assert settings.content_safety_enabled is True
        assert settings.audio_sample_rate == 16000
        assert settings.audio_channels == 1
    
    def test_environment_override(self):
        """Test that environment variables override defaults."""
        with patch.dict(os.environ, {
            'MAX_MEMORY_MB': '300',
            'WAKEWORD_ENGINE': 'openwakeword',
            'STORY_LANGUAGE': 'en',
            'STORY_AGE_RATING': '8+',
            'CONTENT_SAFETY_ENABLED': 'false'
        }):
            settings = Settings()
            
            assert settings.max_memory_mb == 300
            assert settings.wakeword_engine == "openwakeword"
            assert settings.story_language == "en"
            assert settings.story_age_rating == "8+"
            assert settings.content_safety_enabled is False
    
    def test_memory_limit_validation(self):
        """Test memory limit validation."""
        with patch.dict(os.environ, {'MAX_MEMORY_MB': '100'}):
            with pytest.raises(ValueError):
                Settings()
        
        with patch.dict(os.environ, {'MAX_MEMORY_MB': '2000'}):
            with pytest.raises(ValueError):
                Settings()
    
    def test_wakeword_engine_validation(self):
        """Test wakeword engine validation."""
        with patch.dict(os.environ, {'WAKEWORD_ENGINE': 'invalid'}):
            with pytest.raises(ValueError):
                Settings()
    
    def test_language_validation(self):
        """Test language validation."""
        with patch.dict(os.environ, {'STORY_LANGUAGE': 'fr'}):
            with pytest.raises(ValueError):
                Settings()
    
    def test_age_rating_validation(self):
        """Test age rating validation."""
        with patch.dict(os.environ, {'STORY_AGE_RATING': 'invalid'}):
            with pytest.raises(ValueError):
                Settings()
    
    def test_api_key_validation(self):
        """Test API key validation."""
        # Test that empty API keys are handled
        settings = Settings()
        assert settings.openai_api_key is None
        assert settings.porcupine_access_key is None
    
    def test_database_url_default(self):
        """Test database URL default value."""
        settings = Settings()
        assert "sqlite+aiosqlite" in settings.database_url
        assert "storyteller.db" in settings.database_url
    
    def test_get_settings_singleton(self):
        """Test that get_settings returns the same instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
    
    def test_reload_settings(self):
        """Test settings reload functionality."""
        # Get initial settings
        settings1 = get_settings()
        initial_memory = settings1.max_memory_mb
        
        # Change environment and reload
        with patch.dict(os.environ, {'MAX_MEMORY_MB': '350'}):
            reload_settings()
            settings2 = get_settings()
            
            assert settings2.max_memory_mb == 350
            assert settings2.max_memory_mb != initial_memory


class TestHardwareProfiles:
    """Test hardware profile detection and configuration."""
    
    def test_pi_model_enum(self):
        """Test Pi model enumeration."""
        assert PiModel.PI_ZERO_2W.value == "pi_zero_2w"
        assert PiModel.PI_4.value == "pi_4"
        assert PiModel.PI_5.value == "pi_5"
        assert PiModel.UNKNOWN.value == "unknown"
    
    @patch('pathlib.Path.exists')
    @patch('builtins.open')
    def test_detect_pi_zero_2w(self, mock_open, mock_exists):
        """Test Pi Zero 2W detection."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "Raspberry Pi Zero 2 W Rev 1.0"
        
        profile = detect_hardware_profile()
        
        assert profile.model == PiModel.PI_ZERO_2W
        assert profile.audio.device_type == "iqaudio_codec"
        assert profile.audio.alsa_device == "hw:0,0"
        assert profile.gpio.button_pin == 18
        assert profile.gpio.led_pin == 24
    
    @patch('pathlib.Path.exists')
    @patch('builtins.open')
    def test_detect_pi_5(self, mock_open, mock_exists):
        """Test Pi 5 detection."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "Raspberry Pi 5 Model B Rev 1.0"
        
        profile = detect_hardware_profile()
        
        assert profile.model == PiModel.PI_5
        assert profile.audio.device_type == "usb_audio"
        assert "plughw" in profile.audio.alsa_device
    
    @patch('pathlib.Path.exists')
    @patch('builtins.open')
    def test_detect_pi_4(self, mock_open, mock_exists):
        """Test Pi 4 detection."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "Raspberry Pi 4 Model B Rev 1.2"
        
        profile = detect_hardware_profile()
        
        assert profile.model == PiModel.PI_4
        assert profile.audio.device_type == "usb_audio"
    
    @patch('pathlib.Path.exists')
    def test_detect_unknown_model(self, mock_exists):
        """Test unknown model detection."""
        mock_exists.return_value = False
        
        profile = detect_hardware_profile()
        
        assert profile.model == PiModel.UNKNOWN
        assert profile.audio.device_type == "auto"
    
    def test_audio_profile_creation(self):
        """Test audio profile creation."""
        audio = AudioProfile(
            device_type="test_audio",
            alsa_device="hw:1,0",
            sample_rate=44100,
            channels=2,
            buffer_size=2048
        )
        
        assert audio.device_type == "test_audio"
        assert audio.alsa_device == "hw:1,0"
        assert audio.sample_rate == 44100
        assert audio.channels == 2
        assert audio.buffer_size == 2048
    
    def test_gpio_profile_creation(self):
        """Test GPIO profile creation."""
        gpio = GPIOProfile(
            button_pin=20,
            led_pin=21,
            button_pull_up=False,
            button_bounce_time=300
        )
        
        assert gpio.button_pin == 20
        assert gpio.led_pin == 21
        assert gpio.button_pull_up is False
        assert gpio.button_bounce_time == 300
    
    def test_hardware_profile_creation(self):
        """Test complete hardware profile creation."""
        audio = AudioProfile(device_type="test", alsa_device="hw:0,0")
        gpio = GPIOProfile(button_pin=18, led_pin=24)
        
        profile = HardwareProfile(
            model=PiModel.PI_ZERO_2W,
            audio=audio,
            gpio=gpio,
            memory_limit_mb=350
        )
        
        assert profile.model == PiModel.PI_ZERO_2W
        assert profile.audio == audio
        assert profile.gpio == gpio
        assert profile.memory_limit_mb == 350
    
    @patch.dict(os.environ, {'PI_MODEL': 'pi_5'})
    def test_environment_override_detection(self):
        """Test that environment variables can override hardware detection."""
        profile = detect_hardware_profile()
        
        # Should still auto-detect if environment specifies unknown model
        assert profile.model in [PiModel.PI_5, PiModel.UNKNOWN]
    
    def test_audio_profile_validation(self):
        """Test audio profile validation."""
        # Test valid sample rates
        valid_rates = [8000, 16000, 22050, 44100, 48000]
        for rate in valid_rates:
            audio = AudioProfile(
                device_type="test",
                alsa_device="hw:0,0",
                sample_rate=rate
            )
            assert audio.sample_rate == rate
        
        # Test invalid sample rate
        with pytest.raises(ValueError):
            AudioProfile(
                device_type="test",
                alsa_device="hw:0,0",
                sample_rate=1000  # Invalid rate
            )
    
    def test_gpio_profile_validation(self):
        """Test GPIO profile validation."""
        # Test valid GPIO pins
        valid_pins = [2, 3, 4, 18, 24, 25]
        for pin in valid_pins:
            gpio = GPIOProfile(button_pin=pin, led_pin=pin)
            assert gpio.button_pin == pin
        
        # Test invalid GPIO pin
        with pytest.raises(ValueError):
            GPIOProfile(button_pin=50, led_pin=24)  # Pin 50 doesn't exist
    
    def test_memory_optimization_settings(self):
        """Test memory optimization settings for different Pi models."""
        # Pi Zero 2W should have stricter memory limits
        pi_zero_profile = HardwareProfile(
            model=PiModel.PI_ZERO_2W,
            audio=AudioProfile(device_type="iqaudio", alsa_device="hw:0,0"),
            gpio=GPIOProfile(button_pin=18, led_pin=24),
            memory_limit_mb=350
        )
        
        # Pi 5 should have more relaxed limits
        pi5_profile = HardwareProfile(
            model=PiModel.PI_5,
            audio=AudioProfile(device_type="usb", alsa_device="plughw:1,0"),
            gpio=GPIOProfile(button_pin=18, led_pin=24),
            memory_limit_mb=800
        )
        
        assert pi_zero_profile.memory_limit_mb < pi5_profile.memory_limit_mb
    
    def test_profile_serialization(self):
        """Test that profiles can be serialized/deserialized."""
        profile = detect_hardware_profile()
        
        # Test that profile can be converted to dict (for JSON serialization)
        profile_dict = {
            "model": profile.model.value,
            "audio": {
                "device_type": profile.audio.device_type,
                "alsa_device": profile.audio.alsa_device,
                "sample_rate": profile.audio.sample_rate,
                "channels": profile.audio.channels
            },
            "gpio": {
                "button_pin": profile.gpio.button_pin,
                "led_pin": profile.gpio.led_pin
            },
            "memory_limit_mb": profile.memory_limit_mb
        }
        
        assert isinstance(profile_dict["model"], str)
        assert isinstance(profile_dict["audio"]["sample_rate"], int)
        assert isinstance(profile_dict["gpio"]["button_pin"], (int, type(None)))


if __name__ == "__main__":
    pytest.main([__file__])