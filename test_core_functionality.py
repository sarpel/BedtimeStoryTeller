#!/usr/bin/env python3
"""
Test core functionality without CLI dependencies.
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

async def test_core_initialization():
    """Test core application initialization without CLI."""
    
    # Force mock hardware mode
    os.environ['FORCE_MOCK_HARDWARE'] = 'true'
    os.environ['TESTING'] = 'true'
    
    try:
        # Test configuration
        from storyteller.config.settings import get_settings
        settings = get_settings()
        logger.info(f"✅ Settings loaded. Force mock: {settings.force_mock_hardware}")
        
        # Test hardware profile detection
        from storyteller.config.hardware_profiles import detect_hardware_profile
        profile = detect_hardware_profile()
        logger.info(f"✅ Hardware profile detected: {profile.model.value}")
        
        # Test audio device creation
        from storyteller.hal.audio_devices import create_audio_device, MockAudioDevice
        audio_device = await create_audio_device(profile.audio)
        logger.info(f"✅ Audio device created: {type(audio_device).__name__}")
        
        # Test audio initialization
        await audio_device.initialize()
        logger.info("✅ Audio device initialized")
        
        # Test mock audio functionality
        if isinstance(audio_device, MockAudioDevice):
            test_audio = b'\x00\x01' * 100
            await audio_device.play_audio(test_audio)
            logger.info("✅ Mock audio playback successful")
        
        # Test GPIO manager creation
        from storyteller.hal.gpio_manager import create_gpio_manager, MockGPIOManager
        gpio_manager = await create_gpio_manager()
        await gpio_manager.initialize()
        logger.info(f"✅ GPIO manager created: {type(gpio_manager).__name__}")
        
        # Test provider manager
        from storyteller.providers.base import ProviderManager
        provider_manager = ProviderManager()
        logger.info("✅ Provider manager created")
        
        # Test hardware manager
        from storyteller.hal.interface import HardwareManager
        hardware_manager = HardwareManager()
        await hardware_manager.initialize(audio_device, gpio_manager)
        logger.info("✅ Hardware manager initialized")
        
        # Test core agent (without providers for now)
        from storyteller.core.agent import StorytellingAgent
        agent = StorytellingAgent(
            provider_manager=provider_manager,
            hardware_manager=hardware_manager
        )
        logger.info("✅ Storytelling agent created")
        
        # Initialize agent without full initialization
        # (since we don't have API keys in test environment)
        # await agent.initialize()
        
        # Cleanup
        await audio_device.cleanup()
        await gpio_manager.cleanup()
        await hardware_manager.cleanup()
        
        logger.info("🎉 Core functionality test PASSED!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Core functionality test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_mock_story_session():
    """Test mock story session functionality."""
    
    os.environ['FORCE_MOCK_HARDWARE'] = 'true'
    
    try:
        from storyteller.core.story_generator import StoryRequest, StorySession
        from storyteller.utils.safety_filter import SafetyFilter
        
        # Create a story request
        request = StoryRequest(
            prompt="Tell me about a friendly cat",
            language="en",
            age_rating="5+",
            max_paragraphs=3
        )
        logger.info(f"✅ Story request created: {request.prompt}")
        
        # Create a story session
        session = StorySession(request)
        logger.info(f"✅ Story session created: {session.session_id}")
        
        # Test safety filter
        safety_filter = SafetyFilter(target_age=5, language="en")
        safe_text = "The friendly cat played in the garden."
        is_safe = safety_filter.is_content_safe(safe_text)
        logger.info(f"✅ Safety filter test: {is_safe}")
        
        logger.info("🎉 Mock story session test PASSED!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Mock story session test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_database_functionality():
    """Test database functionality."""
    
    try:
        from storyteller.storage.models import create_database_engine, create_tables
        
        # Create in-memory database for testing
        engine = await create_database_engine("sqlite+aiosqlite:///:memory:")
        logger.info("✅ Database engine created")
        
        # Create tables
        await create_tables(engine)
        logger.info("✅ Database tables created")
        
        # Test story library
        from storyteller.storage.story_library import StoryLibrary
        from storyteller.storage.models import get_database_session
        
        session = await get_database_session(engine)
        story_library = StoryLibrary(session)
        logger.info("✅ Story library created")
        
        # Cleanup
        await engine.dispose()
        
        logger.info("🎉 Database functionality test PASSED!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database functionality test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all core functionality tests."""
    logger.info("🧪 Starting Core Functionality Tests")
    logger.info("=" * 60)
    
    results = []
    
    # Test 1: Core initialization
    logger.info("Test 1: Core System Initialization")
    results.append(await test_core_initialization())
    logger.info("-" * 40)
    
    # Test 2: Mock story session
    logger.info("Test 2: Mock Story Session")
    results.append(await test_mock_story_session())
    logger.info("-" * 40)
    
    # Test 3: Database functionality
    logger.info("Test 3: Database Functionality")
    results.append(await test_database_functionality())
    logger.info("-" * 40)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    logger.info("📊 TEST SUMMARY")
    logger.info(f"Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("🎉 ALL CORE TESTS PASSED! System is ready.")
        return 0
    else:
        logger.error("💥 Some core tests failed. Check the logs above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)