import pytest
import asyncio
from unittest.mock import patch, MagicMock
from agent.agent import StorytellingAgent

# `conftest.py`'de tanımlanan fixture'lar, test fonksiyonlarına
# sadece argüman olarak eklenerek otomatik olarak kullanılır.
# Bu sayede her testte tekrar tekrar mock nesnesi oluşturmaya gerek kalmaz.

def test_tell_story_orchestration(mock_llm_provider, mock_tts_provider):
    """
    Agent'ın LLM ve TTS provider'larını doğru sırada ve doğru verilerle
    çağırıp çağırmadığını test eder.
    """
    # Arrange: 
    # Fixture'lar tarafından sağlanan mock provider'ların dönüş değerlerini bu teste özel olarak ayarlayalım.
    mock_llm_provider.generate_story_stream.return_value = ["Chapter 1.", "Chapter 2."]
    mock_tts_provider.synthesize.side_effect = [b"<audio1>", b"<audio2>"]
    
    # AudioPlayer'ı patch'leyerek instance'ını yakalayalım.
    mock_player_instance = MagicMock()
    with patch('agent.agent.AudioPlayer', return_value=mock_player_instance):
        # Act: Agent'ı fixture'dan gelen mock'larla başlat ve metodu çağır.
        agent = StorytellingAgent(
            llm_provider=mock_llm_provider, 
            tts_provider=mock_tts_provider
        )
        asyncio.run(agent.tell_story("a test prompt"))

    # Assert: Tüm etkileşimlerin beklendiği gibi olduğunu doğrula.
    mock_llm_provider.generate_story_stream.assert_called_once_with("a test prompt")
    
    assert mock_tts_provider.synthesize.call_count == 2
    mock_tts_provider.synthesize.assert_any_call("Chapter 1.")
    mock_tts_provider.synthesize.assert_any_call("Chapter 2.")

    assert mock_player_instance.play.call_count == 2
    mock_player_instance.play.assert_any_call(b"<audio1>")
    mock_player_instance.play.assert_any_call(b"<audio2>")