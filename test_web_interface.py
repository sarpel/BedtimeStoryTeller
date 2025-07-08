#!/usr/bin/env python3
"""
Test script to verify web interface is working.
"""

import asyncio
import sys
import os
import time
import requests
from urllib.parse import urljoin

# Add current directory to Python path
sys.path.insert(0, '.')

# Force mock hardware
os.environ['FORCE_MOCK_HARDWARE'] = 'true'

async def test_web_interface():
    """Test that the web interface is accessible."""
    
    print("🌐 Testing web interface...")
    
    try:
        from storyteller.main import StorytellerApplication
        
        # Create and initialize app
        app = StorytellerApplication()
        await app.initialize()
        
        # Start the application in background
        print("🚀 Starting service...")
        service_task = asyncio.create_task(app.run())
        
        # Wait for web server to start
        await asyncio.sleep(5)
        
        # Test web interface accessibility
        base_url = "http://localhost:5000"
        
        print(f"🔗 Testing web interface at {base_url}")
        
        # Test basic endpoints
        endpoints = [
            "/",
            "/api/status",
            "/api/stories"
        ]
        
        success_count = 0
        
        for endpoint in endpoints:
            try:
                url = urljoin(base_url, endpoint)
                response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    print(f"✅ {endpoint} - OK (200)")
                    success_count += 1
                else:
                    print(f"⚠️  {endpoint} - Status {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(f"❌ {endpoint} - Connection refused")
            except requests.exceptions.Timeout:
                print(f"❌ {endpoint} - Timeout")
            except Exception as e:
                print(f"❌ {endpoint} - Error: {e}")
        
        # Shutdown
        await app.shutdown()
        
        # Wait for cleanup
        try:
            await asyncio.wait_for(service_task, timeout=10)
        except asyncio.TimeoutError:
            print("⚠️  Service shutdown timed out")
        
        await app.cleanup()
        
        if success_count >= 2:
            print(f"")
            print(f"🎉 SUCCESS: Web interface is working!")
            print(f"✅ {success_count}/{len(endpoints)} endpoints accessible")
            print(f"")
            print(f"You can now access the web interface at:")
            print(f"  http://192.168.1.48:5000")
            return True
        else:
            print(f"")
            print(f"❌ FAILED: Web interface has issues")
            print(f"Only {success_count}/{len(endpoints)} endpoints accessible")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_web_interface())
    sys.exit(0 if success else 1)