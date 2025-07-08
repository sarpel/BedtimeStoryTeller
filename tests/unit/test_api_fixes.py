import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to the Python path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from storyteller.web.app import WebApplication
from storyteller.storage.story_library import StoryLibrary
from storyteller.hal.interface import HardwareManager

@pytest.fixture
def web_app_fixture():
    """Provides a test instance of the WebApplication."""
    # Mock dependencies that are initialized outside the app constructor
    with patch('storyteller.web.app.get_settings', return_value=MagicMock()):
        app = WebApplication()
    
    # Mock the agent and its managers
    app.agent = MagicMock()
    app.agent.hardware_manager = AsyncMock(spec=HardwareManager)
    app.agent.hardware_manager.get_hardware_info.return_value = {"status": "ok"}
    app.agent.get_status.return_value = {"state": "idle", "is_running": True}
    app.agent.provider_manager.health_check.return_value = {"llm": "ok", "tts": "ok"}

    # Mock the story library
    app.story_library = AsyncMock(spec=StoryLibrary)
    app.story_library.get_recent_sessions.return_value = []

    return app

@pytest.mark.asyncio
async def test_get_status_endpoint_calls_get_hardware_info(web_app_fixture):
    """
    Verifies that the /api/status endpoint correctly calls get_hardware_info
    on the HardwareManager, not the old get_status method.
    """
    # GIVEN a web app with a mocked HardwareManager
    app = web_app_fixture
    
    # WHEN the /api/status endpoint is called
    # We can call the function directly since we are testing the logic, not the routing
    status_func = None
    for route in app.app.routes:
        if route.path == "/api/status":
            status_func = route.endpoint
            break
    
    assert status_func is not None, "Could not find /api/status route"
    
    await status_func()

    # THEN the get_hardware_info method should be called
    app.agent.hardware_manager.get_hardware_info.assert_called_once()
    # Ensure the old, incorrect method is not called
    app.agent.hardware_manager.get_status.assert_not_called()

@pytest.mark.asyncio
async def test_list_stories_endpoint_handles_offset(web_app_fixture):
    """
    Verifies that the /api/stories endpoint correctly calls get_recent_sessions
    with both limit and offset parameters.
    """
    # GIVEN a web app with a mocked StoryLibrary
    app = web_app_fixture
    
    # WHEN the /api/stories endpoint is called with an offset
    list_stories_func = None
    for route in app.app.routes:
        if route.path == "/api/stories" and "get" in route.methods:
            list_stories_func = route.endpoint
            break
            
    assert list_stories_func is not None, "Could not find GET /api/stories route"

    await list_stories_func(limit=10, offset=5)

    # THEN the get_recent_sessions method should be called with the correct offset
    app.story_library.get_recent_sessions.assert_called_once_with(limit=10, offset=5)
