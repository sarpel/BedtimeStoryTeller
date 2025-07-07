"""
Hardware abstraction layer interfaces.
Defines abstract interfaces for audio and GPIO operations to ensure
hardware-agnostic application code.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable, List, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import asyncio


class AudioDeviceType(Enum):
    """Types of audio devices supported."""
    IQAUDIO_CODEC = "iqaudio_codec"
    USB_AUDIO = "usb_audio"
    HDMI_AUDIO = "hdmi_audio"
    SYSTEM_DEFAULT = "system_default"
    MOCK = "mock"


class AudioFormat(Enum):
    """Supported audio formats."""
    PCM_16 = "pcm_16"
    PCM_24 = "pcm_24"
    MP3 = "mp3"
    WAV = "wav"


@dataclass
class AudioConfig:
    """Audio device configuration."""
    device_type: AudioDeviceType
    playback_device: str
    capture_device: str
    sample_rate: int = 16000
    channels: int = 1
    format: AudioFormat = AudioFormat.PCM_16
    buffer_size: int = 1024


@dataclass
class AudioChunk:
    """Audio data chunk."""
    data: bytes
    timestamp: float
    format: AudioFormat
    sample_rate: int
    channels: int


class AudioInterface(ABC):
    """Abstract interface for audio operations."""
    
    def __init__(self, config: AudioConfig):
        self.config = config
        self.is_initialized = False
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the audio device."""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up audio resources."""
        pass
    
    @abstractmethod
    async def play_audio(self, audio_data: bytes, format: AudioFormat = None) -> None:
        """
        Play audio data.
        
        Args:
            audio_data: Raw audio data
            format: Audio format (uses config default if None)
        """
        pass
    
    @abstractmethod
    async def play_audio_stream(self, audio_stream: AsyncGenerator[bytes, None]) -> None:
        """
        Play streaming audio data.
        
        Args:
            audio_stream: Async generator of audio chunks
        """
        pass
    
    @abstractmethod
    async def record_audio(self, duration: float) -> bytes:
        """
        Record audio for a specified duration.
        
        Args:
            duration: Recording duration in seconds
            
        Returns:
            bytes: Recorded audio data
        """
        pass
    
    @abstractmethod
    async def start_recording_stream(self) -> AsyncGenerator[AudioChunk, None]:
        """
        Start recording audio as a stream.
        
        Yields:
            AudioChunk: Audio data chunks
        """
        pass
    
    @abstractmethod
    async def stop_recording_stream(self) -> None:
        """Stop the recording stream."""
        pass
    
    @abstractmethod
    async def set_volume(self, volume: float) -> None:
        """
        Set playback volume.
        
        Args:
            volume: Volume level (0.0 to 1.0)
        """
        pass
    
    @abstractmethod
    async def get_volume(self) -> float:
        """
        Get current playback volume.
        
        Returns:
            float: Current volume level (0.0 to 1.0)
        """
        pass
    
    @abstractmethod
    def is_device_available(self) -> bool:
        """Check if the audio device is available."""
        pass
    
    @abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        """Get information about the audio device."""
        pass


class GPIOPin(Enum):
    """Common GPIO pin assignments."""
    BUTTON = 18
    LED_STATUS = 24
    LED_LISTENING = 25


class PinMode(Enum):
    """GPIO pin modes."""
    INPUT = "input"
    OUTPUT = "output"
    INPUT_PULLUP = "input_pullup"
    INPUT_PULLDOWN = "input_pulldown"


class PinState(Enum):
    """GPIO pin states."""
    LOW = 0
    HIGH = 1


@dataclass
class ButtonEvent:
    """Button press event."""
    pin: int
    state: PinState
    timestamp: float
    duration: Optional[float] = None  # For long press detection


class GPIOInterface(ABC):
    """Abstract interface for GPIO operations."""
    
    def __init__(self):
        self.is_initialized = False
        self._button_callbacks: Dict[int, Callable[[ButtonEvent], None]] = {}
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize GPIO interface."""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up GPIO resources."""
        pass
    
    @abstractmethod
    async def setup_pin(self, pin: int, mode: PinMode) -> None:
        """
        Setup a GPIO pin.
        
        Args:
            pin: GPIO pin number
            mode: Pin mode (input/output)
        """
        pass
    
    @abstractmethod
    async def read_pin(self, pin: int) -> PinState:
        """
        Read the state of a GPIO pin.
        
        Args:
            pin: GPIO pin number
            
        Returns:
            PinState: Current pin state
        """
        pass
    
    @abstractmethod
    async def write_pin(self, pin: int, state: PinState) -> None:
        """
        Write to a GPIO pin.
        
        Args:
            pin: GPIO pin number
            state: State to write
        """
        pass
    
    @abstractmethod
    async def setup_button(
        self, 
        pin: int, 
        callback: Callable[[ButtonEvent], None],
        pull_up: bool = True,
        bounce_time: int = 200
    ) -> None:
        """
        Setup a button with interrupt handling.
        
        Args:
            pin: GPIO pin number
            callback: Function to call on button press
            pull_up: Use pull-up resistor
            bounce_time: Debounce time in milliseconds
        """
        pass
    
    @abstractmethod
    async def setup_led(self, pin: int) -> None:
        """
        Setup an LED pin.
        
        Args:
            pin: GPIO pin number
        """
        pass
    
    @abstractmethod
    async def set_led(self, pin: int, state: bool) -> None:
        """
        Set LED state.
        
        Args:
            pin: GPIO pin number
            state: LED state (True = on, False = off)
        """
        pass
    
    @abstractmethod
    async def blink_led(self, pin: int, duration: float = 0.5, count: int = 1) -> None:
        """
        Blink an LED.
        
        Args:
            pin: GPIO pin number
            duration: Blink duration per cycle
            count: Number of blinks
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if GPIO interface is available."""
        pass


class HardwareManager:
    """
    Central manager for all hardware interfaces.
    Provides unified access to audio and GPIO functionality.
    """
    
    def __init__(self):
        self.audio: Optional[AudioInterface] = None
        self.gpio: Optional[GPIOInterface] = None
        self.is_initialized = False
    
    async def initialize(self, audio_interface: AudioInterface, gpio_interface: GPIOInterface) -> None:
        """
        Initialize hardware manager with specific interfaces.
        
        Args:
            audio_interface: Audio interface implementation
            gpio_interface: GPIO interface implementation
        """
        self.audio = audio_interface
        self.gpio = gpio_interface
        
        # Initialize interfaces
        if self.audio and not self.audio.is_initialized:
            await self.audio.initialize()
        
        if self.gpio and not self.gpio.is_initialized:
            await self.gpio.initialize()
        
        self.is_initialized = True
    
    async def cleanup(self) -> None:
        """Clean up all hardware resources."""
        if self.audio:
            await self.audio.cleanup()
        
        if self.gpio:
            await self.gpio.cleanup()
        
        self.is_initialized = False
    
    def get_hardware_info(self) -> Dict[str, Any]:
        """Get information about all hardware components."""
        info = {
            "initialized": self.is_initialized,
            "audio": None,
            "gpio": None
        }
        
        if self.audio:
            try:
                info["audio"] = {
                    "available": self.audio.is_device_available(),
                    "config": self.audio.config.__dict__,
                    "device_info": self.audio.get_device_info()
                }
            except Exception as e:
                info["audio"] = {"error": str(e)}
        
        if self.gpio:
            try:
                info["gpio"] = {
                    "available": self.gpio.is_available(),
                    "initialized": self.gpio.is_initialized
                }
            except Exception as e:
                info["gpio"] = {"error": str(e)}
        
        return info
    
    async def test_hardware(self) -> Dict[str, Any]:
        """Test all hardware components."""
        results = {
            "audio": {"playback": False, "recording": False},
            "gpio": {"buttons": False, "leds": False}
        }
        
        # Test audio playback
        if self.audio:
            try:
                # Generate a short test tone
                import numpy as np
                duration = 0.1  # 100ms
                sample_rate = self.audio.config.sample_rate
                t = np.linspace(0, duration, int(sample_rate * duration))
                tone = np.sin(2 * np.pi * 440 * t) * 0.1  # 440Hz tone at low volume
                tone_bytes = (tone * 32767).astype(np.int16).tobytes()
                
                await self.audio.play_audio(tone_bytes, AudioFormat.PCM_16)
                results["audio"]["playback"] = True
            except Exception as e:
                results["audio"]["playback_error"] = str(e)
        
        # Test GPIO LEDs if available
        if self.gpio:
            try:
                # Try to blink status LED
                await self.gpio.setup_led(GPIOPin.LED_STATUS.value)
                await self.gpio.blink_led(GPIOPin.LED_STATUS.value, 0.1, 1)
                results["gpio"]["leds"] = True
            except Exception as e:
                results["gpio"]["led_error"] = str(e)
        
        return results