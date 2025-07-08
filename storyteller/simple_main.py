#!/usr/bin/env python3
"""
Simplified main entry point for Bedtime Storyteller without CLI dependencies.
This ensures the service can start without click/CLI issues.
"""

import asyncio
import logging
import signal
import sys
import os
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from .config.settings import get_settings, reload_settings
from .config.hardware_profiles import detect_hardware_profile
from .providers.base import ProviderManager
from .providers.llm.openai_provider import OpenAILLMProvider
from .providers.llm.gemini_provider import GeminiLLMProvider
from .providers.tts.openai_tts import OpenAITTSProvider
from .providers.tts.elevenlabs_tts import ElevenLabsTTSProvider
from .wakeword.loader import load_wakeword_engine
from .hal.interface import HardwareManager
from .hal.audio_devices import create_audio_device
from .hal.gpio_manager import create_gpio_manager
from .core.agent import StorytellingAgent
from .storage.models import create_database_engine, create_tables
from .storage.story_library import StoryLibrary
from .utils.safety_filter import SafetyFilter

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StorytellerApplication:
    """Main application class for Bedtime Storyteller."""
    
    def __init__(self):
        self.settings = get_settings()
        self.hardware_manager = HardwareManager()
        self.provider_manager = ProviderManager()
        self.safety_filter = SafetyFilter(
            target_age=int(self.settings.story_age_rating.replace('+', '')),
            language=self.settings.story_language,
            enabled=self.settings.content_safety_enabled
        )
        self.agent = None
        self.story_library = None
        self.database_engine = None
        self.web_app = None
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> None:
        """Initialize all application components."""
        try:
            logger.info("Initializing Bedtime Storyteller...")
            
            # Initialize database
            await self._initialize_database()
            
            # Initialize hardware with fallbacks
            await self._initialize_hardware()
            
            # Initialize providers
            await self._initialize_providers()
            
            # Initialize agent
            await self._initialize_agent()
            
            # Initialize web interface
            await self._initialize_web()
            
            logger.info("Bedtime Storyteller initialized successfully")
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            raise
    
    async def _initialize_database(self) -> None:
        """Initialize database."""
        try:
            logger.info("Initializing database...")
            
            # Create database engine
            self.database_engine = await create_database_engine(self.settings.database_url)
            
            # Create tables
            await create_tables(self.database_engine)
            logger.info("Database initialized")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _initialize_hardware(self) -> None:
        """Initialize hardware components with graceful fallbacks."""
        try:
            logger.info("Initializing hardware...")
            
            # Detect hardware profile
            hardware_profile = detect_hardware_profile()
            logger.info(f"Detected hardware profile: {hardware_profile.model.value}")
            
            # Create audio device with fallback
            audio_device = None
            
            # Check if mock hardware is forced
            if self.settings.force_mock_hardware:
                logger.info("Mock hardware forced via configuration")
                from .hal.audio_devices import MockAudioDevice
                audio_device = MockAudioDevice(hardware_profile.audio)
                await audio_device.initialize()
                logger.info("Mock audio device initialized (forced)")
            else:
                try:
                    audio_device = await create_audio_device(hardware_profile.audio)
                    await audio_device.initialize()
                    logger.info("Audio device initialized successfully")
                except Exception as audio_error:
                    logger.warning(f"Audio initialization failed: {audio_error}")
                    logger.info("Falling back to mock audio device...")
                    
                    from .hal.audio_devices import MockAudioDevice
                    audio_device = MockAudioDevice(hardware_profile.audio)
                    await audio_device.initialize()
                    logger.info("Mock audio device initialized (no audio hardware)")
            
            # Create GPIO manager with fallback
            gpio_manager = None
            
            if self.settings.force_mock_hardware:
                logger.info("Mock GPIO forced via configuration")
                from .hal.gpio_manager import MockGPIOManager
                gpio_manager = MockGPIOManager()
                await gpio_manager.initialize()
                logger.info("Mock GPIO manager initialized (forced)")
            else:
                try:
                    gpio_manager = await create_gpio_manager()
                    await gpio_manager.initialize()
                    logger.info("GPIO manager initialized successfully")
                except Exception as gpio_error:
                    logger.warning(f"GPIO initialization failed: {gpio_error}")
                    logger.info("Continuing without GPIO support...")
                    
                    from .hal.gpio_manager import MockGPIOManager
                    gpio_manager = MockGPIOManager()
                    await gpio_manager.initialize()
                    logger.info("Mock GPIO manager initialized (no GPIO hardware)")
            
            # Setup GPIO components if available
            if gpio_manager and hasattr(gpio_manager, 'setup_button'):
                try:
                    # Setup trigger button
                    if hardware_profile.gpio.button_pin:
                        await gpio_manager.setup_button(
                            hardware_profile.gpio.button_pin,
                            self._on_button_press,
                            pull_up=hardware_profile.gpio.button_pull_up,
                            bounce_time=hardware_profile.gpio.button_bounce_time
                        )
                    
                    # Setup status LED
                    if hardware_profile.gpio.led_pin:
                        await gpio_manager.setup_led(hardware_profile.gpio.led_pin)
                except Exception as setup_error:
                    logger.warning(f"GPIO setup failed: {setup_error}")
            
            # Initialize hardware manager
            await self.hardware_manager.initialize(audio_device, gpio_manager)
            
            logger.info("Hardware initialized (with fallbacks if needed)")
            
        except Exception as e:
            logger.error(f"Hardware initialization failed completely: {e}")
            # Don't raise - allow system to continue without hardware
            logger.warning("Continuing without hardware support...")
            
            # Initialize with all mock devices
            from .hal.audio_devices import MockAudioDevice
            from .hal.gpio_manager import MockGPIOManager
            
            mock_audio = MockAudioDevice(hardware_profile.audio if 'hardware_profile' in locals() else None)
            mock_gpio = MockGPIOManager()
            
            await mock_audio.initialize()
            await mock_gpio.initialize()
            await self.hardware_manager.initialize(mock_audio, mock_gpio)
            
            logger.info("All mock hardware initialized")
    
    async def _initialize_providers(self) -> None:
        """Initialize AI service providers."""
        try:
            logger.info("Initializing providers...")
            
            # Initialize LLM providers
            if self.settings.openai_api_key:
                openai_llm = OpenAILLMProvider(
                    api_key=self.settings.openai_api_key,
                    model=self.settings.openai_model,
                    base_url=self.settings.openai_base_url
                )
                self.provider_manager.register_llm_provider(
                    openai_llm,
                    is_default=(self.settings.default_llm_provider == "openai")
                )
            
            if self.settings.gemini_api_key:
                gemini_llm = GeminiLLMProvider(
                    api_key=self.settings.gemini_api_key,
                    model=self.settings.gemini_model
                )
                self.provider_manager.register_llm_provider(
                    gemini_llm,
                    is_default=(self.settings.default_llm_provider == "gemini")
                )
            
            # Initialize TTS providers
            if self.settings.openai_api_key:
                openai_tts = OpenAITTSProvider(
                    api_key=self.settings.openai_api_key,
                    model=self.settings.openai_tts_model,
                    voice=self.settings.openai_tts_voice
                )
                self.provider_manager.register_tts_provider(
                    openai_tts,
                    is_default=(self.settings.default_tts_provider == "openai")
                )
            
            if self.settings.elevenlabs_api_key:
                elevenlabs_tts = ElevenLabsTTSProvider(
                    api_key=self.settings.elevenlabs_api_key,
                    voice_id=self.settings.elevenlabs_voice_id
                )
                self.provider_manager.register_tts_provider(
                    elevenlabs_tts,
                    is_default=(self.settings.default_tts_provider == "elevenlabs")
                )
            
            logger.info("Providers initialized")
            
        except Exception as e:
            logger.error(f"Provider initialization failed: {e}")
            # Continue without providers - they can be added later
            logger.warning("Continuing without AI providers (add API keys to enable)")
    
    async def _initialize_agent(self) -> None:
        """Initialize storytelling agent."""
        try:
            logger.info("Initializing agent...")
            
            # Create agent
            self.agent = StorytellingAgent(
                provider_manager=self.provider_manager,
                hardware_manager=self.hardware_manager,
                safety_filter=self.safety_filter
            )
            
            # Initialize agent
            await self.agent.initialize()
            
            logger.info("Agent initialized")
            
        except Exception as e:
            logger.error(f"Agent initialization failed: {e}")
            # Continue without agent
            logger.warning("Continuing without storytelling agent")
    
    async def _initialize_web(self) -> None:
        """Initialize web interface."""
        try:
            logger.info("Initializing web interface...")
            
            # Import and initialize web app
            from .web.app import web_app
            
            if self.story_library:
                await web_app.initialize(self.agent, self.story_library)
            
            logger.info("Web interface initialized")
            
        except Exception as e:
            logger.error(f"Web interface initialization failed: {e}")
            logger.warning("Continuing without web interface")
    
    async def _on_button_press(self, event) -> None:
        """Handle hardware button press."""
        try:
            logger.info("Hardware button pressed")
            if self.agent:
                # Simulate wake word detection
                from .wakeword.loader import WakewordDetection
                import time
                
                detection = WakewordDetection(
                    keyword="button_press",
                    confidence=1.0,
                    timestamp=time.time(),
                    engine_name="hardware_button"
                )
                
                self.agent._on_wake_word_detected(detection)
        except Exception as e:
            logger.error(f"Button press handling failed: {e}")
    
    async def run(self) -> None:
        """Run the application main loop."""
        try:
            logger.info("Starting Bedtime Storyteller service...")
            
            # Setup signal handlers
            def signal_handler(signum, frame):
                logger.info(f"Received signal {signum}")
                self._shutdown_event.set()
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            # Start web server if available
            if hasattr(self, 'web_app') and self.web_app:
                # TODO: Start web server
                pass
            
            logger.info("Service started successfully")
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Service error: {e}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up all resources."""
        try:
            logger.info("Cleaning up...")
            
            # Stop agent
            if self.agent:
                await self.agent.cleanup()
            
            # Cleanup hardware
            if self.hardware_manager:
                await self.hardware_manager.cleanup()
            
            # Close database
            if self.database_engine:
                await self.database_engine.dispose()
            
            logger.info("Cleanup completed")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


async def run_service(daemon: bool = False):
    """Run the storyteller service."""
    app = None
    try:
        logger.info("Daemon mode not fully implemented, running in foreground")
        
        # Create and run application
        app = StorytellerApplication()
        
        # Initialize
        await app.initialize()
        
        # Run main loop
        await app.run()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        return 1
    finally:
        if app:
            await app.cleanup()
    
    return 0


def main():
    """Main entry point."""
    try:
        # Run the service
        exit_code = asyncio.run(run_service())
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()