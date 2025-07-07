"""
Pytest configuration and shared fixtures for Bedtime Storyteller tests.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

# Set test environment
os.environ["TESTING"] = "1"
os.environ["LOG_LEVEL"] = "DEBUG"

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)

@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch('storyteller.config.settings.get_settings') as mock:
        mock_settings = MagicMock()
        mock_settings.debug = True
        mock_settings.log_level = "DEBUG"
        mock_settings.max_memory_mb = 400
        mock_settings.wakeword_engine = "porcupine"
        mock_settings.story_language = "tr"
        mock_settings.story_age_rating = "5+"
        mock_settings.story_max_paragraphs = 10
        mock_settings.content_safety_enabled = True
        mock_settings.openai_api_key = "test-openai-key"
        mock_settings.porcupine_access_key = "test-porcupine-key"
        mock_settings.database_url = "sqlite+aiosqlite:///:memory:"
        mock_settings.default_llm_provider = "openai"
        mock_settings.default_tts_provider = "openai"
        mock_settings.openai_model = "gpt-3.5-turbo"
        mock_settings.openai_tts_model = "tts-1"
        mock_settings.openai_tts_voice = "alloy"
        mock.return_value = mock_settings
        yield mock_settings

@pytest.fixture
async def test_database(temp_dir: Path) -> AsyncGenerator[AsyncEngine, None]:
    """Create a test database."""
    from storyteller.storage.models import create_database_engine, create_tables
    
    db_path = temp_dir / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    
    engine = await create_database_engine(db_url)
    await create_tables(engine)
    
    yield engine
    
    await engine.dispose()

@pytest.fixture
def mock_audio_device():
    """Mock audio device for testing."""
    mock_device = AsyncMock()
    mock_device.initialize = AsyncMock()
    mock_device.cleanup = AsyncMock()
    mock_device.is_available = True
    mock_device.sample_rate = 16000
    mock_device.channels = 1
    mock_device.format = "int16"
    mock_device.play_audio = AsyncMock()
    mock_device.record_audio = AsyncMock(return_value=b'fake_audio_data')
    mock_device.get_status = AsyncMock(return_value={
        "available": True,
        "sample_rate": 16000,
        "channels": 1
    })
    return mock_device

@pytest.fixture
def mock_gpio_manager():
    """Mock GPIO manager for testing."""
    mock_gpio = AsyncMock()
    mock_gpio.initialize = AsyncMock()
    mock_gpio.cleanup = AsyncMock()
    mock_gpio.setup_button = AsyncMock()
    mock_gpio.setup_led = AsyncMock()
    mock_gpio.set_led = AsyncMock()
    mock_gpio.blink_led = AsyncMock()
    mock_gpio.get_status = AsyncMock(return_value={
        "initialized": True,
        "buttons": [],
        "leds": []
    })
    return mock_gpio

@pytest.fixture
def mock_hardware_manager(mock_audio_device, mock_gpio_manager):
    """Mock hardware manager for testing."""
    mock_hw = AsyncMock()
    mock_hw.initialize = AsyncMock()
    mock_hw.cleanup = AsyncMock()
    mock_hw.audio = mock_audio_device
    mock_hw.gpio = mock_gpio_manager
    mock_hw.get_status = AsyncMock(return_value={
        "audio": {"available": True},
        "gpio": {"initialized": True}
    })
    mock_hw.test_hardware = AsyncMock(return_value={
        "audio": {"playback": True, "recording": True},
        "gpio": {"button": True, "led": True}
    })
    return mock_hw

@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing."""
    mock_provider = AsyncMock()
    mock_provider.name = "test_llm"
    mock_provider.is_available = AsyncMock(return_value=True)
    mock_provider.generate_story_stream = AsyncMock()
    mock_provider.health_check = AsyncMock(return_value={
        "status": "healthy",
        "response_time": 0.5
    })
    
    # Mock async generator for story streaming
    async def mock_story_generator():
        yield "Once upon a time, there was a little cat."
        yield "The cat lived in a beautiful garden."
        yield "Every day, the cat would play with butterflies."
        yield "And they all lived happily ever after."
    
    mock_provider.generate_story_stream.return_value = mock_story_generator()
    return mock_provider

@pytest.fixture
def mock_tts_provider():
    """Mock TTS provider for testing."""
    mock_provider = AsyncMock()
    mock_provider.name = "test_tts"
    mock_provider.is_available = AsyncMock(return_value=True)
    mock_provider.synthesize_speech = AsyncMock(return_value=b'fake_audio_data')
    mock_provider.health_check = AsyncMock(return_value={
        "status": "healthy",
        "response_time": 0.3
    })
    return mock_provider

@pytest.fixture
def mock_provider_manager(mock_llm_provider, mock_tts_provider):
    """Mock provider manager for testing."""
    mock_manager = AsyncMock()
    mock_manager.llm_providers = {"test_llm": mock_llm_provider}
    mock_manager.tts_providers = {"test_tts": mock_tts_provider}
    mock_manager.get_default_llm_provider = AsyncMock(return_value=mock_llm_provider)
    mock_manager.get_default_tts_provider = AsyncMock(return_value=mock_tts_provider)
    mock_manager.register_llm_provider = AsyncMock()
    mock_manager.register_tts_provider = AsyncMock()
    mock_manager.health_check = AsyncMock(return_value={
        "overall_status": "healthy",
        "llm": {"test_llm": {"status": "healthy"}},
        "tts": {"test_tts": {"status": "healthy"}}
    })
    return mock_manager

@pytest.fixture
def mock_wakeword_engine():
    """Mock wakeword engine for testing."""
    mock_engine = AsyncMock()
    mock_engine.initialize = AsyncMock()
    mock_engine.cleanup = AsyncMock()
    mock_engine.start_listening = AsyncMock()
    mock_engine.stop_listening = AsyncMock()
    mock_engine.process_audio = AsyncMock(return_value=None)
    mock_engine.is_listening = True
    mock_engine.keywords = ["test_keyword"]
    return mock_engine

@pytest.fixture
def mock_safety_filter():
    """Mock safety filter for testing."""
    mock_filter = MagicMock()
    mock_filter.is_content_safe = MagicMock(return_value=True)
    mock_filter.filter_content = MagicMock(side_effect=lambda x: x)  # Return content unchanged
    mock_filter.get_safety_score = MagicMock(return_value=0.9)
    return mock_filter

@pytest.fixture
async def mock_story_library(test_database):
    """Mock story library for testing."""
    from storyteller.storage.story_library import StoryLibrary
    from storyteller.storage.models import get_database_session
    
    session = await get_database_session(test_database)
    library = StoryLibrary(session)
    return library

@pytest.fixture
def sample_story_request():
    """Sample story request for testing."""
    from storyteller.core.story_generator import StoryRequest
    
    return StoryRequest(
        prompt="Tell me a story about a brave little mouse",
        language="en",
        age_rating="5+",
        max_paragraphs=5
    )

@pytest.fixture
def sample_audio_data():
    """Sample audio data for testing."""
    # Generate simple sine wave data for testing
    import struct
    import math
    
    sample_rate = 16000
    duration = 1.0  # 1 second
    frequency = 440  # A4 note
    
    samples = []
    for i in range(int(sample_rate * duration)):
        value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(struct.pack('<h', value))
    
    return b''.join(samples)

@pytest.fixture
def mock_file_system(temp_dir):
    """Mock file system operations."""
    def mock_path_exists(path):
        # Mock certain paths as existing
        mock_paths = [
            "/proc/device-tree/model",
            "/proc/cpuinfo",
            "/etc/os-release"
        ]
        return str(path) in mock_paths or str(path).startswith(str(temp_dir))
    
    with patch('pathlib.Path.exists', side_effect=mock_path_exists):
        yield temp_dir

# Test data fixtures
@pytest.fixture
def turkish_story_prompts():
    """Sample Turkish story prompts for testing."""
    return [
        "Küçük bir kedi hakkında hikaye",
        "Orman hayvanları ve dostluk",
        "Büyülü bir bahçede macera",
        "Cesur fare ve peynir hazinesi"
    ]

@pytest.fixture
def english_story_prompts():
    """Sample English story prompts for testing."""
    return [
        "A story about a little cat",
        "Forest animals and friendship", 
        "Adventure in a magical garden",
        "Brave mouse and cheese treasure"
    ]

# Async test helpers
class AsyncContextManager:
    """Helper for testing async context managers."""
    
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj
    
    async def __aenter__(self):
        return self.mock_obj
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

@pytest.fixture
def async_context_manager():
    """Helper for creating async context managers in tests."""
    return AsyncContextManager

# Performance testing fixtures
@pytest.fixture
def performance_monitor():
    """Monitor performance metrics during tests."""
    import time
    import psutil
    
    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.start_memory = None
            
        def start(self):
            self.start_time = time.time()
            self.start_memory = psutil.Process().memory_info().rss
            
        def stop(self):
            if self.start_time is None:
                return {}
            
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss
            
            return {
                "duration": end_time - self.start_time,
                "memory_delta": end_memory - self.start_memory,
                "peak_memory": psutil.Process().memory_info().rss
            }
    
    return PerformanceMonitor()

# Hardware simulation fixtures
@pytest.fixture
def mock_raspberry_pi():
    """Mock Raspberry Pi environment."""
    with patch('platform.machine', return_value='aarch64'), \
         patch('os.path.exists') as mock_exists:
        
        def exists_side_effect(path):
            pi_paths = [
                '/proc/device-tree/model',
                '/dev/gpiomem',
                '/sys/class/gpio'
            ]
            return path in pi_paths
        
        mock_exists.side_effect = exists_side_effect
        
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "Raspberry Pi Zero 2 W"
            yield

# Error simulation fixtures
@pytest.fixture
def network_error():
    """Simulate network errors."""
    import httpx
    return httpx.ConnectError("Network unreachable")

@pytest.fixture
def api_error():
    """Simulate API errors."""
    import httpx
    return httpx.HTTPStatusError(
        "API Error",
        request=MagicMock(),
        response=MagicMock(status_code=429)
    )