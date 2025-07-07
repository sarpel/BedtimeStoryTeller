## EXAMPLES:

In the `examples/` folder, there is a README for you to read to understand what the example is all about and also how to structure your own README when you create documentation for the above feature.

-   **`cli_pattern.py`**: `argparse` veya `click` gibi kütüphanelerle komut satırı arayüzü oluşturma ve argümanları (örneğin hikaye konusu) nasıl yöneteceğinizi gösterir.
-   **`agent/`**: Projenin ana iş mantığını oluşturan "Agent" mimarisini sergiler.
    -   **`agent/agent.py`**: Bir hikaye istemini alıp, metin oluşturma ve seslendirme adımlarını asenkron olarak nasıl yöneteceğini gösteren ana sınıfı içerir.
    -   **`agent/providers.py`**: OpenAI, Google Gemini, Ollama gibi farklı LLM (Büyük Dil Modeli) veya ElevenLabs gibi TTS (Text-to-Speech) sağlayıcıları arasında geçiş yapmayı kolaylaştıran bir "provider" deseni sunar. Bu, projenin esnekliğini artırır.
    -   **`agent/audio_player.py`**: Üretilen ses dosyasını (`mp3`, `wav` vb.) oynatmak için temel bir oynatıcı sınıfı deseni gösterir.
-   **`tests/`**: Test yazma konusundaki standartları belirler.
    -   **`test_agent.py`**: Harici API çağrıları yapan `agent.py`'nin, `unittest.mock` kullanarak nasıl izole bir şekilde test edileceğini gösterir. Bu, API'lere gerçekten bağlanmadan hızlı ve güvenilir testler yazmanızı sağlar.
    -   **`conftest.py`**: `pytest` için tekrar kullanılabilir "fixture"lar (örneğin, sahte provider nesneleri) tanımlayarak testlerin daha temiz ve okunaklı olmasını sağlar.

Don't copy any of these examples directly, it is for a different project entirely. But use this as inspiration and for best practices.