import pytest
from unittest.mock import MagicMock

# Base sınıflarını import ederek 'spec' özelliğini kullanabiliriz.
# Bu, mock nesnelerin sadece orijinal sınıfta var olan metodları
# taklit etmesini sağlar ve testlerin güvenilirliğini artırır.
from agent.providers import BaseLLMProvider, BaseTTSProvider

@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """
    BaseLLMProvider arayüzünü taklit eden sahte bir LLM provider'ı
    oluşturan bir pytest fixture'ı.
    """
    # MagicMock, esnek bir sahte nesne oluşturur.
    mock = MagicMock(spec=BaseLLMProvider)
    
    # Testlerde kolaylık olması için varsayılan bir dönüş değeri ayarlayabiliriz.
    # Bu değer, her test içinde ayrıca özelleştirilebilir.
    mock.generate_story_stream.return_value = ["Once upon a time...", "The end."]
    return mock

@pytest.fixture
def mock_tts_provider() -> MagicMock:
    """
    BaseTTSProvider arayüzünü taklit eden sahte bir TTS provider'ı
    oluşturan bir pytest fixture'ı.
    """
    mock = MagicMock(spec=BaseTTSProvider)
    mock.synthesize.return_value = b"<mock_audio_bytes_from_fixture>"
    return mock