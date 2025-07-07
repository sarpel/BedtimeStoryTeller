"""
OpenWakeWord engine implementation.
Provides integration with openWakeWord for lightweight wake word detection.
"""

import asyncio
import logging
import numpy as np
from typing import Dict, Any, Callable, List, Optional
import pyaudio
import psutil

from .loader import WakewordEngine

logger = logging.getLogger(__name__)


class OpenWakeWordEngine(WakewordEngine):
    """OpenWakeWord detection engine implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("openwakeword", config)
        
        # OpenWakeWord-specific attributes
        self.oww_model = None
        self.audio_stream = None
        self.audio = None
        self.detection_task = None
        
        # Configuration
        self.model_paths = config.get("model_paths", [])
        self.inference_framework = config.get("inference_framework", "tflite")
        self.threshold = config.get("threshold", 0.5)
        self.vad_threshold = config.get("vad_threshold", 0.5)
        
        # Audio settings
        self.sample_rate = 16000  # OpenWakeWord expects 16kHz
        self.chunk_size = 1280    # 80ms chunks (16000 * 0.08)
        self.channels = 1         # Mono audio
        self.audio_format = pyaudio.paInt16
        
        # Device settings
        self.input_device_index = config.get("input_device_index")
        
        # Prediction settings
        self.prediction_threshold = config.get("prediction_threshold", 0.5)
        self.debounce_time = config.get("debounce_time", 0.5)  # seconds
        self.last_detection_time = 0
    
    async def initialize(self) -> None:
        """Initialize the OpenWakeWord engine."""
        try:
            # Import OpenWakeWord (only when needed to save memory)
            try:
                import openwakeword
                from openwakeword import Model
                self.openwakeword = openwakeword
                self.Model = Model
            except ImportError:
                raise ImportError(
                    "openwakeword not installed. Install with: pip install openwakeword"
                )
            
            logger.info("Initializing OpenWakeWord engine...")
            
            # Set inference framework
            if self.inference_framework == "tflite":
                try:
                    openwakeword.utils.download_models(["hey_jarvis_v0.1"])  # Download a default model if none specified
                except:
                    pass  # Download might fail, continue with existing models
            
            # Initialize model
            model_kwargs = {
                "inference_framework": self.inference_framework,
                "wakeword_models": self.model_paths if self.model_paths else None,
                "vad_threshold": self.vad_threshold
            }
            
            # Remove None values to use defaults
            model_kwargs = {k: v for k, v in model_kwargs.items() if v is not None}
            
            self.oww_model = self.Model(**model_kwargs)
            
            # Initialize PyAudio
            self.audio = pyaudio.PyAudio()
            
            # Find appropriate input device
            if self.input_device_index is None:
                self.input_device_index = self._find_input_device()
            
            logger.info(f"OpenWakeWord engine initialized successfully")
            logger.info(f"Inference framework: {self.inference_framework}")
            logger.info(f"Available models: {list(self.oww_model.prediction_buffer.keys())}")
            logger.info(f"VAD threshold: {self.vad_threshold}")
            logger.info(f"Sample rate: {self.sample_rate} Hz")
            logger.info(f"Chunk size: {self.chunk_size}")
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenWakeWord engine: {e}")
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
        
        if not self.oww_model:
            raise RuntimeError("OpenWakeWord not initialized. Call initialize() first.")
        
        try:
            self.detection_callback = callback
            
            # Reset model state
            self.oww_model.reset()
            
            # Open audio stream
            self.audio_stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=self.chunk_size
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
                    # Read audio chunk
                    audio_data = self.audio_stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    # Convert to numpy array (OpenWakeWord expects float32)
                    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                    
                    # Process audio with OpenWakeWord
                    prediction = self.oww_model.predict(audio_array)
                    
                    # Check for wake word detections
                    current_time = asyncio.get_event_loop().time()
                    
                    for model_name, score in prediction.items():
                        if score >= self.prediction_threshold:
                            # Check debounce time
                            if current_time - self.last_detection_time > self.debounce_time:
                                logger.info(f"Wake word detected: {model_name} (score: {score:.3f})")
                                self.last_detection_time = current_time
                                
                                if self.detection_callback:
                                    # Run callback in executor to avoid blocking
                                    loop = asyncio.get_event_loop()
                                    await loop.run_in_executor(
                                        None, 
                                        self.detection_callback, 
                                        model_name
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
        """Clean up OpenWakeWord resources."""
        await self.stop_listening()
        
        if self.oww_model:
            # OpenWakeWord doesn't have explicit cleanup, but we can clear references
            self.oww_model = None
        
        if self.audio:
            self.audio.terminate()
            self.audio = None
        
        logger.info("OpenWakeWord engine cleaned up")
    
    def get_supported_keywords(self) -> List[str]:
        """Get list of supported wake words."""
        if self.oww_model:
            return list(self.oww_model.prediction_buffer.keys())
        return []
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage information."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                "engine": "openwakeword",
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": process.memory_percent(),
                "models_loaded": len(self.get_supported_keywords()),
                "inference_framework": self.inference_framework,
                "is_listening": self.is_listening
            }
        except Exception as e:
            logger.warning(f"Could not get memory usage: {e}")
            return {"error": str(e)}
    
    def get_engine_info(self) -> Dict[str, Any]:
        """Get detailed engine information."""
        info = {
            "engine_name": "openwakeword",
            "version": getattr(self.openwakeword, '__version__', 'unknown') if hasattr(self, 'openwakeword') else 'unknown',
            "inference_framework": self.inference_framework,
            "available_models": self.get_supported_keywords(),
            "prediction_threshold": self.prediction_threshold,
            "vad_threshold": self.vad_threshold,
            "sample_rate": self.sample_rate,
            "chunk_size": self.chunk_size,
            "channels": self.channels,
            "is_listening": self.is_listening,
            "input_device_index": self.input_device_index,
            "debounce_time": self.debounce_time
        }
        
        if self.input_device_index is not None and self.audio:
            try:
                device_info = self.audio.get_device_info_by_index(self.input_device_index)
                info["input_device_name"] = device_info["name"]
            except:
                pass
        
        return info
    
    def get_prediction_scores(self) -> Dict[str, float]:
        """Get current prediction scores for all models."""
        if self.oww_model:
            # Get the latest prediction scores
            return dict(self.oww_model.prediction_buffer)
        return {}
    
    def set_threshold(self, threshold: float) -> None:
        """Set the prediction threshold for wake word detection."""
        self.prediction_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Set prediction threshold to: {self.prediction_threshold}")


async def create_engine(config: Dict[str, Any]) -> OpenWakeWordEngine:
    """
    Create and initialize an OpenWakeWord engine instance.
    
    Args:
        config: Engine configuration dictionary
        
    Returns:
        OpenWakeWordEngine: Initialized engine instance
    """
    engine = OpenWakeWordEngine(config)
    await engine.initialize()
    return engine


def validate_openwakeword_config(config: Dict[str, Any]) -> bool:
    """
    Validate OpenWakeWord configuration.
    
    Args:
        config: Configuration to validate
        
    Returns:
        bool: True if configuration is valid
    """
    # OpenWakeWord is more flexible with configuration
    inference_framework = config.get("inference_framework", "tflite")
    
    if inference_framework not in ["onnx", "tflite"]:
        logger.error(f"Invalid inference framework: {inference_framework}")
        return False
    
    # Validate thresholds
    prediction_threshold = config.get("prediction_threshold", 0.5)
    if not 0.0 <= prediction_threshold <= 1.0:
        logger.error(f"Prediction threshold must be between 0.0 and 1.0: {prediction_threshold}")
        return False
    
    vad_threshold = config.get("vad_threshold", 0.5)
    if not 0.0 <= vad_threshold <= 1.0:
        logger.error(f"VAD threshold must be between 0.0 and 1.0: {vad_threshold}")
        return False
    
    return True


def get_available_models() -> List[str]:
    """Get list of available pre-trained models."""
    try:
        import openwakeword
        # This would typically list available models from the openwakeword package
        # For now, return some common models
        return [
            "hey_jarvis",
            "alexa",
            "hey_google", 
            "hey_siri",
            "wake_up"
        ]
    except ImportError:
        return []