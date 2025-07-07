"""
Hardware-specific configurations for different Raspberry Pi models and audio devices.
Implements auto-detection and configuration based on detected hardware.
"""

import os
import subprocess
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PiModel(Enum):
    """Supported Raspberry Pi models."""
    PI_ZERO_2W = "pi_zero_2w"
    PI_5 = "pi_5"
    PI_4 = "pi_4" 
    PI_3 = "pi_3"
    UNKNOWN = "unknown"


class AudioDeviceType(Enum):
    """Supported audio device types."""
    IQAUDIO_CODEC = "iqaudio_codec"
    USB_AUDIO = "usb_audio"
    HDMI_AUDIO = "hdmi_audio"
    SYSTEM_DEFAULT = "system_default"


@dataclass
class AudioConfig:
    """Audio device configuration."""
    device_type: AudioDeviceType
    playback_device: str
    capture_device: str
    sample_rate: int = 16000
    channels: int = 1
    format: str = "S16_LE"
    buffer_size: int = 1024


@dataclass
class GPIOConfig:
    """GPIO configuration for buttons and LEDs."""
    button_pin: Optional[int] = None
    led_pin: Optional[int] = None
    button_pull_up: bool = True
    button_bounce_time: int = 200  # milliseconds


@dataclass
class HardwareProfile:
    """Complete hardware profile for a specific Pi model and configuration."""
    model: PiModel
    audio: AudioConfig
    gpio: GPIOConfig
    memory_limit_mb: int
    cpu_cores: int
    wakeword_engine_preference: str = "porcupine"


# Hardware profiles for different Pi models and configurations
HARDWARE_PROFILES: Dict[str, HardwareProfile] = {
    "pi_zero_2w_iqaudio": HardwareProfile(
        model=PiModel.PI_ZERO_2W,
        audio=AudioConfig(
            device_type=AudioDeviceType.IQAUDIO_CODEC,
            playback_device="hw:0,0",
            capture_device="hw:0,0",
            sample_rate=16000,
            channels=1,
            buffer_size=512  # Smaller buffer for limited memory
        ),
        gpio=GPIOConfig(
            button_pin=18,  # GPIO 18 for trigger button
            led_pin=24,     # GPIO 24 for status LED
        ),
        memory_limit_mb=350,  # Conservative limit for Pi Zero 2W
        cpu_cores=4,
        wakeword_engine_preference="openwakeword"  # Better for limited resources
    ),
    
    "pi_5_usb_audio": HardwareProfile(
        model=PiModel.PI_5,
        audio=AudioConfig(
            device_type=AudioDeviceType.USB_AUDIO,
            playback_device="plughw:1,0",  # Waveshare USB audio dongle
            capture_device="plughw:1,0",
            sample_rate=16000,
            channels=1,
            buffer_size=1024
        ),
        gpio=GPIOConfig(
            button_pin=18,  # GPIO 18 for trigger button
            led_pin=24,     # GPIO 24 for status LED
        ),
        memory_limit_mb=400,  # More memory available on Pi 5
        cpu_cores=4,
        wakeword_engine_preference="porcupine"  # Can handle more complex engine
    ),
    
    "pi_4_hdmi": HardwareProfile(
        model=PiModel.PI_4,
        audio=AudioConfig(
            device_type=AudioDeviceType.HDMI_AUDIO,
            playback_device="plughw:1,0",  # HDMI audio
            capture_device="plughw:2,0",   # USB mic
            sample_rate=16000,
            channels=1,
        ),
        gpio=GPIOConfig(
            button_pin=18,
            led_pin=24,
        ),
        memory_limit_mb=400,
        cpu_cores=4,
        wakeword_engine_preference="porcupine"
    ),
    
    "fallback": HardwareProfile(
        model=PiModel.UNKNOWN,
        audio=AudioConfig(
            device_type=AudioDeviceType.SYSTEM_DEFAULT,
            playback_device="default",
            capture_device="default",
            sample_rate=16000,
            channels=1,
        ),
        gpio=GPIOConfig(),
        memory_limit_mb=300,  # Conservative fallback
        cpu_cores=1,
        wakeword_engine_preference="openwakeword"
    )
}


def detect_pi_model() -> PiModel:
    """Detect the Raspberry Pi model from system information."""
    try:
        # Try to read from /proc/device-tree/model (most reliable)
        if os.path.exists("/proc/device-tree/model"):
            with open("/proc/device-tree/model", "r") as f:
                model_info = f.read().strip().lower()
                
            if "pi zero 2" in model_info:
                return PiModel.PI_ZERO_2W
            elif "pi 5" in model_info or "raspberry pi 5" in model_info:
                return PiModel.PI_5
            elif "pi 4" in model_info or "raspberry pi 4" in model_info:
                return PiModel.PI_4
            elif "pi 3" in model_info or "raspberry pi 3" in model_info:
                return PiModel.PI_3
                
        # Fallback to /proc/cpuinfo
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read().lower()
            
        if "bcm2710" in cpuinfo or "bcm2837" in cpuinfo:
            if "zero 2" in cpuinfo:
                return PiModel.PI_ZERO_2W
            else:
                return PiModel.PI_3
        elif "bcm2711" in cpuinfo:
            return PiModel.PI_4
        elif "bcm2712" in cpuinfo:
            return PiModel.PI_5
            
    except Exception as e:
        logger.warning(f"Could not detect Pi model: {e}")
    
    return PiModel.UNKNOWN


def detect_audio_devices() -> Dict[str, Any]:
    """Detect available audio devices using aplay and arecord."""
    devices = {
        "playback": [],
        "capture": [],
        "iqaudio_detected": False,
        "usb_audio_detected": False
    }
    
    try:
        # Detect playback devices
        result = subprocess.run(
            ["aplay", "-l"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        
        if result.returncode == 0:
            output = result.stdout.lower()
            devices["playback"] = _parse_audio_devices(output)
            
            # Check for specific audio devices
            if "iqaudio" in output or "codec" in output:
                devices["iqaudio_detected"] = True
            if "usb" in output:
                devices["usb_audio_detected"] = True
                
    except Exception as e:
        logger.warning(f"Could not detect playback devices: {e}")
    
    try:
        # Detect capture devices
        result = subprocess.run(
            ["arecord", "-l"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        
        if result.returncode == 0:
            devices["capture"] = _parse_audio_devices(result.stdout.lower())
            
    except Exception as e:
        logger.warning(f"Could not detect capture devices: {e}")
    
    return devices


def _parse_audio_devices(output: str) -> list:
    """Parse aplay/arecord output to extract device information."""
    devices = []
    lines = output.split('\n')
    
    for line in lines:
        if 'card' in line and ':' in line:
            # Extract card number and device info
            parts = line.split(':')
            if len(parts) >= 2:
                card_info = parts[0].strip()
                device_info = parts[1].strip()
                devices.append({
                    "card_info": card_info,
                    "device_info": device_info,
                    "raw_line": line.strip()
                })
    
    return devices


def detect_hardware_profile() -> HardwareProfile:
    """Auto-detect hardware and return appropriate profile."""
    pi_model = detect_pi_model()
    audio_devices = detect_audio_devices()
    
    logger.info(f"Detected Pi model: {pi_model}")
    logger.info(f"Audio devices: {audio_devices}")
    
    # Determine the best profile based on detected hardware
    if pi_model == PiModel.PI_ZERO_2W:
        if audio_devices.get("iqaudio_detected"):
            profile_key = "pi_zero_2w_iqaudio"
        else:
            # Fallback for Pi Zero 2W without IQAudio
            profile_key = "fallback"
            
    elif pi_model == PiModel.PI_5:
        if audio_devices.get("usb_audio_detected"):
            profile_key = "pi_5_usb_audio"
        else:
            profile_key = "pi_4_hdmi"  # Fallback to HDMI audio
            
    elif pi_model == PiModel.PI_4:
        profile_key = "pi_4_hdmi"
        
    else:
        profile_key = "fallback"
    
    profile = HARDWARE_PROFILES.get(profile_key, HARDWARE_PROFILES["fallback"])
    
    logger.info(f"Selected hardware profile: {profile_key}")
    logger.info(f"Audio config: {profile.audio}")
    logger.info(f"Memory limit: {profile.memory_limit_mb}MB")
    
    return profile


def get_profile_by_name(profile_name: str) -> HardwareProfile:
    """Get a specific hardware profile by name."""
    return HARDWARE_PROFILES.get(profile_name, HARDWARE_PROFILES["fallback"])


def list_available_profiles() -> Dict[str, HardwareProfile]:
    """List all available hardware profiles."""
    return HARDWARE_PROFILES.copy()


def validate_audio_config(audio_config: AudioConfig) -> bool:
    """Validate that the audio configuration is working."""
    try:
        # Test if the specified audio devices exist
        playback_test = subprocess.run(
            ["aplay", "-D", audio_config.playback_device, "--help"],
            capture_output=True,
            timeout=5
        )
        
        capture_test = subprocess.run(
            ["arecord", "-D", audio_config.capture_device, "--help"],
            capture_output=True,
            timeout=5
        )
        
        return playback_test.returncode == 0 and capture_test.returncode == 0
        
    except Exception as e:
        logger.warning(f"Audio config validation failed: {e}")
        return False


def create_alsa_config(audio_config: AudioConfig) -> str:
    """Create ALSA configuration for the specified audio device."""
    alsa_config = f"""
# ALSA configuration for {audio_config.device_type.value}
pcm.storyteller_playback {{
    type hw
    card "{audio_config.playback_device}"
    device 0
    rate {audio_config.sample_rate}
    channels {audio_config.channels}
    format {audio_config.format}
}}

pcm.storyteller_capture {{
    type hw
    card "{audio_config.capture_device}"
    device 0
    rate {audio_config.sample_rate}
    channels {audio_config.channels}
    format {audio_config.format}
}}

# Default devices for storyteller application
pcm.!default {{
    type asym
    playback.pcm "storyteller_playback"
    capture.pcm "storyteller_capture"
}}
"""
    return alsa_config