"""
Audio device implementations for different hardware configurations.
Provides concrete implementations for IQAudio Codec, USB Audio, and mock devices.
"""

import asyncio
import logging
import subprocess
import os
from typing import Optional, Dict, Any, AsyncGenerator
import threading
from queue import Queue, Empty

# Optional imports for audio hardware
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    PYAUDIO_AVAILABLE = False

try:
    import wave
    WAVE_AVAILABLE = True
except ImportError:
    wave = None
    WAVE_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

from .interface import AudioInterface, AudioConfig, AudioFormat, AudioChunk, AudioDeviceType
from ..config.hardware_profiles import detect_pi_model, PiModel

logger = logging.getLogger(__name__)


class IQAudioDevice(AudioInterface):
    """IQAudio Codec HAT implementation for Pi Zero 2W."""
    
    def __init__(self, config: AudioConfig):
        super().__init__(config)
        self.audio = None
        self.playback_stream = None
        self.recording_stream = None
        self._recording_active = False
        self._recording_queue = None
    
    async def initialize(self) -> None:
        """Initialize IQAudio Codec."""
        try:
            logger.info("Initializing IQAudio Codec...")
            
            # Check if PyAudio is available
            if not PYAUDIO_AVAILABLE:
                raise RuntimeError("PyAudio not available - install python3-pyaudio")
            
            # Initialize PyAudio
            self.audio = pyaudio.PyAudio()
            
            # Check if the device exists
            if not self._find_iqaudio_device():
                raise RuntimeError("IQAudio Codec device not found")
            
            # Configure ALSA settings for IQAudio
            await self._configure_alsa()
            
            self.is_initialized = True
            logger.info("IQAudio Codec initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize IQAudio: {e}")
            await self.cleanup()
            raise
    
    def _find_iqaudio_device(self) -> bool:
        """Check if IQAudio device is available."""
        try:
            device_count = self.audio.get_device_count()
            logger.info(f"Found {device_count} audio devices.")
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                device_name = device_info["name"].lower()
                logger.debug(f"Device {i}: {device_name}")
                
                if "iqaudio" in device_name or "codec" in device_name:
                    logger.info(f"Found IQAudio device by name: {device_info['name']}")
                    return True
            
            # Check via aplay/arecord
            logger.debug("Checking with aplay -l")
            result = subprocess.run(["aplay", "-l"], capture_output=True, text=True)
            output = result.stdout.lower()
            if "iqaudio" in output or "codec" in output:
                logger.info("Found IQAudio device via aplay")
                return True
            
            logger.warning("IQAudio Codec device not found.")
            return False
            
        except Exception as e:
            logger.warning(f"Error checking for IQAudio device: {e}")
            return False
    
    async def _configure_alsa(self) -> None:
        """Configure ALSA for optimal IQAudio performance."""
        try:
            # Set the IQAudio device as default
            alsa_config = f"""
pcm.!default {{
    type hw
    card 0
    device 0
    rate {self.config.sample_rate}
    channels {self.config.channels}
    format S16_LE
}}

ctl.!default {{
    type hw
    card 0
}}
"""
            
            # Write ALSA config (would typically go to ~/.asoundrc)
            logger.debug("ALSA configuration for IQAudio prepared")
            
        except Exception as e:
            logger.warning(f"ALSA configuration failed: {e}")
    
    async def play_audio(self, audio_data: bytes, format: AudioFormat = None) -> None:
        """Play audio data through IQAudio."""
        if not self.is_initialized:
            raise RuntimeError("IQAudio not initialized")
        
        try:
            # Open playback stream
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                output=True,
                output_device_index=self._get_device_index()
            )
            
            # Play audio
            stream.write(audio_data)
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
            raise
    
    async def play_audio_stream(self, audio_stream: AsyncGenerator[bytes, None]) -> None:
        """Play streaming audio data."""
        if not self.is_initialized:
            raise RuntimeError("IQAudio not initialized")
        
        stream = None
        try:
            # Open playback stream
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                output=True,
                output_device_index=self._get_device_index(),
                frames_per_buffer=self.config.buffer_size
            )
            
            # Stream audio chunks
            async for chunk in audio_stream:
                if chunk:
                    stream.write(chunk)
                    await asyncio.sleep(0.01)  # Small delay to prevent buffer overrun
            
        except Exception as e:
            logger.error(f"Streaming playback failed: {e}")
            raise
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
    
    async def record_audio(self, duration: float) -> bytes:
        """Record audio for specified duration."""
        if not self.is_initialized:
            raise RuntimeError("IQAudio not initialized")
        
        try:
            # Open recording stream
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                input_device_index=self._get_device_index(),
                frames_per_buffer=self.config.buffer_size
            )
            
            # Calculate number of frames to record
            frames_to_record = int(self.config.sample_rate * duration)
            
            # Record audio
            audio_chunks = []
            for _ in range(0, frames_to_record, self.config.buffer_size):
                chunk = stream.read(self.config.buffer_size)
                audio_chunks.append(chunk)
            
            stream.stop_stream()
            stream.close()
            
            return b''.join(audio_chunks)
            
        except Exception as e:
            logger.error(f"Audio recording failed: {e}")
            raise
    
    async def start_recording_stream(self) -> AsyncGenerator[AudioChunk, None]:
        """Start recording audio as a stream."""
        if not self.is_initialized:
            raise RuntimeError("IQAudio not initialized")
        
        if self._recording_active:
            raise RuntimeError("Recording already active")
        
        try:
            self._recording_queue = Queue()
            self._recording_active = True
            
            # Start recording in a separate thread
            recording_thread = threading.Thread(target=self._recording_thread)
            recording_thread.start()
            
            # Yield audio chunks
            while self._recording_active:
                try:
                    chunk_data = self._recording_queue.get(timeout=1.0)
                    
                    chunk = AudioChunk(
                        data=chunk_data,
                        timestamp=asyncio.get_event_loop().time(),
                        format=AudioFormat.PCM_16,
                        sample_rate=self.config.sample_rate,
                        channels=self.config.channels
                    )
                    
                    yield chunk
                    
                except Empty:
                    continue
                
                await asyncio.sleep(0.01)
            
        except Exception as e:
            logger.error(f"Recording stream failed: {e}")
            self._recording_active = False
            raise
    
    def _recording_thread(self) -> None:
        """Recording thread function."""
        stream = None
        try:
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                input_device_index=self._get_device_index(),
                frames_per_buffer=self.config.buffer_size
            )
            
            while self._recording_active:
                try:
                    chunk = stream.read(self.config.buffer_size, exception_on_overflow=False)
                    self._recording_queue.put(chunk)
                except Exception as e:
                    logger.error(f"Recording error: {e}")
                    break
            
        except Exception as e:
            logger.error(f"Recording thread error: {e}")
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
    
    async def stop_recording_stream(self) -> None:
        """Stop the recording stream."""
        self._recording_active = False
    
    def _get_device_index(self) -> Optional[int]:
        """Get the device index for IQAudio."""
        try:
            device_count = self.audio.get_device_count()
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                device_name = device_info["name"].lower()
                
                if "iqaudio" in device_name or "codec" in device_name:
                    return i
            
            # Fallback to device 0
            return 0
            
        except Exception:
            return 0
    
    async def set_volume(self, volume: float) -> None:
        """Set playback volume using amixer."""
        try:
            volume_percent = int(volume * 100)
            subprocess.run(
                ["amixer", "set", "Master", f"{volume_percent}%"],
                check=True,
                capture_output=True
            )
        except Exception as e:
            logger.warning(f"Failed to set volume: {e}")
    
    async def get_volume(self) -> float:
        """Get current playback volume."""
        try:
            result = subprocess.run(
                ["amixer", "get", "Master"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse volume from amixer output
            for line in result.stdout.split('\n'):
                if '[' in line and '%' in line:
                    start = line.find('[') + 1
                    end = line.find('%')
                    if start > 0 and end > start:
                        volume_str = line[start:end]
                        return float(volume_str) / 100.0
            
            return 0.5  # Default fallback
            
        except Exception as e:
            logger.warning(f"Failed to get volume: {e}")
            return 0.5
    
    def is_device_available(self) -> bool:
        """Check if IQAudio device is available."""
        return self._find_iqaudio_device()
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get IQAudio device information."""
        return {
            "type": "iqaudio_codec",
            "name": "IQAudio Codec HAT",
            "sample_rate": self.config.sample_rate,
            "channels": self.config.channels,
            "buffer_size": self.config.buffer_size,
            "device_index": self._get_device_index(),
            "initialized": self.is_initialized
        }
    
    async def cleanup(self) -> None:
        """Clean up IQAudio resources."""
        self._recording_active = False
        
        if self.playback_stream:
            self.playback_stream.close()
            self.playback_stream = None
        
        if self.recording_stream:
            self.recording_stream.close()
            self.recording_stream = None
        
        if self.audio:
            self.audio.terminate()
            self.audio = None
        
        self.is_initialized = False
        logger.info("IQAudio cleanup completed")


class USBAudioDevice(AudioInterface):
    """USB Audio device implementation for Pi 5 with Waveshare dongle."""
    
    def __init__(self, config: AudioConfig):
        super().__init__(config)
        self.audio = None
        self._recording_active = False
        self._recording_queue = None
    
    async def initialize(self) -> None:
        """Initialize USB Audio device."""
        try:
            logger.info("Initializing USB Audio device...")
            
            # Check if PyAudio is available
            if not PYAUDIO_AVAILABLE:
                raise RuntimeError("PyAudio not available - install python3-pyaudio")
            
            # Initialize PyAudio
            self.audio = pyaudio.PyAudio()
            
            # Check if USB audio device exists
            device_index = self._find_usb_audio_device()
            if device_index is None:
                raise RuntimeError("USB Audio device not found")
            
            self.is_initialized = True
            logger.info(f"USB Audio device initialized (device index: {device_index})")
            
        except Exception as e:
            logger.error(f"Failed to initialize USB Audio: {e}")
            await self.cleanup()
            raise
    
    def _find_usb_audio_device(self) -> Optional[int]:
        """Find USB audio device."""
        try:
            device_count = self.audio.get_device_count()
            logger.info(f"Found {device_count} audio devices.")
            
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                device_name = device_info["name"].lower()
                logger.debug(f"Device {i}: {device_name}, inputs: {device_info['maxInputChannels']}, outputs: {device_info['maxOutputChannels']}")

                # Look for USB audio indicators
                if any(keyword in device_name for keyword in ["usb", "waveshare", "audio", "microphone"]):
                    if device_info["maxInputChannels"] > 0 and device_info["maxOutputChannels"] > 0:
                        logger.info(f"Found USB audio device: {device_info['name']} at index {i}")
                        return i
            
            # Fallback: look for any device that's not the default and has both input and output
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                is_default = device_info.get('is_default', False)
                if not is_default and device_info["maxInputChannels"] > 0 and device_info["maxOutputChannels"] > 0:
                    logger.info(f"Using fallback USB device: {device_info['name']} at index {i}")
                    return i
            
            logger.warning("No suitable USB audio device found.")
            return None
            
        except Exception as e:
            logger.warning(f"Error finding USB audio device: {e}")
            return None
    
    async def play_audio(self, audio_data: bytes, format: AudioFormat = None) -> None:
        """Play audio through USB device."""
        if not self.is_initialized:
            raise RuntimeError("USB Audio not initialized")
        
        try:
            device_index = self._find_usb_audio_device()
            
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                output=True,
                output_device_index=device_index
            )
            
            stream.write(audio_data)
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            logger.error(f"USB audio playback failed: {e}")
            raise
    
    async def play_audio_stream(self, audio_stream: AsyncGenerator[bytes, None]) -> None:
        """Play streaming audio data."""
        if not self.is_initialized:
            raise RuntimeError("USB Audio not initialized")
        
        stream = None
        try:
            device_index = self._find_usb_audio_device()
            
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                output=True,
                output_device_index=device_index,
                frames_per_buffer=self.config.buffer_size
            )
            
            async for chunk in audio_stream:
                if chunk:
                    stream.write(chunk)
                    await asyncio.sleep(0.01)
            
        except Exception as e:
            logger.error(f"USB streaming playback failed: {e}")
            raise
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
    
    async def record_audio(self, duration: float) -> bytes:
        """Record audio through USB device."""
        if not self.is_initialized:
            raise RuntimeError("USB Audio not initialized")
        
        try:
            device_index = self._find_usb_audio_device()
            
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.config.buffer_size
            )
            
            frames_to_record = int(self.config.sample_rate * duration)
            audio_chunks = []
            
            for _ in range(0, frames_to_record, self.config.buffer_size):
                chunk = stream.read(self.config.buffer_size)
                audio_chunks.append(chunk)
            
            stream.stop_stream()
            stream.close()
            
            return b''.join(audio_chunks)
            
        except Exception as e:
            logger.error(f"USB audio recording failed: {e}")
            raise
    
    async def start_recording_stream(self) -> AsyncGenerator[AudioChunk, None]:
        """Start recording audio as a stream."""
        # Similar implementation to IQAudio but with USB device
        raise NotImplementedError("Streaming recording for USB audio not implemented yet")
    
    async def stop_recording_stream(self) -> None:
        """Stop the recording stream."""
        self._recording_active = False
    
    async def set_volume(self, volume: float) -> None:
        """Set volume for USB audio device."""
        try:
            volume_percent = int(volume * 100)
            # Try to set volume for USB audio device
            subprocess.run(
                ["amixer", "-c", "1", "set", "PCM", f"{volume_percent}%"],
                check=True,
                capture_output=True
            )
        except Exception as e:
            logger.warning(f"Failed to set USB audio volume: {e}")
    
    async def get_volume(self) -> float:
        """Get current volume of USB audio device."""
        try:
            result = subprocess.run(
                ["amixer", "-c", "1", "get", "PCM"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse volume from output
            for line in result.stdout.split('\n'):
                if '[' in line and '%' in line:
                    start = line.find('[') + 1
                    end = line.find('%')
                    if start > 0 and end > start:
                        volume_str = line[start:end]
                        return float(volume_str) / 100.0
            
            return 0.5
            
        except Exception as e:
            logger.warning(f"Failed to get USB audio volume: {e}")
            return 0.5
    
    def is_device_available(self) -> bool:
        """Check if USB audio device is available."""
        return self._find_usb_audio_device() is not None
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get USB audio device information."""
        device_index = self._find_usb_audio_device()
        device_name = "Unknown"
        
        if device_index is not None and self.audio:
            try:
                device_info = self.audio.get_device_info_by_index(device_index)
                device_name = device_info["name"]
            except:
                pass
        
        return {
            "type": "usb_audio",
            "name": device_name,
            "sample_rate": self.config.sample_rate,
            "channels": self.config.channels,
            "buffer_size": self.config.buffer_size,
            "device_index": device_index,
            "initialized": self.is_initialized
        }
    
    async def cleanup(self) -> None:
        """Clean up USB audio resources."""
        self._recording_active = False
        
        if self.audio:
            self.audio.terminate()
            self.audio = None
        
        self.is_initialized = False
        logger.info("USB Audio cleanup completed")


class MockAudioDevice(AudioInterface):
    """Mock audio device for testing and development."""
    
    def __init__(self, config: AudioConfig):
        super().__init__(config)
        self._recording_active = False
    
    async def initialize(self) -> None:
        """Initialize mock audio device."""
        logger.info("Initializing mock audio device...")
        self.is_initialized = True
        logger.info("Mock audio device ready")
    
    async def play_audio(self, audio_data: bytes, format: AudioFormat = None) -> None:
        """Mock audio playback."""
        duration = len(audio_data) / (self.config.sample_rate * self.config.channels * 2)
        logger.info(f"Mock: Playing {len(audio_data)} bytes of audio ({duration:.2f}s)")
        await asyncio.sleep(duration)  # Simulate playback time
    
    async def play_audio_stream(self, audio_stream: AsyncGenerator[bytes, None]) -> None:
        """Mock streaming audio playback."""
        logger.info("Mock: Starting streaming playback")
        async for chunk in audio_stream:
            if chunk:
                duration = len(chunk) / (self.config.sample_rate * self.config.channels * 2)
                await asyncio.sleep(duration)
        logger.info("Mock: Streaming playback completed")
    
    async def record_audio(self, duration: float) -> bytes:
        """Mock audio recording."""
        logger.info(f"Mock: Recording {duration}s of audio")
        await asyncio.sleep(duration)
        
        # Generate silence
        samples = int(self.config.sample_rate * duration * self.config.channels)
        return b'\x00' * (samples * 2)  # 16-bit samples
    
    async def start_recording_stream(self) -> AsyncGenerator[AudioChunk, None]:
        """Mock recording stream."""
        logger.info("Mock: Starting recording stream")
        self._recording_active = True
        
        while self._recording_active:
            # Generate a chunk of silence
            chunk_duration = self.config.buffer_size / self.config.sample_rate
            samples = self.config.buffer_size * self.config.channels
            data = b'\x00' * (samples * 2)
            
            chunk = AudioChunk(
                data=data,
                timestamp=asyncio.get_event_loop().time(),
                format=AudioFormat.PCM_16,
                sample_rate=self.config.sample_rate,
                channels=self.config.channels
            )
            
            yield chunk
            await asyncio.sleep(chunk_duration)
    
    async def stop_recording_stream(self) -> None:
        """Stop mock recording."""
        logger.info("Mock: Stopping recording stream")
        self._recording_active = False
    
    async def set_volume(self, volume: float) -> None:
        """Mock volume setting."""
        logger.info(f"Mock: Setting volume to {volume:.2f}")
    
    async def get_volume(self) -> float:
        """Mock volume getting."""
        return 0.5
    
    def is_device_available(self) -> bool:
        """Mock device is always available."""
        return True
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get mock device information."""
        return {
            "type": "mock",
            "name": "Mock Audio Device",
            "sample_rate": self.config.sample_rate,
            "channels": self.config.channels,
            "buffer_size": self.config.buffer_size,
            "initialized": self.is_initialized
        }
    
    async def cleanup(self) -> None:
        """Clean up mock device."""
        self._recording_active = False
        self.is_initialized = False
        logger.info("Mock audio device cleaned up")


async def create_audio_device(config: AudioConfig) -> AudioInterface:
    """
    Create appropriate audio device based on configuration and hardware detection.
    
    Args:
        config: Audio configuration
        
    Returns:
        AudioInterface: Initialized audio device
    """
    if config.device_type == AudioDeviceType.MOCK:
        return MockAudioDevice(config)
    elif config.device_type == AudioDeviceType.IQAUDIO_CODEC:
        return IQAudioDevice(config)
    elif config.device_type == AudioDeviceType.USB_AUDIO:
        return USBAudioDevice(config)
    elif config.device_type == AudioDeviceType.SYSTEM_DEFAULT:
        # Use mock device for system default when no audio hardware
        logger.info("System default audio requested, using mock device as fallback")
        return MockAudioDevice(config)
    else:
        # Auto-detect based on Pi model
        pi_model = detect_pi_model()
        
        if pi_model == PiModel.PI_ZERO_2W:
            logger.info("Detected Pi Zero 2W, using IQAudio device")
            return IQAudioDevice(config)
        elif pi_model == PiModel.PI_5:
            logger.info("Detected Pi 5, using USB audio device")
            return USBAudioDevice(config)
        else:
            logger.info("Unknown Pi model, using mock audio device")
            return MockAudioDevice(config)