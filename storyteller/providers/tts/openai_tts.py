"""
OpenAI TTS provider implementation with streaming support.
Implements high-quality text-to-speech synthesis with Turkish language support.
"""

import asyncio
import logging
from typing import AsyncGenerator, List, Optional, Dict, Any
import httpx
from ..base import BaseTTSProvider, TTSRequest, ProviderStatus, ProviderError

logger = logging.getLogger(__name__)


class OpenAITTSProvider(BaseTTSProvider):
    """OpenAI TTS provider for text-to-speech synthesis."""
    
    def __init__(self, api_key: str, model: str = "tts-1", voice: str = "alloy", **kwargs):
        self.api_key = api_key
        self.model = model
        self.default_voice = voice
        self.base_url = kwargs.get("base_url", "https://api.openai.com/v1")
        self.timeout = kwargs.get("timeout", 30)
        self.max_retries = kwargs.get("max_retries", 3)
        
        super().__init__("openai_tts", **kwargs)
    
    def _configure(self, **kwargs) -> None:
        """Configure OpenAI TTS-specific settings."""
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Supported voices for OpenAI TTS
        self.supported_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        
        # Quality settings
        self.response_format = kwargs.get("response_format", "mp3")
        self.speed = kwargs.get("speed", 1.0)
        
        # Rate limiting settings
        self.requests_per_minute = kwargs.get("requests_per_minute", 50)
        self._request_times = []
        
        # Turkish language-specific voice mapping
        self.turkish_voice_preferences = {
            "female": "nova",
            "male": "onyx",
            "neutral": "alloy"
        }
    
    async def synthesize(self, request: TTSRequest) -> bytes:
        """
        Synthesize text to speech audio.
        
        Args:
            request: TTS synthesis request
            
        Returns:
            bytes: Audio data in MP3 format
        """
        try:
            # Rate limiting check
            await self._check_rate_limits()
            
            # Prepare voice selection
            voice = await self._select_voice(request)
            
            # Prepare the API request
            payload = {
                "model": self.model,
                "input": request.text,
                "voice": voice,
                "response_format": request.format or self.response_format,
                "speed": request.speed
            }
            
            # Make the API request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/audio/speech",
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise ProviderError(
                        provider_name=self.name,
                        error_type="api_error",
                        message=f"OpenAI TTS API error: {response.status_code} - {error_text}",
                        is_recoverable=response.status_code in [429, 500, 502, 503, 504]
                    )
                
                audio_data = await response.aread()
                
                # Update rate limiting tracking
                self._update_rate_limiting()
                self.set_status(ProviderStatus.AVAILABLE)
                
                return audio_data
                
        except httpx.TimeoutException:
            error = ProviderError(
                provider_name=self.name,
                error_type="timeout",
                message="OpenAI TTS API request timed out",
                is_recoverable=True
            )
            self.set_status(ProviderStatus.ERROR, error)
            raise error
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited
                retry_after = int(e.response.headers.get("retry-after", "60"))
                error = ProviderError(
                    provider_name=self.name,
                    error_type="rate_limit",
                    message="OpenAI TTS API rate limit exceeded",
                    retry_after=retry_after,
                    is_recoverable=True
                )
                self.set_status(ProviderStatus.RATE_LIMITED, error)
            else:
                error = ProviderError(
                    provider_name=self.name,
                    error_type="http_error",
                    message=f"OpenAI TTS API HTTP error: {e.response.status_code}",
                    is_recoverable=e.response.status_code in [500, 502, 503, 504]
                )
                self.set_status(ProviderStatus.ERROR, error)
            raise error
            
        except Exception as e:
            error = ProviderError(
                provider_name=self.name,
                error_type="unknown",
                message=f"Unexpected error: {str(e)}",
                is_recoverable=False
            )
            self.set_status(ProviderStatus.ERROR, error)
            raise error
    
    async def synthesize_stream(
        self, request: TTSRequest
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesize text to speech as a streaming response.
        Note: OpenAI TTS doesn't support true streaming, so we chunk the text.
        
        Args:
            request: TTS synthesis request
            
        Yields:
            bytes: Audio chunks
        """
        try:
            # Split text into chunks for pseudo-streaming
            chunks = self._split_text_into_chunks(request.text)
            
            for chunk in chunks:
                chunk_request = TTSRequest(
                    text=chunk,
                    voice=request.voice,
                    language=request.language,
                    speed=request.speed,
                    format=request.format
                )
                
                audio_data = await self.synthesize(chunk_request)
                yield audio_data
                
                # Small delay between chunks
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Streaming synthesis failed: {e}")
            raise
    
    def _split_text_into_chunks(self, text: str, max_chunk_size: int = 300) -> List[str]:
        """
        Split text into chunks for pseudo-streaming synthesis.
        
        Args:
            text: Text to split
            max_chunk_size: Maximum characters per chunk
            
        Returns:
            List of text chunks
        """
        chunks = []
        sentences = text.split('. ')
        current_chunk = ""
        
        for sentence in sentences:
            # Add sentence to current chunk if it fits
            if len(current_chunk + sentence) <= max_chunk_size:
                if current_chunk:
                    current_chunk += ". " + sentence
                else:
                    current_chunk = sentence
            else:
                # Current chunk is ready, start new one
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    async def _select_voice(self, request: TTSRequest) -> str:
        """
        Select appropriate voice based on request and language.
        
        Args:
            request: TTS synthesis request
            
        Returns:
            str: Selected voice name
        """
        # Use voice from request if specified and supported
        if request.voice and request.voice in self.supported_voices:
            return request.voice
        
        # Use default voice if no preference
        if not request.voice:
            return self.default_voice
        
        # For Turkish language, prefer certain voices
        if request.language == "tr":
            # Try to map voice preference to Turkish-friendly options
            if request.voice in self.turkish_voice_preferences:
                return self.turkish_voice_preferences[request.voice]
            else:
                return self.turkish_voice_preferences["neutral"]
        
        # Fallback to default
        return self.default_voice
    
    async def _check_rate_limits(self) -> None:
        """Check if we're within rate limits before making a request."""
        import time
        current_time = time.time()
        
        # Clean old entries (older than 1 minute)
        self._request_times = [
            t for t in self._request_times 
            if current_time - t < 60
        ]
        
        # Check request rate limit
        if len(self._request_times) >= self.requests_per_minute:
            raise ProviderError(
                provider_name=self.name,
                error_type="rate_limit",
                message="Request rate limit exceeded",
                retry_after=60,
                is_recoverable=True
            )
    
    def _update_rate_limiting(self) -> None:
        """Update rate limiting tracking after a successful request."""
        import time
        self._request_times.append(time.time())
    
    async def check_availability(self) -> ProviderStatus:
        """Check if OpenAI TTS API is available."""
        try:
            # Test with a minimal request
            test_request = TTSRequest(
                text="Hello",
                language="en"
            )
            
            # Try to synthesize a very short test
            await self.synthesize(test_request)
            
            self.set_status(ProviderStatus.AVAILABLE)
            return ProviderStatus.AVAILABLE
            
        except ProviderError as e:
            if e.error_type == "rate_limit":
                return ProviderStatus.RATE_LIMITED
            else:
                return ProviderStatus.ERROR
        except Exception as e:
            logger.warning(f"OpenAI TTS availability check failed: {e}")
            return ProviderStatus.UNAVAILABLE
    
    def get_supported_voices(self) -> List[str]:
        """Get list of supported voice names."""
        return self.supported_voices.copy()
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        return {
            "provider": "openai_tts",
            "model": self.model,
            "default_voice": self.default_voice,
            "supported_voices": self.supported_voices,
            "supported_formats": ["mp3", "opus", "aac", "flac"],
            "languages_supported": ["tr", "en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh"],
            "streaming": False,  # Pseudo-streaming via chunking
            "max_text_length": 4096
        }
    
    def get_voice_info(self, voice_name: str) -> Dict[str, Any]:
        """Get information about a specific voice."""
        voice_descriptions = {
            "alloy": "Neutral, balanced voice suitable for most content",
            "echo": "Male voice with clear pronunciation",
            "fable": "Female voice with expressive intonation",
            "onyx": "Deep male voice with authoritative tone",
            "nova": "Female voice with warm, friendly tone",
            "shimmer": "Female voice with bright, energetic tone"
        }
        
        if voice_name not in self.supported_voices:
            return {"error": f"Voice '{voice_name}' not supported"}
        
        return {
            "name": voice_name,
            "description": voice_descriptions.get(voice_name, "No description available"),
            "gender": self._get_voice_gender(voice_name),
            "suitable_for_turkish": voice_name in ["nova", "alloy", "onyx"]
        }
    
    def _get_voice_gender(self, voice_name: str) -> str:
        """Get gender classification for voice."""
        female_voices = ["fable", "nova", "shimmer"]
        male_voices = ["echo", "onyx"]
        
        if voice_name in female_voices:
            return "female"
        elif voice_name in male_voices:
            return "male"
        else:
            return "neutral"