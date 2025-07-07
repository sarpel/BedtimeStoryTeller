"""
Porcupine wakeword engine implementation.
Provides integration with Picovoice Porcupine for high-accuracy wake word detection.
"""

import asyncio
import logging
import os
import struct
from typing import Dict, Any, Callable, List, Optional
import pyaudio
import psutil

from .loader import WakewordEngine

logger = logging.getLogger(__name__)


class PorcupineEngine(WakewordEngine):
    """Porcupine wake word detection engine implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("porcupine", config)
        
        # Porcupine-specific attributes
        self.porcupine = None
        self.audio_stream = None
        self.audio = None
        self.detection_task = None
        
        # Configuration
        self.access_key = config.get("access_key")
        self.keywords = config.get("keywords", ["porcupine"])
        self.keyword_paths = config.get("keyword_paths", [])
        self.model_path = config.get("model_path")
        self.sensitivities = config.get("sensitivities", [0.5])
        
        # Audio settings
        self.sample_rate = 16000  # Porcupine requires 16kHz
        self.frame_length = 512   # Porcupine frame length
        self.channels = 1         # Mono audio
        self.audio_format = pyaudio.paInt16
        
        # Device settings
        self.input_device_index = config.get("input_device_index")
        
        # Validate required configuration
        if not self.access_key:
            raise ValueError("Porcupine access key is required")
        
        # Ensure sensitivities list matches keywords
        while len(self.sensitivities) < len(self.keywords):
            self.sensitivities.append(0.5)
    
    async def initialize(self) -> None:
        """Initialize the Porcupine engine."""
        try:
            # Import Porcupine (only when needed to save memory)
            try:
                import pvporcupine
                self.pvporcupine = pvporcupine
            except ImportError:
                raise ImportError(
                    "pvporcupine not installed. Install with: pip install pvporcupine"
                )
            
            # Create Porcupine instance
            logger.info("Initializing Porcupine engine...")
            
            # Prepare keyword arguments
            porcupine_kwargs = {
                "access_key": self.access_key,
                "keywords": self.keywords,
                "sensitivities": self.sensitivities[:len(self.keywords)]
            }
            
            # Add optional parameters if provided
            if self.keyword_paths:
                porcupine_kwargs["keyword_paths"] = self.keyword_paths
            if self.model_path:
                porcupine_kwargs["model_path"] = self.model_path
            
            self.porcupine = self.pvporcupine.create(**porcupine_kwargs)
            
            # Initialize PyAudio
            self.audio = pyaudio.PyAudio()
            
            # Find appropriate input device
            if self.input_device_index is None:
                self.input_device_index = self._find_input_device()
            
            logger.info(f"Porcupine engine initialized successfully")
            logger.info(f"Keywords: {self.keywords}")
            logger.info(f"Sensitivities: {self.sensitivities[:len(self.keywords)]}")
            logger.info(f"Sample rate: {self.sample_rate} Hz")
            logger.info(f"Frame length: {self.frame_length}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Porcupine engine: {e}")
            await self.cleanup()
            raise
    
    def _find_input_device(self) -> int:
        """Find the best input device for audio capture."""
        try:
            device_count = self.audio.get_device_count()
            
            # Look for devices with input channels
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                
                if device_info["maxInputChannels"] > 0:
                    logger.info(f"Found input device {i}: {device_info['name']}")
                    
                    # Prefer devices with "codec" or "usb" in the name for Pi setups
                    device_name_lower = device_info["name"].lower()
                    if any(keyword in device_name_lower for keyword in ["codec", "usb", "audio"]):
                        logger.info(f"Selected preferred device {i}: {device_info['name']}")
                        return i
            
            # If no preferred device found, use the first available input device
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                if device_info["maxInputChannels"] > 0:
                    logger.info(f"Using first available input device {i}: {device_info['name']}")
                    return i
            
            # No input devices found
            raise RuntimeError("No audio input devices found")
            
        except Exception as e:
            logger.error(f"Error finding input device: {e}")
            return 0  # Default to device 0
    
    async def start_listening(self, callback: Callable[[str], None]) -> None:
        """Start listening for wake words."""
        if self.is_listening:
            logger.warning("Already listening for wake words")
            return
        
        if not self.porcupine:
            raise RuntimeError("Porcupine not initialized. Call initialize() first.")
        
        try:
            self.detection_callback = callback
            
            # Open audio stream
            self.audio_stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=self.frame_length
            )
            
            # Start detection task
            self.is_listening = True
            self._stop_event.clear()
            self.detection_task = asyncio.create_task(self._detection_loop())
            
            logger.info("Started listening for wake words")
            
        except Exception as e:
            logger.error(f"Failed to start listening: {e}")
            self.is_listening = False
            if self.audio_stream:
                self.audio_stream.close()
                self.audio_stream = None
            raise
    
    async def _detection_loop(self) -> None:
        """Main detection loop running in a separate task."""
        try:
            while self.is_listening and not self._stop_event.is_set():
                try:
                    # Read audio frame
                    pcm = self.audio_stream.read(self.frame_length, exception_on_overflow=False)
                    pcm_data = struct.unpack_from("h" * self.frame_length, pcm)
                    
                    # Process frame with Porcupine
                    keyword_index = self.porcupine.process(pcm_data)
                    
                    if keyword_index >= 0:
                        # Wake word detected
                        detected_keyword = self.keywords[keyword_index]
                        logger.info(f"Wake word detected: {detected_keyword}")
                        
                        if self.detection_callback:
                            # Run callback in executor to avoid blocking
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(
                                None, 
                                self.detection_callback, 
                                detected_keyword
                            )
                
                except Exception as e:
                    if self.is_listening:  # Only log if we're still supposed to be listening
                        logger.error(f"Error in detection loop: {e}")
                    break
                
                # Small sleep to prevent tight loop
                await asyncio.sleep(0.01)
                
        except asyncio.CancelledError:
            logger.info("Detection loop cancelled")
        except Exception as e:
            logger.error(f"Detection loop error: {e}")
        finally:
            logger.info("Detection loop ended")
    
    async def stop_listening(self) -> None:
        """Stop listening for wake words."""
        if not self.is_listening:
            return
        
        logger.info("Stopping wake word detection...")
        self.is_listening = False
        self._stop_event.set()
        
        # Cancel detection task
        if self.detection_task:
            self.detection_task.cancel()
            try:
                await self.detection_task
            except asyncio.CancelledError:
                pass
            self.detection_task = None
        
        # Close audio stream
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio_stream = None
        
        logger.info("Stopped wake word detection")
    
    async def cleanup(self) -> None:
        """Clean up Porcupine resources."""
        await self.stop_listening()
        
        if self.porcupine:
            self.porcupine.delete()
            self.porcupine = None
        
        if self.audio:
            self.audio.terminate()
            self.audio = None
        
        logger.info("Porcupine engine cleaned up")
    
    def get_supported_keywords(self) -> List[str]:
        """Get list of supported wake words."""
        return self.keywords.copy()
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage information."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                "engine": "porcupine",
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": process.memory_percent(),
                "keywords_loaded": len(self.keywords),
                "is_listening": self.is_listening
            }
        except Exception as e:
            logger.warning(f"Could not get memory usage: {e}")
            return {"error": str(e)}
    
    def get_engine_info(self) -> Dict[str, Any]:
        """Get detailed engine information."""
        info = {
            "engine_name": "porcupine",
            "version": getattr(self.pvporcupine, '__version__', 'unknown') if hasattr(self, 'pvporcupine') else 'unknown',
            "keywords": self.keywords,
            "sensitivities": self.sensitivities[:len(self.keywords)],
            "sample_rate": self.sample_rate,
            "frame_length": self.frame_length,
            "channels": self.channels,
            "is_listening": self.is_listening,
            "input_device_index": self.input_device_index
        }
        
        if self.input_device_index is not None and self.audio:
            try:
                device_info = self.audio.get_device_info_by_index(self.input_device_index)
                info["input_device_name"] = device_info["name"]
            except:
                pass
        
        return info


async def create_engine(config: Dict[str, Any]) -> PorcupineEngine:
    """
    Create and initialize a Porcupine engine instance.
    
    Args:
        config: Engine configuration dictionary
        
    Returns:
        PorcupineEngine: Initialized engine instance
    """
    engine = PorcupineEngine(config)
    await engine.initialize()
    return engine


def validate_porcupine_config(config: Dict[str, Any]) -> bool:
    """
    Validate Porcupine configuration.
    
    Args:
        config: Configuration to validate
        
    Returns:
        bool: True if configuration is valid
    """
    required_fields = ["access_key"]
    
    for field in required_fields:
        if field not in config or not config[field]:
            logger.error(f"Missing required field: {field}")
            return False
    
    # Validate keywords
    keywords = config.get("keywords", [])
    if not keywords:
        logger.error("At least one keyword must be specified")
        return False
    
    # Validate sensitivities
    sensitivities = config.get("sensitivities", [])
    if sensitivities and len(sensitivities) != len(keywords):
        logger.warning("Number of sensitivities doesn't match number of keywords")
    
    return True