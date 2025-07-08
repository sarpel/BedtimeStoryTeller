"""
Configuration management using Pydantic with environment variable support.
Follows resource-first development principles with validation.
"""

import os
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings with environment variable support and validation."""
    
    # Application settings
    app_name: str = Field(default="Bedtime Storyteller", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", env="LOG_LEVEL"
    )
    
    # Resource constraints
    max_memory_mb: int = Field(default=400, env="MAX_MEMORY_MB")
    max_audio_queue_size: int = Field(default=3, env="MAX_AUDIO_QUEUE_SIZE")
    
    # Hardware configuration
    pi_model: Optional[str] = Field(default=None, env="PI_MODEL")
    audio_device: Optional[str] = Field(default=None, env="AUDIO_DEVICE")
    gpio_button_pin: Optional[int] = Field(default=None, env="GPIO_BUTTON_PIN")
    
    # Wakeword engine settings
    wakeword_engine: Literal["porcupine", "openwakeword"] = Field(
        default="porcupine", env="WAKEWORD_ENGINE"
    )
    porcupine_access_key: Optional[str] = Field(default=None, env="PORCUPINE_ACCESS_KEY")
    porcupine_keywords: str = Field(default="porcupine", env="PORCUPINE_KEYWORDS")
    porcupine_model_path: Optional[str] = Field(default=None, env="PORCUPINE_MODEL_PATH")
    openwakeword_model_path: Optional[str] = Field(
        default=None, env="OPENWAKEWORD_MODEL_PATH"
    )
    openwakeword_inference_framework: Literal["onnx", "tflite"] = Field(
        default="tflite", env="OPENWAKEWORD_INFERENCE_FRAMEWORK"
    )
    
    # API settings - LLM providers
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-3.5-turbo", env="OPENAI_MODEL")
    openai_base_url: Optional[str] = Field(default=None, env="OPENAI_BASE_URL")
    
    gemini_api_key: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-pro", env="GEMINI_MODEL")
    
    # API settings - TTS providers
    openai_tts_voice: str = Field(default="alloy", env="OPENAI_TTS_VOICE")
    openai_tts_model: str = Field(default="tts-1", env="OPENAI_TTS_MODEL")
    
    elevenlabs_api_key: Optional[str] = Field(default=None, env="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: Optional[str] = Field(default=None, env="ELEVENLABS_VOICE_ID")
    
    # Default providers
    default_llm_provider: Literal["openai", "gemini"] = Field(
        default="openai", env="DEFAULT_LLM_PROVIDER"
    )
    default_tts_provider: Literal["openai", "elevenlabs"] = Field(
        default="openai", env="DEFAULT_TTS_PROVIDER"
    )
    
    # Story generation settings
    story_language: str = Field(default="tr", env="STORY_LANGUAGE")
    story_age_rating: str = Field(default="5+", env="STORY_AGE_RATING")
    story_max_paragraphs: int = Field(default=10, env="STORY_MAX_PARAGRAPHS")
    
    # Audio settings
    audio_sample_rate: int = Field(default=16000, env="AUDIO_SAMPLE_RATE")
    audio_channels: int = Field(default=1, env="AUDIO_CHANNELS")
    audio_format: str = Field(default="mp3", env="AUDIO_FORMAT")
    
    # Database settings
    database_url: str = Field(
        default="sqlite+aiosqlite:///./storyteller.db", env="DATABASE_URL"
    )
    
    # Web interface settings
    web_host: str = Field(default="0.0.0.0", env="WEB_HOST")
    web_port: int = Field(default=5000, env="WEB_PORT")
    web_secret_key: str = Field(
        default="your-secret-key-change-in-production", env="WEB_SECRET_KEY"
    )
    
    # Safety settings
    content_safety_enabled: bool = Field(default=True, env="CONTENT_SAFETY_ENABLED")
    max_story_length: int = Field(default=2000, env="MAX_STORY_LENGTH")
    
    # Performance settings
    api_timeout_seconds: int = Field(default=30, env="API_TIMEOUT_SECONDS")
    max_concurrent_tts_requests: int = Field(
        default=3, env="MAX_CONCURRENT_TTS_REQUESTS"
    )
    
    # Hardware configuration
    force_mock_hardware: bool = Field(default=False, env="FORCE_MOCK_HARDWARE")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields to prevent validation errors
    
    @field_validator("max_memory_mb")
    @classmethod
    def validate_memory_constraint(cls, v):
        """Ensure memory constraint is reasonable for Pi Zero 2W."""
        if v > 450:  # Pi Zero 2W has 512MB total
            raise ValueError("Memory limit too high for Pi Zero 2W")
        if v < 100:
            raise ValueError("Memory limit too low for application")
        return v
    
    @field_validator("story_language")
    @classmethod
    def validate_story_language(cls, v):
        """Ensure story language is supported."""
        supported_languages = ["tr", "en"]  # Turkish and English
        if v not in supported_languages:
            raise ValueError(f"Unsupported language: {v}")
        return v


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment variables."""
    global settings
    settings = Settings()
    return settings