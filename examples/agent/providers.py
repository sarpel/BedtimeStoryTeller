from abc import ABC, abstractmethod

# --- LLM Provider Patterns ---
class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_story_stream(self, prompt: str):
        """Generates a story paragraph by paragraph (or sentence by sentence)."""
        pass

class OpenAIProvider(BaseLLMProvider):
    def generate_story_stream(self, prompt: str):
        print("Connecting to OpenAI to generate story...")
        # Gerçek OpenAI API çağrısı ve streaming mantığı burada olur.
        yield "Once upon a time, in a land far, far away,"
        yield "there lived a brave knight."

class OllamaProvider(BaseLLMProvider):
    def generate_story_stream(self, prompt: str):
        print("Connecting to local Ollama instance to generate story...")
        # Gerçek Ollama API çağrısı ve streaming mantığı burada olur.
        yield "In a cozy little burrow under a hill,"
        yield "slept a family of rabbits."

# --- TTS Provider Patterns ---
class BaseTTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Converts a text chunk into audio bytes."""
        pass

class OpenAITTSProvider(BaseTTSProvider):
    def synthesize(self, text: str) -> bytes:
        print(f"Synthesizing text: '{text[:20]}...'")
        # Gerçek TTS API çağrısı burada olur.
        return b"<mock_audio_bytes>"