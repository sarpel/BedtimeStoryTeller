"""
Main application entry point for the Bedtime Storyteller.
Provides CLI interface and orchestrates all system components.
"""

import asyncio
import logging
import signal
import sys
import os
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

# Optional import for CLI functionality
try:
    import click
    CLICK_AVAILABLE = True
except ImportError:
    click = None
    CLICK_AVAILABLE = False

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
from .utils.safety_filter import SafetyFilter
from .storage.models import create_database_engine, create_tables, get_database_session, init_default_preferences
from .storage.story_library import StoryLibrary

# Setup logging with safe file handler
def setup_logging():
    """Setup logging with fallback handlers for permission issues."""
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Try to add file handler, with fallbacks for permission issues
    log_file_paths = [
        '/var/log/storyteller.log',
        '/tmp/storyteller.log',
        os.path.expanduser('~/storyteller.log')
    ]
    
    for log_path in log_file_paths:
        try:
            # Test if we can write to this location
            test_path = os.path.dirname(log_path)
            if os.path.exists(test_path) and os.access(test_path, os.W_OK):
                handlers.append(logging.FileHandler(log_path, mode='a'))
                break
        except (PermissionError, OSError):
            continue
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

setup_logging()

logger = logging.getLogger(__name__)


class StorytellerApplication:
    """Main application class that orchestrates all components."""
    
    def __init__(self):
        self.settings = get_settings()
        self.provider_manager = ProviderManager()
        self.hardware_manager = HardwareManager()
        self.safety_filter = SafetyFilter(
            target_age=int(self.settings.story_age_rating.replace('+', '')),
            language=self.settings.story_language
        )
        self.agent: Optional[StorytellingAgent] = None
        self.database_engine = None
        self.story_library: Optional[StoryLibrary] = None
        self.shutdown_event = asyncio.Event()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.shutdown())
    
    async def initialize(self) -> None:
        """Initialize all application components."""
        try:
            logger.info("Initializing Bedtime Storyteller...")
            
            # Initialize database
            await self._initialize_database()
            
            # Initialize hardware
            await self._initialize_hardware()
            
            # Initialize providers
            await self._initialize_providers()
            
            # Initialize wakeword engine
            await self._initialize_wakeword()
            
            # Initialize agent
            self.agent = StorytellingAgent(
                self.provider_manager,
                self.hardware_manager,
                self.safety_filter
            )
            await self.agent.initialize()
            
            # Setup event callbacks
            self.agent.on_state_change = self._on_agent_state_change
            self.agent.on_story_started = self._on_story_started
            self.agent.on_story_completed = self._on_story_completed
            self.agent.on_error = self._on_agent_error
            
            logger.info("Bedtime Storyteller initialized successfully")
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            await self.cleanup()
            raise
    
    async def _initialize_database(self) -> None:
        """Initialize database and story library."""
        try:
            logger.info("Initializing database...")
            
            # Create database engine
            self.database_engine = await create_database_engine(self.settings.database_url)
            
            # Create tables
            await create_tables(self.database_engine)
            
            # Initialize story library
            session = await get_database_session(self.database_engine)
            self.story_library = StoryLibrary(session)
            
            # Initialize default preferences
            await init_default_preferences(session)
            
            logger.info("Database initialized")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _initialize_hardware(self) -> None:
        """Initialize hardware components."""
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
                    
                    # Import here to avoid circular import
                    from .hal.audio_devices import MockAudioDevice
                    
                    # Create mock audio device with same config
                    audio_device = MockAudioDevice(hardware_profile.audio)
                    await audio_device.initialize()
                    logger.info("Mock audio device initialized (no audio hardware)")
            
            # Create GPIO manager with fallback
            gpio_manager = None
            
            # Check if mock hardware is forced
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
                    
                    # Import here to avoid circular import
                    from .hal.gpio_manager import MockGPIOManager
                    
                    # Create mock GPIO manager
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
            
            # Check if we have at least one provider of each type
            if not self.provider_manager.llm_providers:
                raise RuntimeError("No LLM providers configured")
            
            if not self.provider_manager.tts_providers:
                raise RuntimeError("No TTS providers configured")
            
            logger.info(
                f"Providers initialized: "
                f"LLM={list(self.provider_manager.llm_providers.keys())}, "
                f"TTS={list(self.provider_manager.tts_providers.keys())}"
            )
            
        except Exception as e:
            logger.error(f"Provider initialization failed: {e}")
            raise
    
    async def _initialize_wakeword(self) -> None:
        """Initialize wakeword engine."""
        try:
            logger.info("Initializing wakeword engine...")
            
            # Prepare wakeword config
            wakeword_config = {
                "engine_name": self.settings.wakeword_engine
            }
            
            if self.settings.wakeword_engine == "porcupine":
                wakeword_config.update({
                    "access_key": self.settings.porcupine_access_key,
                    "keywords": self.settings.porcupine_keywords.split(",")
                })
            elif self.settings.wakeword_engine == "openwakeword":
                wakeword_config.update({
                    "inference_framework": self.settings.openwakeword_inference_framework,
                    "model_paths": [self.settings.openwakeword_model_path] if self.settings.openwakeword_model_path else []
                })
            
            # Load wakeword engine
            engine = await load_wakeword_engine(self.settings.wakeword_engine, wakeword_config)
            
            logger.info(f"Wakeword engine initialized: {self.settings.wakeword_engine}")
            
        except Exception as e:
            logger.error(f"Wakeword initialization failed: {e}")
            raise
    
    def _on_button_press(self, event) -> None:
        """Handle GPIO button press."""
        from .hal.interface import PinState
        
        if event.state == PinState.LOW:  # Button pressed (assuming pull-up)
            logger.info("Button pressed, triggering story generation")
            
            # Create task to handle story generation
            asyncio.create_task(self._handle_button_story())
    
    async def _handle_button_story(self) -> None:
        """Handle story generation triggered by button press."""
        try:
            if self.agent and self.agent.state.value in ["idle", "listening"]:
                # Use default prompt for button trigger
                prompt = "Güzel bir uyku masalı anlat"  # "Tell a beautiful bedtime story"
                await self.agent.tell_story(prompt)
        except Exception as e:
            logger.error(f"Button story handling failed: {e}")
    
    def _on_agent_state_change(self, new_state) -> None:
        """Handle agent state changes."""
        logger.info(f"Agent state changed to: {new_state.value}")
        
        # Update status LED if available
        if self.hardware_manager.gpio:
            try:
                if new_state.value == "listening":
                    # Blink LED to indicate listening
                    asyncio.create_task(
                        self.hardware_manager.gpio.blink_led(24, 0.5, 3)
                    )
                elif new_state.value == "playing":
                    # Solid LED during playback
                    asyncio.create_task(
                        self.hardware_manager.gpio.set_led(24, True)
                    )
                elif new_state.value == "idle":
                    # Turn off LED when idle
                    asyncio.create_task(
                        self.hardware_manager.gpio.set_led(24, False)
                    )
            except Exception as e:
                logger.warning(f"LED update failed: {e}")
        
        # Log event to database
        if self.story_library:
            asyncio.create_task(
                self.story_library.log_event(
                    "state_change",
                    f"Agent state changed to {new_state.value}",
                    level="info",
                    component="agent"
                )
            )
    
    def _on_story_started(self, session) -> None:
        """Handle story session start."""
        logger.info(f"Story session started: {session.session_id}")
        
        # Log event
        if self.story_library:
            asyncio.create_task(
                self.story_library.log_event(
                    "story_started",
                    f"Story session started: {session.prompt}",
                    level="info",
                    component="agent",
                    session_id=session.session_id
                )
            )
    
    def _on_story_completed(self, session) -> None:
        """Handle story session completion."""
        logger.info(f"Story session completed: {session.session_id}")
        
        # Save session to database
        if self.story_library:
            asyncio.create_task(
                self.story_library.complete_session(session.session_id)
            )
            
            # Log event
            asyncio.create_task(
                self.story_library.log_event(
                    "story_completed",
                    f"Story session completed: {session.paragraphs_generated} paragraphs",
                    level="info",
                    component="agent",
                    session_id=session.session_id
                )
            )
    
    def _on_agent_error(self, error) -> None:
        """Handle agent errors."""
        logger.error(f"Agent error: {error}")
        
        # Log error to database
        if self.story_library:
            asyncio.create_task(
                self.story_library.log_event(
                    "agent_error",
                    str(error),
                    level="error",
                    component="agent"
                )
            )
    
    async def run(self) -> None:
        """Run the main application loop."""
        try:
            logger.info("Starting Bedtime Storyteller service...")
            
            # Start listening for wake words
            if self.agent:
                await self.agent.start_listening()
            
            logger.info("Bedtime Storyteller is running. Press Ctrl+C to stop.")
            
            # Main loop - wait for shutdown signal
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Runtime error: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def shutdown(self) -> None:
        """Initiate graceful shutdown."""
        logger.info("Shutting down Bedtime Storyteller...")
        self.shutdown_event.set()
    
    async def cleanup(self) -> None:
        """Clean up all resources."""
        try:
            # Stop agent
            if self.agent:
                await self.agent.cleanup()
            
            # Clean up hardware
            if self.hardware_manager:
                await self.hardware_manager.cleanup()
            
            # Close database
            if self.database_engine:
                await self.database_engine.dispose()
            
            logger.info("Cleanup completed")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


# CLI Interface
if CLICK_AVAILABLE:
    @click.group()
    @click.version_option(version="0.1.0")
    def cli():
        """Bedtime Storyteller - AI-powered storytelling for children."""
        pass
else:
    def cli():
        """Dummy CLI function when click is not available."""
        print("Click library not available. Install with: pip install click")
        return


if CLICK_AVAILABLE:
    @cli.command()
    @click.option('--daemon', '-d', is_flag=True, help='Run as daemon service')
    @click.option('--config', '-c', help='Configuration file path')
    def run(daemon: bool, config: Optional[str]) -> None:
        """Run the storyteller service."""
        try:
            # Reload settings if config file specified
            if config:
                os.environ['STORYTELLER_CONFIG'] = config
                reload_settings()
            
            # Create and run application
            app = StorytellerApplication()
            
            if daemon:
                # TODO: Implement proper daemon mode
                logger.info("Daemon mode not fully implemented, running in foreground")
            
            # Run the application
            async def run_app():
                await app.initialize()
                await app.run()
            
            asyncio.run(run_app())
            
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Application error: {e}")
            sys.exit(1)


    @cli.command()
    @click.argument('prompt')
    @click.option('--language', '-l', default='tr', help='Story language (tr/en)')
    @click.option('--age', '-a', default='5+', help='Age rating')
    def tell(prompt: str, language: str, age: str) -> None:
        """Tell a story with the given prompt."""
        async def tell_story():
            app = StorytellerApplication()
            try:
                await app.initialize()
                
                if app.agent:
                    await app.agent.tell_story(prompt, language=language, age_rating=age)
                
            except Exception as e:
                logger.error(f"Story telling failed: {e}")
            finally:
                await app.cleanup()
        
        try:
            asyncio.run(tell_story())
        except KeyboardInterrupt:
            logger.info("Story interrupted by user")


if CLICK_AVAILABLE:
    @cli.command()
    def wake():
        """Simulate a wake word detection for testing."""
        async def simulate_wake():
            app = StorytellerApplication()
            try:
                await app.initialize()
                
                if app.agent:
                    # Simulate wake word detection
                    from .wakeword.loader import WakewordDetection
                    import time
                    
                    detection = WakewordDetection(
                        keyword="test",
                        confidence=1.0,
                        timestamp=time.time(),
                        engine_name="manual"
                    )
                    
                    app.agent._on_wake_word_detected(detection)
                    
                    # Wait a bit for the story to start
                    await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Wake simulation failed: {e}")
            finally:
                await app.cleanup()
        
        try:
            asyncio.run(simulate_wake())
        except KeyboardInterrupt:
            logger.info("Wake simulation interrupted")


if CLICK_AVAILABLE:
    @cli.command()
    def status():
        """Show system status."""
        async def show_status():
            app = StorytellerApplication()
            try:
                await app.initialize()
                
                if app.agent:
                    status = app.agent.get_status()
                    
                    click.echo("=== Bedtime Storyteller Status ===")
                    click.echo(f"State: {status['state']}")
                    click.echo(f"Running: {status['is_running']}")
                    
                    if status.get('current_session'):
                        session = status['current_session']
                        click.echo(f"Current Session: {session['session_id']}")
                        click.echo(f"Prompt: {session['prompt']}")
                        click.echo(f"Status: {session['status']}")
                    
                    if status.get('wakeword_engine'):
                        engine = status['wakeword_engine']
                        click.echo(f"Wakeword Engine: {engine.get('engine_name', 'unknown')}")
                        click.echo(f"Listening: {engine.get('is_listening', False)}")
                    
                    stats = status.get('stats', {})
                    click.echo(f"Sessions Completed: {stats.get('sessions_completed', 0)}")
                    click.echo(f"Stories Generated: {stats.get('total_stories_generated', 0)}")
                    click.echo(f"Wake Word Detections: {stats.get('wake_word_detections', 0)}")
                
            except Exception as e:
                logger.error(f"Status check failed: {e}")
            finally:
                await app.cleanup()
        
        try:
            asyncio.run(show_status())
        except Exception as e:
            click.echo(f"Error: {e}")


if CLICK_AVAILABLE:
    @cli.command()
    def test():
        """Run system tests."""
        async def run_tests():
            app = StorytellerApplication()
            try:
                await app.initialize()
                
                click.echo("=== Hardware Test ===")
                if app.hardware_manager:
                    test_results = await app.hardware_manager.test_hardware()
                    
                    for component, results in test_results.items():
                        click.echo(f"{component.title()}:")
                        for test, result in results.items():
                            if isinstance(result, bool):
                                status = "✓" if result else "✗"
                                click.echo(f"  {test}: {status}")
                            else:
                                click.echo(f"  {test}: {result}")
                
                click.echo("\n=== Provider Test ===")
                if app.provider_manager:
                    health = await app.provider_manager.health_check()
                    
                    overall = health.get('overall_status', 'unknown')
                    click.echo(f"Overall Status: {overall}")
                    
                    for provider_type, providers in health.items():
                        if provider_type != 'overall_status' and isinstance(providers, dict):
                            click.echo(f"{provider_type.title()}:")
                            for name, status in providers.items():
                                if isinstance(status, dict):
                                    status_val = status.get('status', 'unknown')
                                    click.echo(f"  {name}: {status_val}")
                
            except Exception as e:
                logger.error(f"System test failed: {e}")
                click.echo(f"Test failed: {e}")
            finally:
                await app.cleanup()
        
        try:
            asyncio.run(run_tests())
        except Exception as e:
            click.echo(f"Error: {e}")


def main():
    """Main entry point."""
    try:
        cli()
    except Exception as e:
        logger.error(f"CLI error: {e}")
        sys.exit(1)


def wake_command():
    """Wake command entry point for systemd integration."""
    try:
        asyncio.run(wake.callback())
    except Exception as e:
        logger.error(f"Wake command error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()