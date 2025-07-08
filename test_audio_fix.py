#!/usr/bin/env python3
"""
Test script to verify audio fallback fixes.
"""

import asyncio
import logging
import os
import sys

# Add the storyteller module to path
sys.path.insert(0, '.')

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_audio_initialization():
    """Test audio device initialization with fallbacks."""
    
    # Set mock hardware mode
    os.environ['FORCE_MOCK_HARDWARE'] = 'true'
    
    try:
        from storyteller.config.hardware_profiles import detect_hardware_profile
        from storyteller.hal.audio_devices import create_audio_device
        from storyteller.config.settings import get_settings
        
        logger.info("Starting audio initialization test...")
        
        # Get settings
        settings = get_settings()
        logger.info(f"Force mock hardware: {settings.force_mock_hardware}")
        
        # Detect hardware profile
        hardware_profile = detect_hardware_profile()
        logger.info(f"Detected hardware profile: {hardware_profile.model.value}")
        logger.info(f"Audio config: {hardware_profile.audio}")
        
        # Create audio device
        audio_device = await create_audio_device(hardware_profile.audio)
        logger.info(f"Created audio device: {type(audio_device).__name__}")
        
        # Initialize audio device
        await audio_device.initialize()
        logger.info("Audio device initialized successfully")
        
        # Test audio device status
        if hasattr(audio_device, 'get_status'):
            status = await audio_device.get_status()
            logger.info(f"Audio device status: {status}")
        
        # Test mock audio playback
        test_audio_data = b'\x00\x01' * 1000  # Small test audio
        await audio_device.play_audio(test_audio_data)
        logger.info("Test audio playback completed")
        
        # Cleanup
        await audio_device.cleanup()
        logger.info("Audio device cleanup completed")
        
        logger.info("✅ Audio initialization test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Audio initialization test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_main_app_initialization():
    """Test main application initialization."""
    
    # Set mock hardware mode
    os.environ['FORCE_MOCK_HARDWARE'] = 'true'
    os.environ['TESTING'] = 'true'
    
    try:
        from storyteller.main import StorytellerApplication
        
        logger.info("Starting main application test...")
        
        # Create application
        app = StorytellerApplication()
        
        # Initialize (this should not fail now)
        await app.initialize()
        logger.info("Application initialized successfully")
        
        # Check if hardware manager is available
        if app.hardware_manager:
            logger.info("Hardware manager is available")
        
        # Check if provider manager is available
        if app.provider_manager:
            logger.info("Provider manager is available")
        
        # Cleanup
        await app.cleanup()
        logger.info("Application cleanup completed")
        
        logger.info("✅ Main application test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Main application test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    logger.info("🧪 Starting Bedtime Storyteller Audio Fix Tests")
    logger.info("=" * 60)
    
    results = []
    
    # Test 1: Audio initialization
    logger.info("Test 1: Audio Device Initialization")
    results.append(await test_audio_initialization())
    logger.info("-" * 40)
    
    # Test 2: Main application initialization
    logger.info("Test 2: Main Application Initialization")
    results.append(await test_main_app_initialization())
    logger.info("-" * 40)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    logger.info("📊 TEST SUMMARY")
    logger.info(f"Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! The audio fix is working.")
        return 0
    else:
        logger.error("💥 Some tests failed. Check the logs above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)