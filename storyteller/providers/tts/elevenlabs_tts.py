"""
ElevenLabs TTS provider implementation with streaming support.
Implements high-quality, expressive text-to-speech synthesis.
"""

import asyncio
import logging
from typing import AsyncGenerator, List, Optional, Dict, Any
import httpx
from ..base import BaseTTSProvider, TTSRequest, ProviderStatus, ProviderError

logger = logging.getLogger(__name__)


class ElevenLabsTTSProvider(BaseTTSProvider):
    """ElevenLabs TTS provider for high-quality text-to-speech synthesis."""
    
    def __init__(self, api_key: str, voice_id: str = None, **kwargs):
        self.api_key = api_key
        self.default_voice_id = voice_id
        self.base_url = kwargs.get("base_url", "https://api.elevenlabs.io/v1")
        self.timeout = kwargs.get("timeout", 60)  # Longer timeout for higher quality
        self.max_retries = kwargs.get("max_retries", 3)
        
        super().__init__("elevenlabs", **kwargs)
    
    def _configure(self, **kwargs) -> None:
        """Configure ElevenLabs-specific settings."""
        self.headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Voice and model settings
        self.model_id = kwargs.get("model_id", "eleven_multilingual_v2")
        self.stability = kwargs.get("stability", 0.5)
        self.similarity_boost = kwargs.get("similarity_boost", 0.8)
        self.style = kwargs.get("style", 0.0)
        self.use_speaker_boost = kwargs.get("use_speaker_boost", True)
        
        # Output settings
        self.output_format = kwargs.get("output_format", "mp3_44100_128")
        
        # Rate limiting settings
        self.characters_per_month = kwargs.get("characters_per_month", 10000)
        self.requests_per_minute = kwargs.get("requests_per_minute", 20)
        self._request_times = []
        self._character_usage = 0
        
        # Available voices cache
        self._voices_cache = None
        self._cache_expiry = 0
    
    async def synthesize(self, request: TTSRequest) -> bytes:
        """
        Synthesize text to speech audio using ElevenLabs.
        
        Args:
            request: TTS synthesis request
            
        Returns:
            bytes: Audio data in specified format
        """
        try:
            # Rate limiting and usage check
            await self._check_limits(request.text)
            
            # Get voice ID
            voice_id = await self._get_voice_id(request.voice)
            
            # Prepare the API request
            payload = {
                "text": request.text,
                "model_id": self.model_id,
                "voice_settings": {
                    "stability": self.stability,
                    "similarity_boost": self.similarity_boost,
                    "style": self.style,
                    "use_speaker_boost": self.use_speaker_boost
                }
            }
            
            # Add output format to URL params
            params = {
                "output_format": self.output_format
            }
            
            # Make the API request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/text-to-speech/{voice_id}",
                    headers=self.headers,
                    params=params,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise ProviderError(
                        provider_name=self.name,
                        error_type="api_error",
                        message=f"ElevenLabs API error: {response.status_code} - {error_text}",
                        is_recoverable=response.status_code in [429, 500, 502, 503, 504]
                    )
                
                audio_data = await response.aread()
                
                # Update usage tracking
                self._update_usage(request.text)
                self.set_status(ProviderStatus.AVAILABLE)
                
                return audio_data
                
        except httpx.TimeoutException:
            error = ProviderError(
                provider_name=self.name,
                error_type="timeout",
                message="ElevenLabs API request timed out",
                is_recoverable=True
            )
            self.set_status(ProviderStatus.ERROR, error)
            raise error
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited or quota exceeded
                retry_after = int(e.response.headers.get("retry-after", "60"))
                error = ProviderError(
                    provider_name=self.name,
                    error_type="rate_limit",
                    message="ElevenLabs API rate limit or quota exceeded",
                    retry_after=retry_after,
                    is_recoverable=True
                )
                self.set_status(ProviderStatus.RATE_LIMITED, error)
            else:
                error = ProviderError(
                    provider_name=self.name,
                    error_type="http_error",
                    message=f"ElevenLabs API HTTP error: {e.response.status_code}",
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
        ElevenLabs supports true streaming synthesis.
        
        Args:
            request: TTS synthesis request
            
        Yields:
            bytes: Audio chunks
        """
        try:
            # Rate limiting and usage check
            await self._check_limits(request.text)
            
            # Get voice ID
            voice_id = await self._get_voice_id(request.voice)
            
            # Prepare the API request for streaming
            payload = {
                "text": request.text,
                "model_id": self.model_id,
                "voice_settings": {
                    "stability": self.stability,
                    "similarity_boost": self.similarity_boost,
                    "style": self.style,
                    "use_speaker_boost": self.use_speaker_boost
                }
            }
            
            # Add output format and streaming params
            params = {
                "output_format": self.output_format
            }
            
            # Make streaming request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/text-to-speech/{voice_id}/stream",
                    headers=self.headers,
                    params=params,
                    json=payload
                ) as response:
                    
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise ProviderError(
                            provider_name=self.name,
                            error_type="api_error",
                            message=f"ElevenLabs streaming API error: {response.status_code} - {error_text}",
                            is_recoverable=response.status_code in [429, 500, 502, 503, 504]
                        )
                    
                    # Stream audio chunks
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            yield chunk
                            # Small delay to prevent overwhelming the system
                            await asyncio.sleep(0.01)
            
            # Update usage tracking
            self._update_usage(request.text)
            self.set_status(ProviderStatus.AVAILABLE)
            
        except Exception as e:
            logger.error(f"Streaming synthesis failed: {e}")
            raise
    
    async def _get_voice_id(self, voice_name: Optional[str] = None) -> str:
        """
        Get voice ID from voice name or use default.
        
        Args:
            voice_name: Voice name or ID
            
        Returns:
            str: Voice ID
        """
        if not voice_name:
            if not self.default_voice_id:
                # Try to get a default voice from available voices
                voices = await self.get_available_voices()
                if voices:
                    return voices[0]["voice_id"]
                else:
                    raise ProviderError(
                        provider_name=self.name,
                        error_type="configuration",
                        message="No voice ID specified and no default voice available",
                        is_recoverable=False
                    )
            return self.default_voice_id
        
        # Check if it's already a voice ID (alphanumeric string)
        if len(voice_name) > 10 and voice_name.replace("-", "").replace("_", "").isalnum():
            return voice_name
        
        # Look up voice by name
        voices = await self.get_available_voices()
        for voice in voices:
            if voice["name"].lower() == voice_name.lower():
                return voice["voice_id"]
        
        # Fallback to default or raise error
        if self.default_voice_id:
            logger.warning(f"Voice '{voice_name}' not found, using default")
            return self.default_voice_id
        else:
            raise ProviderError(
                provider_name=self.name,
                error_type="voice_not_found",
                message=f"Voice '{voice_name}' not found and no default voice set",
                is_recoverable=False
            )
    
    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get list of available voices from ElevenLabs."""
        import time
        current_time = time.time()
        
        # Use cache if valid
        if self._voices_cache and current_time < self._cache_expiry:
            return self._voices_cache
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/voices",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    voices = data.get("voices", [])
                    
                    # Cache voices for 1 hour
                    self._voices_cache = voices
                    self._cache_expiry = current_time + 3600
                    
                    return voices
                else:
                    logger.warning(f"Failed to fetch voices: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.warning(f"Error fetching voices: {e}")
            return []
    
    async def _check_limits(self, text: str) -> None:
        """Check rate limits and character usage before making a request."""
        import time
        current_time = time.time()
        
        # Clean old request times (older than 1 minute)
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
        
        # Check character usage (rough monthly limit)
        text_length = len(text)
        if self._character_usage + text_length > self.characters_per_month:
            raise ProviderError(
                provider_name=self.name,
                error_type="quota_exceeded",
                message="Monthly character quota exceeded",
                retry_after=None,
                is_recoverable=False
            )
    
    def _update_usage(self, text: str) -> None:
        """Update usage tracking after a successful request."""
        import time
        self._request_times.append(time.time())
        self._character_usage += len(text)
    
    async def check_availability(self) -> ProviderStatus:
        """Check if ElevenLabs API is available."""
        try:
            # Test with a simple user info request
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/user",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    self.set_status(ProviderStatus.AVAILABLE)
                    return ProviderStatus.AVAILABLE
                elif response.status_code == 429:
                    return ProviderStatus.RATE_LIMITED
                else:
                    return ProviderStatus.ERROR
                    
        except Exception as e:
            logger.warning(f"ElevenLabs availability check failed: {e}")
            return ProviderStatus.UNAVAILABLE
    
    def get_supported_voices(self) -> List[str]:
        """Get list of supported voice names (cached)."""
        if self._voices_cache:
            return [voice["name"] for voice in self._voices_cache]
        else:
            return []
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        return {
            "provider": "elevenlabs",
            "model_id": self.model_id,
            "default_voice_id": self.default_voice_id,
            "supported_formats": ["mp3_44100_128", "mp3_22050_32", "pcm_16000", "pcm_22050", "pcm_24000"],
            "languages_supported": ["en", "tr", "es", "fr", "de", "it", "pt", "pl", "hi", "ar", "zh", "ja", "ko"],
            "streaming": True,
            "voice_cloning": True,
            "max_text_length": 2500,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "style": self.style,
                "use_speaker_boost": self.use_speaker_boost
            }
        }
    
    async def get_voice_info(self, voice_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific voice."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/voices/{voice_id}",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"Voice {voice_id} not found"}
                    
        except Exception as e:
            return {"error": f"Error fetching voice info: {str(e)}"}
    
    async def get_user_info(self) -> Dict[str, Any]:
        """Get user subscription and usage information."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/user",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": "Failed to fetch user info"}
                    
        except Exception as e:
            return {"error": f"Error fetching user info: {str(e)}"}