examples/
├── README.md           # Her bir örneğin neyi gösterdiğini açıklar.
├── cli_pattern.py      # Basit bir CLI (Komut Satırı Arayüzü) kullanım örneği.
├── agent/              # Ana mantığın ve mimari desenlerin bulunduğu klasör.
│   ├── agent.py        # Hikaye oluşturma sürecini yöneten ana Agent sınıfı.
│   ├── providers.py    # Farklı yapay zeka sağlayıcılarını (OpenAI, Ollama vb.) yöneten desen.
│   └── audio_player.py # Ses dosyalarını platform bağımsız oynatma deseni.
└── tests/              # Test desenlerinin gösterildiği klasör.
    ├── test_agent.py   # Agent'ın iş mantığını test etme (mocking ile).
    └── conftest.py     # Pytest için genel ayarlar ve fixture'lar.