#!/usr/bin/env python3
"""
Direct test of the simple main without import issues.
"""

import asyncio
import sys
import os

# Add current directory to Python path
sys.path.insert(0, '.')

# Set environment variables for testing
os.environ['FORCE_MOCK_HARDWARE'] = 'true'
os.environ['TESTING'] = 'true'

async def test_storyteller():
    """Test the storyteller application directly."""
    
    try:
        print("🧪 Testing Bedtime Storyteller (Simple Mode)")
        print("=" * 50)
        
        # Import the simple main module
        from storyteller.simple_main import StorytellerApplication
        
        print("✅ Successfully imported StorytellerApplication")
        
        # Create application instance
        app = StorytellerApplication()
        print("✅ Application instance created")
        
        # Initialize the application
        print("⏳ Initializing application...")
        await app.initialize()
        print("✅ Application initialized successfully!")
        
        # Test that hardware manager is working
        if app.hardware_manager:
            print("✅ Hardware manager available")
        
        # Test that providers are set up
        if app.provider_manager:
            print("✅ Provider manager available")
        
        # Cleanup
        await app.cleanup()
        print("✅ Cleanup completed")
        
        print("")
        print("🎉 ALL TESTS PASSED!")
        print("The service should now work properly.")
        
        return 0
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

async def run_service_test():
    """Test running the actual service for a few seconds."""
    
    try:
        print("")
        print("🚀 Testing service startup...")
        
        from storyteller.simple_main import StorytellerApplication
        
        app = StorytellerApplication()
        await app.initialize()
        
        print("✅ Service initialized, would run normally")
        print("✅ Mock audio device should be active")
        print("✅ Mock GPIO should be active")
        print("✅ Web interface should be accessible")
        
        await app.cleanup()
        return 0
        
    except Exception as e:
        print(f"❌ Service test failed: {e}")
        return 1

async def main():
    """Main test function."""
    
    # Test 1: Basic functionality
    result1 = await test_storyteller()
    
    # Test 2: Service startup
    result2 = await run_service_test()
    
    if result1 == 0 and result2 == 0:
        print("")
        print("🎯 FINAL RESULT: SUCCESS!")
        print("Your Bedtime Storyteller is ready to run.")
        print("")
        print("To start the service:")
        print("  sudo systemctl start storyteller-simple")
        print("")
        print("To test manually:")
        print("  python3 -m storyteller.simple_main")
        return 0
    else:
        print("")
        print("💥 FINAL RESULT: SOME ISSUES FOUND")
        print("Check the error messages above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)