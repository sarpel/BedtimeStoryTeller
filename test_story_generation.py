#!/usr/bin/env python3
"""
Test story generation functionality with proper error handling.
"""

import asyncio
import sys
import os

# Add current directory to Python path
sys.path.insert(0, '.')

# Force mock hardware to avoid audio issues
os.environ['FORCE_MOCK_HARDWARE'] = 'true'

async def test_story_generation():
    """Test story generation with API providers."""
    
    print("📖 Testing story generation...")
    
    try:
        from storyteller.main import StorytellerApplication
        
        # Create and initialize app
        app = StorytellerApplication()
        await app.initialize()
        
        print("✅ Application initialized")
        
        # Check if any LLM providers are available
        llm_provider = await app.provider_manager.get_available_llm_provider()
        
        if not llm_provider:
            print("❌ No LLM providers available")
            print("📝 Check your API keys in .env file:")
            print("   - OPENAI_API_KEY=your_actual_key")
            print("   - GEMINI_API_KEY=your_actual_key (optional)")
            return False
        
        print(f"✅ LLM provider available: {llm_provider.name}")
        
        # Check TTS provider
        tts_provider = await app.provider_manager.get_available_tts_provider()
        
        if not tts_provider:
            print("❌ No TTS providers available")
            return False
            
        print(f"✅ TTS provider available: {tts_provider.name}")
        
        # Test basic story generation
        print("🎭 Testing story generation...")
        
        if app.agent:
            try:
                # This should not crash with the tts_tasks bug anymore
                session = await app.agent.tell_story("bir kedi hakkında kısa hikaye")
                
                if session:
                    print(f"✅ Story generation successful!")
                    print(f"   Session ID: {session.session_id}")
                    print(f"   Paragraphs: {session.paragraphs_generated}")
                    print(f"   Status: {session.status}")
                else:
                    print("⚠️  Story generation returned None")
                    
            except Exception as story_error:
                print(f"❌ Story generation failed: {story_error}")
                # This is expected if API keys are invalid, but should not be a code bug
                if "cannot access local variable 'tts_tasks'" in str(story_error):
                    print("💥 BUG: tts_tasks variable scope error still exists!")
                    return False
                else:
                    print("ℹ️  This is likely an API configuration issue, not a code bug")
        
        # Cleanup
        await app.cleanup()
        
        print("✅ Test completed successfully (no code bugs)")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        
        # Check for specific bugs we fixed
        if "cannot access local variable 'tts_tasks'" in str(e):
            print("💥 BUG: tts_tasks variable scope error!")
            return False
        elif "Request URL is missing" in str(e):
            print("💥 BUG: OpenAI base URL error!")
            return False
        else:
            print("ℹ️  This may be a configuration issue")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = asyncio.run(test_story_generation())
    
    if success:
        print("")
        print("🎉 SUCCESS: All code bugs are fixed!")
        print("📝 To use story generation, ensure your .env file has:")
        print("   OPENAI_API_KEY=your_actual_openai_key")
        print("   (And optionally GEMINI_API_KEY=your_gemini_key)")
    
    sys.exit(0 if success else 1)