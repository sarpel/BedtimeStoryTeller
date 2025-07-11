# Bedtime Storyteller Project Memory

## Project Overview
A resource-efficient, AI-powered bedtime storytelling device for Raspberry Pi, specifically designed for Turkish-speaking children. The system uses local wake word detection with remote AI processing for story generation and text-to-speech.

## Target Hardware
- **Primary**: Raspberry Pi Zero 2W with IQAudio Codec HAT
- **Secondary**: Raspberry Pi 5 with Waveshare USB Audio Dongle
- **OS**: DietPi (preferred) or Raspberry Pi OS
- **Memory Constraint**: 350-400MB RAM limit (critical for Pi Zero 2W)

## Architecture Overview

### Core Components
- **Wake Word Detection**: Porcupine (commercial) or OpenWakeWord (open source)
- **LLM Providers**: OpenAI GPT-4o-mini or Google Gemini
- **TTS Providers**: OpenAI TTS or ElevenLabs
- **Audio Processing**: PyAudio with hardware-specific device configuration
- **Database**: SQLite with async support
- **Web Interface**: FastAPI-based management interface
- **System Service**: Systemd service for auto-start and reliability

### Project Structure
```
storyteller/
   config/          # Settings and hardware profiles
   core/           # Main application logic and agent
   providers/      # AI service providers (LLM/TTS)
   wakeword/       # Wake word detection engines
   hal/           # Hardware abstraction layer
   storage/       # Database models and operations
   web/           # Web management interface
   utils/         # Utility functions and safety filters
   main.py        # Application entry point
```

## Key Technical Decisions

### Memory Optimization
- **Dynamic Loading**: Only one wake word engine loaded at runtime
- **Streaming Architecture**: Audio processed in chunks to minimize memory usage
- **Minimal Dependencies**: Carefully selected lightweight libraries
- **Resource Monitoring**: Built-in memory usage tracking

### Hardware Abstraction
- **Auto-Detection**: Automatic Pi model and audio device detection
- **Profile-Based**: Hardware-specific configurations in `hardware_profiles.py`
- **Audio Devices**:
  - Pi Zero 2W: IQAudio Codec (`hw:0,0`)
  - Pi 5: USB Audio (`plughw:1,0`)
  - Fallback: System default

### Safety & Content Filtering
- **Target Audience**: 5+ year old Turkish-speaking children
- **Content Safety**: Built-in safety filter for age-appropriate content
- **Parental Controls**: "Do Not Disturb" scheduling and content approval

## Configuration Management

### Environment Variables (.env)
```bash
# Required
OPENAI_API_KEY=your_key_here
PORCUPINE_ACCESS_KEY=your_key_here

# Hardware (auto-detected if empty)
PI_MODEL=pi_zero_2w  # or pi_5
AUDIO_DEVICE=iqaudio_codec  # or usb_audio

# Story Settings
STORY_LANGUAGE=tr
STORY_AGE_RATING=5+
WAKEWORD_ENGINE=porcupine  # or openwakeword
```

### Hardware Profiles
- **Pi Zero 2W + IQAudio**: Optimized for minimal memory, OpenWakeWord preferred
- **Pi 5 + USB Audio**: More resources available, Porcupine preferred
- **Auto-Detection**: System detects hardware and applies appropriate profile

## Development History & Fixes

### Critical Issues Resolved
1. **Asyncio Event Loop Bug**: Fixed double `asyncio.run()` calls in main.py
2. **Pydantic v2 Compatibility**: Updated from v1 syntax to v2 with `field_validator`
3. **Service Directory Paths**: Fixed incorrect `/opt/storyteller` paths to `/home/pi/BedtimeStoryTeller`
4. **OS Detection**: Improved DietPi detection (was incorrectly identified as Raspberry Pi OS)
5. **Permission Issues**: Removed overly restrictive systemd security settings
6. **Dependency Errors**: Added missing `pydantic-settings` dependency

### Production Readiness Improvements
- **Project Name Consistency**: Standardized from `bedtime-storyteller` to `BedtimeStoryTeller`
- **Dynamic User Detection**: Removed hardcoded 'pi' username assumption
- **OS-Specific Handling**: Different package sets for DietPi vs Pi OS
- **Boot Partition Compatibility**: Handles both `/boot/config.txt` and `/boot/firmware/config.txt`

## Installation & Deployment

### Setup Process
```bash
# Clone and setup
git clone https://github.com/sarpel/BedtimeStoryTeller.git
cd BedtimeStoryTeller
sudo ./scripts/setup.sh

# Configure environment
cp .env.example .env
nano .env  # Add API keys

# Start service
sudo systemctl start storyteller
```

### Service Management
- **Service File**: `/etc/systemd/system/storyteller.service`
- **Working Directory**: `/home/pi/BedtimeStoryTeller`
- **User**: `pi` (or dynamically detected user)
- **Auto-Restart**: Enabled with failure recovery

## CLI Commands
```bash
# Run interactively
python -m storyteller.main run

# Tell specific story
python -m storyteller.main tell "bir kedi hakk1nda hikaye"

# System status
python -m storyteller.main status

# Hardware test
python -m storyteller.main test

# Simulate wake word
python -m storyteller.main wake
```

## Web Interface
- **URL**: `http://pi-ip:5000`
- **Features**: Story library, playback history, scheduling, system configuration
- **Proxy**: Nginx reverse proxy (on full OS installs)

## Monitoring & Debugging

### Log Locations
- **Application**: `/var/log/storyteller.log`
- **System Service**: `sudo journalctl -u storyteller -f`
- **Debug Level**: Configurable via `LOG_LEVEL` environment variable

### Common Issues & Solutions
1. **502 Bad Gateway**: Service not running, check systemd status
2. **Memory Limit Exceeded**: Reduce concurrent requests, check for memory leaks
3. **Audio Device Not Found**: Verify hardware profile, check `aplay -l`
4. **Wake Word Not Detecting**: Check microphone permissions, audio sample rate
5. **API Errors**: Verify API keys, check network connectivity

## Development Guidelines

### Code Standards
- **Python 3.9+**: Minimum version requirement
- **Type Hints**: Required for all functions and variables
- **Async/Await**: Preferred for I/O operations
- **Error Handling**: Comprehensive exception handling with logging
- **Testing**: Unit tests with pytest and pytest-asyncio

### Resource Constraints
- **Memory**: Never exceed 400MB RAM usage
- **CPU**: Optimize for ARM Cortex-A53 (Pi Zero 2W)
- **Storage**: Minimize disk I/O, use efficient data structures
- **Network**: Handle intermittent connectivity gracefully

## Future Considerations

### Potential Enhancements
- **Multi-Language Support**: Extend beyond Turkish and English
- **Custom Wake Words**: User-trainable wake word models
- **Offline TTS**: Local TTS for improved privacy and reliability
- **Voice Cloning**: Personalized parent/guardian voice synthesis
- **Story Continuity**: Multi-session story continuation
- **Smart Scheduling**: Adaptive scheduling based on child's sleep patterns

### Technical Debt
- **Security Hardening**: Re-enable systemd security features after stability
- **Configuration Validation**: More robust settings validation
- **Error Recovery**: Better handling of API failures and network issues
- **Performance Optimization**: Further memory usage reduction
- **Testing Coverage**: Expand unit and integration test coverage

## Repository Information
- **GitHub**: https://github.com/sarpel/BedtimeStoryTeller.git
- **Main Branch**: `main`
- **Latest Commit**: Service path fixes and Pydantic v2 compatibility
- **License**: MIT License (assumed)

## Contact & Support
This is a personal project for creating a child-friendly storytelling device. The system prioritizes safety, reliability, and age-appropriate content above all else.