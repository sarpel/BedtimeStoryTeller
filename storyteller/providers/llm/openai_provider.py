"""
OpenAI LLM provider implementation with streaming support.
Implements Turkish story generation with safety filtering and rate limiting.
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional, Dict, Any
import httpx
from ..base import BaseLLMProvider, StoryRequest, ProviderStatus, ProviderError

logger = logging.getLogger(__name__)


class OpenAILLMProvider(BaseLLMProvider):
    """OpenAI GPT provider for story generation."""
    
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo", **kwargs):
        self.api_key = api_key
        self.model = model
        self.base_url = kwargs.get("base_url", "https://api.openai.com/v1")
        self.timeout = kwargs.get("timeout", 30)
        self.max_retries = kwargs.get("max_retries", 3)
        self.max_tokens = kwargs.get("max_tokens", 1500)
        self.temperature = kwargs.get("temperature", 0.7)
        
        super().__init__("openai", **kwargs)
    
    def _configure(self, **kwargs) -> None:
        """Configure OpenAI-specific settings."""
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Rate limiting settings
        self.requests_per_minute = kwargs.get("requests_per_minute", 20)
        self.tokens_per_minute = kwargs.get("tokens_per_minute", 40000)
        self._request_times = []
        self._token_usage = []
    
    async def generate_story_stream(
        self, request: StoryRequest
    ) -> AsyncGenerator[str, None]:
        """
        Generate a story using OpenAI's streaming API.
        
        Args:
            request: Story generation request
            
        Yields:
            str: Individual paragraphs of the story
        """
        try:
            # Rate limiting check
            await self._check_rate_limits()
            
            # Get safety-filtered prompt
            safe_prompt = await self.get_safety_filtered_prompt(request)
            
            # Prepare the API request
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a gentle storyteller who creates age-appropriate bedtime stories."
                    },
                    {
                        "role": "user", 
                        "content": safe_prompt
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "stream": True,
                "n": 1
            }
            
            # Make streaming request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload
                ) as response:
                    
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise ProviderError(
                            provider_name=self.name,
                            error_type="api_error",
                            message=f"OpenAI API error: {response.status_code} - {error_text}",
                            is_recoverable=response.status_code in [429, 500, 502, 503, 504]
                        )
                    
                    # Process streaming response
                    current_paragraph = ""
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix
                            
                            if data_str.strip() == "[DONE]":
                                # Yield final paragraph if any
                                if current_paragraph.strip():
                                    yield current_paragraph.strip()
                                break
                            
                            try:
                                import json
                                data = json.loads(data_str)
                                
                                if "choices" in data and len(data["choices"]) > 0:
                                    choice = data["choices"][0]
                                    
                                    if "delta" in choice and "content" in choice["delta"]:
                                        content = choice["delta"]["content"]
                                        current_paragraph += content
                                        
                                        # Check if we have a complete paragraph
                                        if self._is_paragraph_complete(current_paragraph):
                                            yield current_paragraph.strip()
                                            current_paragraph = ""
                                            
                                            # Small delay to avoid overwhelming the system
                                            await asyncio.sleep(0.1)
                                            
                            except json.JSONDecodeError:
                                # Skip malformed JSON lines
                                continue
            
            # Update rate limiting tracking
            self._update_rate_limiting()
            self.set_status(ProviderStatus.AVAILABLE)
            
        except httpx.TimeoutException:
            error = ProviderError(
                provider_name=self.name,
                error_type="timeout",
                message="OpenAI API request timed out",
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
                    message="OpenAI API rate limit exceeded",
                    retry_after=retry_after,
                    is_recoverable=True
                )
                self.set_status(ProviderStatus.RATE_LIMITED, error)
            else:
                error = ProviderError(
                    provider_name=self.name,
                    error_type="http_error",
                    message=f"OpenAI API HTTP error: {e.response.status_code}",
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
    
    def _is_paragraph_complete(self, text: str) -> bool:
        """
        Check if the current text represents a complete paragraph.
        
        Args:
            text: Current accumulated text
            
        Returns:
            bool: True if paragraph appears complete
        """
        # Simple heuristic: paragraph ends with period, exclamation, or question mark
        # followed by whitespace or double newline
        text = text.strip()
        
        if not text:
            return False
        
        # Check for sentence-ending punctuation
        if text.endswith(('.', '!', '?')):
            return True
        
        # Check for double newline (paragraph break)
        if '\n\n' in text:
            return True
        
        # Check for minimum length to avoid very short paragraphs
        if len(text) > 150 and text.endswith(('.', '!', '?', ':')):
            return True
        
        return False
    
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
        """Check if OpenAI API is available."""
        try:
            # Simple ping to check API availability
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/models",
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
            logger.warning(f"OpenAI availability check failed: {e}")
            return ProviderStatus.UNAVAILABLE
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        return {
            "provider": "openai",
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "streaming": True,
            "languages_supported": ["tr", "en"],
            "safety_filtering": True
        }