from agent.providers import BaseLLMProvider, BaseTTSProvider, OpenAIProvider, OpenAITTSProvider
from agent.audio_player import AudioPlayer
import asyncio

class StorytellingAgent:
    def __init__(self, llm_provider: BaseLLMProvider, tts_provider: BaseTTSProvider):
        self.llm = llm_provider
        self.tts = tts_provider
        self.player = AudioPlayer()

    async def tell_story(self, prompt: str):
        """Generates and plays a story paragraph by paragraph."""
        story_stream = self.llm.generate_story_stream(prompt)
        
        for paragraph in story_stream:
            print(f"Received paragraph: {paragraph}")
            audio_data = self.tts.synthesize(paragraph)
            print("Playing audio chunk...")
            self.player.play(audio_data)

# --- Main execution example ---
async def main():
    # Bu desen, provider'ların kolayca değiştirilebilmesini sağlar.
    llm_provider = OpenAIProvider()
    tts_provider = OpenAITTSProvider()
    
    agent = StorytellingAgent(llm_provider, tts_provider)
    await agent.tell_story("A story about a robot who wants to be a gardener.")

if __name__ == "__main__":
    asyncio.run(main())