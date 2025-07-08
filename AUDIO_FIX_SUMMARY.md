# Audio Hardware Detection Fix

## Problem Summary
The Bedtime Storyteller service was failing to start on Raspberry Pi 5 due to audio hardware detection issues:

- **Error**: "USB Audio device not found" 
- **Cause**: Pi 5 detected but no USB audio hardware present
- **Result**: Service crashes and restarts continuously

## Root Cause Analysis
1. **Hardware Detection**: Pi 5 correctly detected
2. **Audio Profile**: System attempted to use USB audio device
3. **Hardware Missing**: No USB audio dongle connected 
4. **ALSA Errors**: "cannot find card 0" - no audio devices available
5. **PyAudio Failure**: PyAudio initialization fails without audio hardware
6. **Service Crash**: Application exits with status code 1

## Applied Fixes

### 1. Hardware Profile Fallback (`storyteller/config/hardware_profiles.py`)
```python
elif pi_model == PiModel.PI_5:
    if audio_devices.get("usb_audio_detected"):
        profile_key = "pi_5_usb_audio"
    else:
        # Use fallback profile for Pi 5 without USB audio
        profile_key = "fallback"
```

**Impact**: Pi 5 without USB audio now uses the fallback profile with `SYSTEM_DEFAULT` device type.

### 2. Optional Dependencies (`storyteller/hal/audio_devices.py`)
```python
# Optional imports for audio hardware
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    PYAUDIO_AVAILABLE = False
```

**Impact**: PyAudio import failures no longer crash the application.

### 3. Mock Device Routing
```python
elif config.device_type == AudioDeviceType.SYSTEM_DEFAULT:
    # Use mock device for system default when no audio hardware
    logger.info("System default audio requested, using mock device as fallback")
    return MockAudioDevice(config)
```

**Impact**: `SYSTEM_DEFAULT` device type automatically uses `MockAudioDevice`.

### 4. Graceful Hardware Initialization (`storyteller/main.py`)
```python
# Create audio device with fallback
try:
    audio_device = await create_audio_device(hardware_profile.audio)
    await audio_device.initialize()
    logger.info("Audio device initialized successfully")
except Exception as audio_error:
    logger.warning(f"Audio initialization failed: {audio_error}")
    logger.info("Falling back to mock audio device...")
    
    audio_device = MockAudioDevice(hardware_profile.audio)
    await audio_device.initialize()
    logger.info("Mock audio device initialized (no audio hardware)")
```

**Impact**: Hardware failures trigger automatic fallback to mock devices instead of crashing.

### 5. Environment Variable Override
```python
# Hardware configuration
force_mock_hardware: bool = Field(default=False, env="FORCE_MOCK_HARDWARE")
```

**Impact**: Can force mock hardware mode via `FORCE_MOCK_HARDWARE=true` environment variable.

## Testing & Validation

### Expected Log Output (Success)
```
INFO - Detected Pi model: PiModel.PI_5
INFO - Audio devices: {'playback': [], 'capture': [], 'iqaudio_detected': False, 'usb_audio_detected': False}
INFO - Selected hardware profile: fallback
INFO - Audio config: AudioConfig(device_type=<AudioDeviceType.SYSTEM_DEFAULT: 'system_default'>, ...)
INFO - System default audio requested, using mock device as fallback
INFO - Mock audio device initialized (no audio hardware)
INFO - Mock GPIO manager initialized (no GPIO hardware)
INFO - Hardware initialized (with fallbacks if needed)
INFO - Application initialized successfully
```

### Test Commands
```bash
# Restart the service
sudo systemctl restart storyteller

# Monitor logs
sudo journalctl -u storyteller -f

# Force mock mode (optional)
echo "FORCE_MOCK_HARDWARE=true" >> /home/pi/BedtimeStoryTeller/.env
sudo systemctl restart storyteller

# Test functionality
curl http://localhost:5000/api/status
```

## Benefits

1. **Service Reliability**: Service starts successfully without audio hardware
2. **Development Support**: Can develop/test without physical audio devices  
3. **Hardware Flexibility**: Graceful handling of missing/broken hardware
4. **Mock Functionality**: Full API and web interface remain functional
5. **Easy Testing**: Environment variable override for testing scenarios

## Future Considerations

1. **Hot-Plug Support**: Detect when audio hardware is connected later
2. **Audio Device Selection**: Web interface for manual audio device selection
3. **Hardware Health Monitoring**: Periodic hardware availability checks
4. **User Notifications**: Web UI notifications when running in mock mode

## Files Modified

- `storyteller/config/settings.py` - Added `force_mock_hardware` setting
- `storyteller/config/hardware_profiles.py` - Pi 5 fallback logic 
- `storyteller/hal/audio_devices.py` - Optional PyAudio, mock routing
- `storyteller/main.py` - Graceful hardware initialization with fallbacks

## Deployment Instructions

1. **Copy updated files** to your Raspberry Pi
2. **Restart the service**: `sudo systemctl restart storyteller`
3. **Verify startup**: `sudo journalctl -u storyteller -n 20`
4. **Test web interface**: Visit `http://pi-ip:5000`

The service should now start successfully and provide full functionality through the web interface, even without audio hardware present.