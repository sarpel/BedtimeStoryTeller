"""
Storytelling Agent - The core orchestrator for story generation and playback.
Implements streaming pipeline for concurrent story generation, TTS synthesis, and audio playback.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
from enum import Enum

from ..providers.base import ProviderManager, StoryRequest, TTSRequest, ProviderError
from ..wakeword.loader import WakewordDetection, get_engine_loader
from ..hal.interface import HardwareManager, AudioFormat
from ..utils.safety_filter import SafetyFilter
from ..config.settings import get_settings

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Storytelling agent states."""
    IDLE = "idle"
    LISTENING = "listening"
    GENERATING = "generating"
    PLAYING = "playing"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class StorySession:
    """Information about a story session."""
    session_id: str
    prompt: str
    start_time: float
    language: str = "tr"
    age_rating: str = "5+"
    paragraphs_generated: int = 0
    paragraphs_played: int = 0
    total_audio_duration: float = 0.0
    status: str = "active"


class StorytellingAgent:
    """
    Core storytelling agent that orchestrates the entire story generation and playback pipeline.
    
    Implements:
    - Wake word detection
    - Story generation with streaming
    - Concurrent TTS synthesis
    - Audio playback with queue management
    - Error handling and recovery
    """
    
    def __init__(
        self,
        provider_manager: ProviderManager,
        hardware_manager: HardwareManager,
        safety_filter: SafetyFilter
    ):
        self.provider_manager = provider_manager
        self.hardware_manager = hardware_manager
        self.safety_filter = safety_filter
        self.settings = get_settings()
        
        # Agent state
        self.state = AgentState.IDLE
        self.current_session: Optional[StorySession] = None
        self.is_running = False
        
        # Processing components
        self.wakeword_loader = get_engine_loader()
        self.audio_queue: Optional[asyncio.Queue] = None
        self.playback_task: Optional[asyncio.Task] = None
        self.generation_task: Optional[asyncio.Task] = None
        
        # Event callbacks
        self.on_state_change: Optional[Callable[[AgentState], None]] = None
        self.on_story_started: Optional[Callable[[StorySession], None]] = None
        self.on_story_completed: Optional[Callable[[StorySession], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        
        # Performance monitoring
        self.stats = {
            "sessions_completed": 0,
            "total_stories_generated": 0,
            "total_audio_duration": 0.0,
            "average_time_to_first_sound": 0.0,
            "wake_word_detections": 0
        }
    
    async def initialize(self) -> None:
        """Initialize the storytelling agent."""
        try:
            logger.info("Initializing Storytelling Agent...")
            
            # Ensure hardware manager is initialized
            if not self.hardware_manager.is_initialized:
                raise RuntimeError("Hardware manager not initialized")
            
            # Initialize audio queue
            self.audio_queue = asyncio.Queue(maxsize=self.settings.max_audio_queue_size)
            
            # Initialize safety filter
            if hasattr(self.safety_filter, 'initialize'):
                await self.safety_filter.initialize()
            
            self.is_running = True
            self._set_state(AgentState.IDLE)
            
            logger.info("Storytelling Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            await self.cleanup()
            raise
    
    async def start_listening(self) -> None:
        """Start listening for wake words."""
        if not self.is_running:
            raise RuntimeError("Agent not initialized")
        
        if self.state == AgentState.LISTENING:
            logger.warning("Already listening for wake words")
            return
        
        try:
            logger.info("Starting wake word detection...")
            
            # Start wake word detection
            await self.wakeword_loader.start_detection(self._on_wake_word_detected)
            
            self._set_state(AgentState.LISTENING)
            logger.info("Wake word detection started")
            
        except Exception as e:
            logger.error(f"Failed to start listening: {e}")
            self._set_state(AgentState.ERROR)
            if self.on_error:
                self.on_error(e)
            raise
    
    async def stop_listening(self) -> None:
        """Stop listening for wake words."""
        if self.state != AgentState.LISTENING:
            return
        
        try:
            await self.wakeword_loader.stop_detection()
            self._set_state(AgentState.IDLE)
            logger.info("Wake word detection stopped")
        except Exception as e:
            logger.error(f"Error stopping wake word detection: {e}")
    
    async def tell_story(self, prompt: str, **kwargs) -> StorySession:
        """
        Generate and play a story based on the given prompt.
        
        Args:
            prompt: Story topic or prompt
            **kwargs: Additional story parameters
            
        Returns:
            StorySession: Information about the story session
        """
        if not self.is_running:
            raise RuntimeError("Agent not initialized")
        
        if self.state in [AgentState.GENERATING, AgentState.PLAYING]:
            raise RuntimeError(f"Agent busy: {self.state}")
        
        try:
            # Create story session
            session = StorySession(
                session_id=f"session_{int(time.time())}",
                prompt=prompt,
                start_time=time.time(),
                language=kwargs.get("language", self.settings.story_language),
                age_rating=kwargs.get("age_rating", self.settings.story_age_rating)
            )
            
            self.current_session = session
            logger.info(f"Starting story session: {session.session_id}")
            
            # Notify listeners
            if self.on_story_started:
                self.on_story_started(session)
            
            # Start story generation and playback pipeline
            await self._execute_story_pipeline(session)
            
            # Update stats
            self.stats["sessions_completed"] += 1
            self.stats["total_stories_generated"] += session.paragraphs_generated
            self.stats["total_audio_duration"] += session.total_audio_duration
            
            # Mark session as completed
            session.status = "completed"
            logger.info(f"Story session completed: {session.session_id}")
            
            # Notify listeners
            if self.on_story_completed:
                self.on_story_completed(session)
            
            return session
            
        except Exception as e:
            logger.error(f"Story generation failed: {e}")
            if self.current_session:
                self.current_session.status = "failed"
            
            self._set_state(AgentState.ERROR)
            if self.on_error:
                self.on_error(e)
            raise
        finally:
            self.current_session = None
            if self.state != AgentState.ERROR:
                self._set_state(AgentState.IDLE)
    
    async def _execute_story_pipeline(self, session: StorySession) -> None:
        """Execute the main story generation and playback pipeline."""
        time_to_first_sound_start = time.time()
        first_sound_played = False
        
        # Initialize variables that may be used in exception handler
        tts_tasks = []
        
        try:
            self._set_state(AgentState.GENERATING)
            
            # Validate and filter the prompt
            safe_prompt = await self.safety_filter.validate_and_filter_prompt(session.prompt)
            
            # Get available providers
            llm_provider = await self.provider_manager.get_available_llm_provider()
            if not llm_provider:
                raise RuntimeError("No LLM provider available")
            
            tts_provider = await self.provider_manager.get_available_tts_provider()
            if not tts_provider:
                raise RuntimeError("No TTS provider available")
            
            logger.info(f"Using LLM: {llm_provider.name}, TTS: {tts_provider.name}")
            
            # Create story request
            story_request = StoryRequest(
                prompt=safe_prompt,
                language=session.language,
                age_rating=session.age_rating,
                max_paragraphs=self.settings.story_max_paragraphs
            )
            
            # Start playback task
            self.playback_task = asyncio.create_task(self._audio_playback_loop())
            
            # Start story generation and TTS processing
            
            async for paragraph in llm_provider.generate_story_stream(story_request):
                session.paragraphs_generated += 1
                logger.info(f"Generated paragraph {session.paragraphs_generated}: {paragraph[:50]}...")
                
                # Process paragraph through TTS
                tts_task = asyncio.create_task(
                    self._process_paragraph_tts(paragraph, tts_provider, session)
                )
                tts_tasks.append(tts_task)
                
                # Track time to first sound
                if not first_sound_played:
                    first_sound_played = True
                    time_to_first_sound = time.time() - time_to_first_sound_start
                    logger.info(f"Time to first sound: {time_to_first_sound:.2f}s")
                    
                    # Update running average
                    current_avg = self.stats["average_time_to_first_sound"]
                    sessions = self.stats["sessions_completed"]
                    self.stats["average_time_to_first_sound"] = (
                        (current_avg * sessions + time_to_first_sound) / (sessions + 1)
                    )
                
                # Limit concurrent TTS requests to manage memory
                if len(tts_tasks) >= self.settings.max_concurrent_tts_requests:
                    await asyncio.gather(*tts_tasks[:1])  # Wait for oldest task
                    tts_tasks = tts_tasks[1:]
            
            # Wait for all TTS tasks to complete
            if tts_tasks:
                await asyncio.gather(*tts_tasks)
            
            # Signal end of audio stream
            await self.audio_queue.put(None)
            
            # Wait for playback to complete
            if self.playback_task:
                await self.playback_task
                self.playback_task = None
            
            logger.info(f"Story pipeline completed: {session.paragraphs_generated} paragraphs")
            
        except Exception as e:
            logger.error(f"Story pipeline error: {e}")
            
            # Clean up tasks
            if self.playback_task and not self.playback_task.done():
                self.playback_task.cancel()
                try:
                    await self.playback_task
                except asyncio.CancelledError:
                    pass
                self.playback_task = None
            
            # Cancel pending TTS tasks
            for task in tts_tasks:
                if not task.done():
                    task.cancel()
            
            raise
    
    async def _process_paragraph_tts(
        self, 
        paragraph: str, 
        tts_provider, 
        session: StorySession
    ) -> None:
        """Process a paragraph through TTS and queue the audio."""
        try:
            # Create TTS request
            tts_request = TTSRequest(
                text=paragraph,
                language=session.language,
                format=self.settings.audio_format
            )
            
            # Synthesize audio
            audio_data = await tts_provider.synthesize(tts_request)
            
            # Calculate audio duration (approximate)
            # For 16-bit mono audio: duration = bytes / (sample_rate * 2)
            duration = len(audio_data) / (self.settings.audio_sample_rate * 2)
            session.total_audio_duration += duration
            
            # Queue audio for playback
            await self.audio_queue.put(audio_data)
            
            logger.debug(f"Queued audio for paragraph (duration: {duration:.2f}s)")
            
        except ProviderError as e:
            logger.error(f"TTS synthesis failed: {e}")
            # Queue silence to maintain story flow
            silence_duration = 2.0  # 2 seconds of silence
            silence_samples = int(self.settings.audio_sample_rate * silence_duration)
            silence = b'\x00' * (silence_samples * 2)  # 16-bit silence
            await self.audio_queue.put(silence)
        except Exception as e:
            logger.error(f"Paragraph processing error: {e}")
            raise
    
    async def _audio_playback_loop(self) -> None:
        """Audio playback loop that processes the audio queue."""
        try:
            self._set_state(AgentState.PLAYING)
            
            while True:
                try:
                    # Get audio chunk from queue
                    audio_data = await asyncio.wait_for(
                        self.audio_queue.get(), 
                        timeout=30.0  # Timeout to prevent hanging
                    )
                    
                    # Check for end-of-stream signal
                    if audio_data is None:
                        logger.info("End of audio stream")
                        break
                    
                    # Play audio
                    await self.hardware_manager.audio.play_audio(
                        audio_data, 
                        AudioFormat.MP3 if self.settings.audio_format == "mp3" else AudioFormat.PCM_16
                    )
                    
                    # Update session stats
                    if self.current_session:
                        self.current_session.paragraphs_played += 1
                    
                    # Mark task as done
                    self.audio_queue.task_done()
                    
                except asyncio.TimeoutError:
                    logger.warning("Audio playback timeout")
                    break
                except Exception as e:
                    logger.error(f"Audio playback error: {e}")
                    # Continue with next audio chunk
                    continue
            
            logger.info("Audio playback completed")
            
        except Exception as e:
            logger.error(f"Audio playback loop error: {e}")
            raise
    
    def _on_wake_word_detected(self, detection: WakewordDetection) -> None:
        """Handle wake word detection."""
        logger.info(f"Wake word detected: {detection.keyword} (confidence: {detection.confidence:.3f})")
        
        self.stats["wake_word_detections"] += 1
        
        # Create a default story prompt based on the wake word
        if detection.keyword.lower() in ["porcupine", "picovoice"]:
            prompt = "Güzel bir gece masalı anlat"  # "Tell a beautiful bedtime story"
        elif "jarvis" in detection.keyword.lower():
            prompt = "Macera dolu bir hikaye anlat"  # "Tell an adventurous story"
        else:
            prompt = "Sevimli hayvanlar hakkında bir hikaye"  # "A story about cute animals"
        
        # Start story generation in background task
        asyncio.create_task(self._handle_wake_word_story(prompt))
    
    async def _handle_wake_word_story(self, prompt: str) -> None:
        """Handle story generation triggered by wake word."""
        try:
            # Stop listening while generating story
            await self.stop_listening()
            
            # Generate and play story
            await self.tell_story(prompt)
            
            # Resume listening after story completion
            await self.start_listening()
            
        except Exception as e:
            logger.error(f"Wake word story handling failed: {e}")
            self._set_state(AgentState.ERROR)
            if self.on_error:
                self.on_error(e)
    
    def _set_state(self, new_state: AgentState) -> None:
        """Set agent state and notify listeners."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.info(f"Agent state changed: {old_state.value} -> {new_state.value}")
            
            if self.on_state_change:
                self.on_state_change(new_state)
    
    async def stop_current_story(self) -> None:
        """Stop the currently playing story."""
        if self.state not in [AgentState.GENERATING, AgentState.PLAYING]:
            return
        
        logger.info("Stopping current story...")
        
        # Cancel generation task
        if self.generation_task and not self.generation_task.done():
            self.generation_task.cancel()
        
        # Cancel playback task
        if self.playback_task and not self.playback_task.done():
            self.playback_task.cancel()
        
        # Clear audio queue
        if self.audio_queue:
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                    self.audio_queue.task_done()
                except asyncio.QueueEmpty:
                    break
        
        # Update session status
        if self.current_session:
            self.current_session.status = "stopped"
        
        self._set_state(AgentState.IDLE)
        logger.info("Story stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        status = {
            "state": self.state.value,
            "is_running": self.is_running,
            "current_session": None,
            "wakeword_engine": None,
            "providers": {},
            "stats": self.stats.copy()
        }
        
        # Add current session info
        if self.current_session:
            status["current_session"] = {
                "session_id": self.current_session.session_id,
                "prompt": self.current_session.prompt,
                "language": self.current_session.language,
                "paragraphs_generated": self.current_session.paragraphs_generated,
                "paragraphs_played": self.current_session.paragraphs_played,
                "duration": time.time() - self.current_session.start_time,
                "status": self.current_session.status
            }
        
        # Add wakeword engine info
        try:
            status["wakeword_engine"] = self.wakeword_loader.get_current_engine_info()
        except:
            pass
        
        # Add provider info
        try:
            status["providers"] = {
                "llm_providers": list(self.provider_manager.llm_providers.keys()),
                "tts_providers": list(self.provider_manager.tts_providers.keys()),
                "default_llm": self.provider_manager.default_llm,
                "default_tts": self.provider_manager.default_tts
            }
        except:
            pass
        
        return status
    
    async def cleanup(self) -> None:
        """Clean up agent resources."""
        logger.info("Cleaning up Storytelling Agent...")
        
        self.is_running = False
        
        # Stop current story
        await self.stop_current_story()
        
        # Stop wake word detection
        await self.stop_listening()
        
        # Clean up wakeword engine
        try:
            await self.wakeword_loader.cleanup()
        except Exception as e:
            logger.warning(f"Error cleaning up wakeword loader: {e}")
        
        self._set_state(AgentState.STOPPED)
        logger.info("Storytelling Agent cleanup completed")