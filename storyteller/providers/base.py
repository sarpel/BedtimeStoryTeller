"""
Abstract base classes for LLM and TTS providers.
Implements the provider pattern for easy switching between external services.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    """Provider availability status."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


@dataclass
class StoryRequest:
    """Request for story generation."""
    prompt: str
    language: str = "tr"
    age_rating: str = "5+"
    max_paragraphs: int = 10
    style: Optional[str] = None
    characters: Optional[List[str]] = None


@dataclass
class TTSRequest:
    """Request for text-to-speech synthesis."""
    text: str
    voice: Optional[str] = None
    language: str = "tr"
    speed: float = 1.0
    format: str = "mp3"


@dataclass
class ProviderError(Exception):
    """Provider error information."""
    provider_name: str
    error_type: str
    message: str
    retry_after: Optional[int] = None
    is_recoverable: bool = True


class BaseLLMProvider(ABC):
    """Abstract base class for Large Language Model providers."""
    
    def __init__(self, name: str, **kwargs):
        self.name = name
        self.status = ProviderStatus.AVAILABLE
        self.last_error: Optional[ProviderError] = None
        self._configure(**kwargs)
    
    @abstractmethod
    def _configure(self, **kwargs) -> None:
        """Configure the provider with API keys and settings."""
        pass
    
    @abstractmethod
    async def generate_story_stream(
        self, request: StoryRequest
    ) -> AsyncGenerator[str, None]:
        """
        Generate a story paragraph by paragraph as an async stream.
        
        Args:
            request: Story generation request
            
        Yields:
            str: Individual paragraphs of the story
            
        Raises:
            ProviderError: If generation fails
        """
        pass
    
    @abstractmethod
    async def check_availability(self) -> ProviderStatus:
        """Check if the provider is currently available."""
        pass
    
    async def get_safety_filtered_prompt(self, request: StoryRequest) -> str:
        """
        Create a safety-filtered prompt for age-appropriate content.
        
        Args:
            request: Story generation request
            
        Returns:
            str: Safety-filtered prompt
        """
        base_prompt = f"""
Please create a gentle, age-appropriate bedtime story in {request.language} 
for a {request.age_rating} child. The story should be:

- Calming and peaceful
- Educational or featuring positive values
- Free from scary, violent, or inappropriate content
- Suitable for bedtime (ending should be soothing)

Story topic: {request.prompt}

Please structure the story in {request.max_paragraphs} short paragraphs, 
each paragraph should be 2-3 sentences long.
"""
        
        if request.language == "tr":
            base_prompt = f"""
Lütfen {request.age_rating} yaşındaki bir çocuk için Türkçe, yaşına uygun, 
yumuşak bir uyku masalı oluşturun. Hikaye şöyle olmalı:

- Sakinleştirici ve huzur verici
- Eğitici veya olumlu değerler içeren
- Korkutucu, şiddetli veya uygunsuz içerik barındırmayan
- Uyku vakti için uygun (sonu rahatlatıcı olmalı)

Hikaye konusu: {request.prompt}

Lütfen hikayeyi {request.max_paragraphs} kısa paragrafta yapılandırın,
her paragraf 2-3 cümle uzunluğunda olsun.
"""
        
        return base_prompt
    
    def set_status(self, status: ProviderStatus, error: Optional[ProviderError] = None):
        """Update provider status and error information."""
        self.status = status
        self.last_error = error
        if error:
            logger.warning(f"Provider {self.name} error: {error.message}")


class BaseTTSProvider(ABC):
    """Abstract base class for Text-to-Speech providers."""
    
    def __init__(self, name: str, **kwargs):
        self.name = name
        self.status = ProviderStatus.AVAILABLE
        self.last_error: Optional[ProviderError] = None
        self._configure(**kwargs)
    
    @abstractmethod
    def _configure(self, **kwargs) -> None:
        """Configure the provider with API keys and settings."""
        pass
    
    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> bytes:
        """
        Synthesize text to speech audio.
        
        Args:
            request: TTS synthesis request
            
        Returns:
            bytes: Audio data in the requested format
            
        Raises:
            ProviderError: If synthesis fails
        """
        pass
    
    @abstractmethod
    async def synthesize_stream(
        self, request: TTSRequest
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesize text to speech as a streaming response.
        
        Args:
            request: TTS synthesis request
            
        Yields:
            bytes: Audio chunks
            
        Raises:
            ProviderError: If synthesis fails
        """
        pass
    
    @abstractmethod
    async def check_availability(self) -> ProviderStatus:
        """Check if the provider is currently available."""
        pass
    
    @abstractmethod
    def get_supported_voices(self) -> List[str]:
        """Get list of supported voice names."""
        pass
    
    def set_status(self, status: ProviderStatus, error: Optional[ProviderError] = None):
        """Update provider status and error information."""
        self.status = status
        self.last_error = error
        if error:
            logger.warning(f"Provider {self.name} error: {error.message}")


class ProviderManager:
    """Manages multiple providers with fallback capabilities."""
    
    def __init__(self):
        self.llm_providers: Dict[str, BaseLLMProvider] = {}
        self.tts_providers: Dict[str, BaseTTSProvider] = {}
        self.default_llm: Optional[str] = None
        self.default_tts: Optional[str] = None
    
    def register_llm_provider(self, provider: BaseLLMProvider, is_default: bool = False):
        """Register an LLM provider."""
        self.llm_providers[provider.name] = provider
        if is_default or not self.default_llm:
            self.default_llm = provider.name
        logger.info(f"Registered LLM provider: {provider.name}")
    
    def register_tts_provider(self, provider: BaseTTSProvider, is_default: bool = False):
        """Register a TTS provider."""
        self.tts_providers[provider.name] = provider
        if is_default or not self.default_tts:
            self.default_tts = provider.name
        logger.info(f"Registered TTS provider: {provider.name}")
    
    async def get_available_llm_provider(
        self, preferred: Optional[str] = None
    ) -> Optional[BaseLLMProvider]:
        """Get an available LLM provider, with fallback logic."""
        providers_to_try = []
        
        # Try preferred provider first
        if preferred and preferred in self.llm_providers:
            providers_to_try.append(preferred)
        
        # Try default provider
        if self.default_llm and self.default_llm not in providers_to_try:
            providers_to_try.append(self.default_llm)
        
        # Try all other providers
        for name in self.llm_providers:
            if name not in providers_to_try:
                providers_to_try.append(name)
        
        # Check availability in order
        for provider_name in providers_to_try:
            provider = self.llm_providers[provider_name]
            status = await provider.check_availability()
            
            if status == ProviderStatus.AVAILABLE:
                logger.info(f"Using LLM provider: {provider_name}")
                return provider
            else:
                logger.warning(f"LLM provider {provider_name} unavailable: {status}")
        
        logger.error("No available LLM providers")
        return None
    
    async def get_available_tts_provider(
        self, preferred: Optional[str] = None
    ) -> Optional[BaseTTSProvider]:
        """Get an available TTS provider, with fallback logic."""
        providers_to_try = []
        
        # Try preferred provider first
        if preferred and preferred in self.tts_providers:
            providers_to_try.append(preferred)
        
        # Try default provider
        if self.default_tts and self.default_tts not in providers_to_try:
            providers_to_try.append(self.default_tts)
        
        # Try all other providers
        for name in self.tts_providers:
            if name not in providers_to_try:
                providers_to_try.append(name)
        
        # Check availability in order
        for provider_name in providers_to_try:
            provider = self.tts_providers[provider_name]
            status = await provider.check_availability()
            
            if status == ProviderStatus.AVAILABLE:
                logger.info(f"Using TTS provider: {provider_name}")
                return provider
            else:
                logger.warning(f"TTS provider {provider_name} unavailable: {status}")
        
        logger.error("No available TTS providers")
        return None
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of all registered providers."""
        health_status = {
            "llm_providers": {},
            "tts_providers": {},
            "overall_status": "healthy"
        }
        
        # Check LLM providers
        for name, provider in self.llm_providers.items():
            try:
                status = await provider.check_availability()
                health_status["llm_providers"][name] = {
                    "status": status.value,
                    "last_error": provider.last_error.message if provider.last_error else None
                }
                
                if status != ProviderStatus.AVAILABLE:
                    health_status["overall_status"] = "degraded"
                    
            except Exception as e:
                health_status["llm_providers"][name] = {
                    "status": "error",
                    "last_error": str(e)
                }
                health_status["overall_status"] = "degraded"
        
        # Check TTS providers
        for name, provider in self.tts_providers.items():
            try:
                status = await provider.check_availability()
                health_status["tts_providers"][name] = {
                    "status": status.value,
                    "last_error": provider.last_error.message if provider.last_error else None
                }
                
                if status != ProviderStatus.AVAILABLE:
                    health_status["overall_status"] = "degraded"
                    
            except Exception as e:
                health_status["tts_providers"][name] = {
                    "status": "error",
                    "last_error": str(e)
                }
                health_status["overall_status"] = "degraded"
        
        return health_status