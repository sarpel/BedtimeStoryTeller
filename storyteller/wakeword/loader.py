"""
Dynamic wakeword engine loader.
Implements memory-safe loading of only the configured wakeword engine.
Critical for maintaining the 400MB RAM constraint on Pi Zero 2W.
"""

import importlib
import logging
import asyncio
from typing import Optional, Dict, Any, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class WakewordEngine(ABC):
    """Abstract base class for wakeword detection engines."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.is_listening = False
        self.detection_callback: Optional[Callable] = None
        self._stop_event = asyncio.Event()
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the wakeword engine with given configuration."""
        pass
    
    @abstractmethod
    async def start_listening(self, callback: Callable[[str], None]) -> None:
        """
        Start listening for wake words.
        
        Args:
            callback: Function to call when wake word is detected
        """
        pass
    
    @abstractmethod
    async def stop_listening(self) -> None:
        """Stop listening for wake words."""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources and stop the engine."""
        pass
    
    @abstractmethod
    def get_supported_keywords(self) -> list:
        """Get list of supported wake words."""
        pass
    
    @abstractmethod
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage information."""
        pass


class EngineStatus(Enum):
    """Wakeword engine status."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    LISTENING = "listening"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class WakewordDetection:
    """Wake word detection event."""
    keyword: str
    confidence: float
    timestamp: float
    engine_name: str


class WakewordEngineLoader:
    """
    Manages dynamic loading and switching of wakeword engines.
    Ensures only one engine is loaded at a time to conserve memory.
    """
    
    def __init__(self):
        self.current_engine: Optional[WakewordEngine] = None
        self.current_engine_name: Optional[str] = None
        self.status = EngineStatus.UNINITIALIZED
        self._supported_engines = {
            "porcupine": "storyteller.wakeword.porcupine_engine",
            "openwakeword": "storyteller.wakeword.openwakeword_engine"
        }
    
    async def load_engine(self, engine_name: str, config: Dict[str, Any]) -> WakewordEngine:
        """
        Load a wakeword engine dynamically, unloading any existing engine first.
        
        Args:
            engine_name: Name of the engine to load ("porcupine" or "openwakeword")
            config: Engine configuration dictionary
            
        Returns:
            WakewordEngine: Initialized engine instance
            
        Raises:
            ValueError: If engine is not supported
            ImportError: If engine module cannot be imported
            RuntimeError: If engine initialization fails
        """
        try:
            self.status = EngineStatus.INITIALIZING
            
            # Clean up existing engine first to free memory
            if self.current_engine:
                logger.info(f"Unloading current engine: {self.current_engine_name}")
                await self._unload_current_engine()
            
            # Validate engine name
            if engine_name not in self._supported_engines:
                raise ValueError(
                    f"Unsupported engine: {engine_name}. "
                    f"Supported engines: {list(self._supported_engines.keys())}"
                )
            
            # Dynamic import to avoid loading unused engines
            module_path = self._supported_engines[engine_name]
            logger.info(f"Loading wakeword engine: {engine_name} from {module_path}")
            
            try:
                engine_module = importlib.import_module(module_path)
            except ImportError as e:
                logger.error(f"Failed to import {module_path}: {e}")
                raise ImportError(f"Could not import {engine_name} engine: {e}")
            
            # Get the engine creation function
            if not hasattr(engine_module, 'create_engine'):
                raise ImportError(f"Engine module {module_path} missing 'create_engine' function")
            
            # Create engine instance
            try:
                engine = await engine_module.create_engine(config)
            except Exception as e:
                logger.error(f"Failed to create {engine_name} engine: {e}")
                raise RuntimeError(f"Failed to create {engine_name} engine: {e}")
            
            # Initialize the engine
            try:
                await engine.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize {engine_name} engine: {e}")
                await engine.cleanup()  # Clean up partial initialization
                raise RuntimeError(f"Failed to initialize {engine_name} engine: {e}")
            
            # Store the engine
            self.current_engine = engine
            self.current_engine_name = engine_name
            self.status = EngineStatus.READY
            
            logger.info(f"Successfully loaded and initialized {engine_name} engine")
            
            # Log memory usage
            try:
                memory_info = engine.get_memory_usage()
                logger.info(f"Engine memory usage: {memory_info}")
            except Exception as e:
                logger.warning(f"Could not get memory usage info: {e}")
            
            return engine
            
        except Exception as e:
            self.status = EngineStatus.ERROR
            self.current_engine = None
            self.current_engine_name = None
            logger.error(f"Failed to load engine {engine_name}: {e}")
            raise
    
    async def _unload_current_engine(self) -> None:
        """Unload the current engine and free its memory."""
        if not self.current_engine:
            return
        
        try:
            # Stop listening if active
            if self.current_engine.is_listening:
                await self.current_engine.stop_listening()
            
            # Clean up engine resources
            await self.current_engine.cleanup()
            
            logger.info(f"Successfully unloaded {self.current_engine_name} engine")
            
        except Exception as e:
            logger.error(f"Error during engine cleanup: {e}")
        finally:
            # Clear references to help garbage collection
            self.current_engine = None
            self.current_engine_name = None
    
    async def start_detection(self, callback: Callable[[WakewordDetection], None]) -> None:
        """
        Start wake word detection with the loaded engine.
        
        Args:
            callback: Function to call when wake word is detected
        """
        if not self.current_engine:
            raise RuntimeError("No engine loaded. Call load_engine() first.")
        
        if self.status != EngineStatus.READY:
            raise RuntimeError(f"Engine not ready. Status: {self.status}")
        
        try:
            # Wrap the callback to create WakewordDetection objects
            def detection_wrapper(keyword: str, confidence: float = 1.0):
                import time
                detection = WakewordDetection(
                    keyword=keyword,
                    confidence=confidence,
                    timestamp=time.time(),
                    engine_name=self.current_engine_name
                )
                callback(detection)
            
            await self.current_engine.start_listening(detection_wrapper)
            self.status = EngineStatus.LISTENING
            logger.info(f"Started wake word detection with {self.current_engine_name}")
            
        except Exception as e:
            self.status = EngineStatus.ERROR
            logger.error(f"Failed to start detection: {e}")
            raise
    
    async def stop_detection(self) -> None:
        """Stop wake word detection."""
        if not self.current_engine:
            return
        
        try:
            await self.current_engine.stop_listening()
            self.status = EngineStatus.READY
            logger.info("Stopped wake word detection")
            
        except Exception as e:
            logger.error(f"Error stopping detection: {e}")
            self.status = EngineStatus.ERROR
            raise
    
    async def switch_engine(self, new_engine_name: str, config: Dict[str, Any]) -> WakewordEngine:
        """
        Switch to a different wakeword engine.
        
        Args:
            new_engine_name: Name of the new engine to load
            config: Configuration for the new engine
            
        Returns:
            WakewordEngine: The new engine instance
        """
        if self.current_engine_name == new_engine_name:
            logger.info(f"Already using {new_engine_name} engine")
            return self.current_engine
        
        logger.info(f"Switching from {self.current_engine_name} to {new_engine_name}")
        
        # Stop current detection if active
        if self.status == EngineStatus.LISTENING:
            await self.stop_detection()
        
        # Load the new engine (this will unload the current one)
        return await self.load_engine(new_engine_name, config)
    
    def get_current_engine_info(self) -> Dict[str, Any]:
        """Get information about the currently loaded engine."""
        if not self.current_engine:
            return {
                "engine_name": None,
                "status": self.status.value,
                "supported_keywords": [],
                "memory_usage": {}
            }
        
        try:
            return {
                "engine_name": self.current_engine_name,
                "status": self.status.value,
                "is_listening": self.current_engine.is_listening,
                "supported_keywords": self.current_engine.get_supported_keywords(),
                "memory_usage": self.current_engine.get_memory_usage(),
                "config": self.current_engine.config
            }
        except Exception as e:
            logger.warning(f"Error getting engine info: {e}")
            return {
                "engine_name": self.current_engine_name,
                "status": "error",
                "error": str(e)
            }
    
    def get_supported_engines(self) -> Dict[str, str]:
        """Get list of supported engine names and their module paths."""
        return self._supported_engines.copy()
    
    async def cleanup(self) -> None:
        """Clean up all resources and unload any loaded engine."""
        if self.current_engine:
            await self._unload_current_engine()
        self.status = EngineStatus.STOPPED
        logger.info("Wakeword engine loader cleaned up")


# Global engine loader instance
_engine_loader = None


def get_engine_loader() -> WakewordEngineLoader:
    """Get the global engine loader instance."""
    global _engine_loader
    if _engine_loader is None:
        _engine_loader = WakewordEngineLoader()
    return _engine_loader


async def load_wakeword_engine(engine_name: str, config: Dict[str, Any]) -> WakewordEngine:
    """
    Convenience function to load a wakeword engine.
    
    Args:
        engine_name: Name of the engine to load
        config: Engine configuration
        
    Returns:
        WakewordEngine: Loaded engine instance
    """
    loader = get_engine_loader()
    return await loader.load_engine(engine_name, config)