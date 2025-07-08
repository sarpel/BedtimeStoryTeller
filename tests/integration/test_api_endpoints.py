import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

# It's important to set up the test environment before other imports
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ..test_utils import setup_test_environment
setup_test_environment()

from storyteller.web.app import create_app
from storyteller.core.agent import StorytellingAgent
from storyteller.storage.story_library import StoryLibrary
from storyteller.hal.interface import HardwareManager

@pytest.fixture
def mock_agent():
    """Provides a mock StorytellingAgent."""
    agent = MagicMock(spec=StorytellingAgent)
    agent.get_status = MagicMock(return_value={
        "state": "idle",
        "is_running": True,
        "current_session": None,
        "stats": {"stories_told": 5}
    })
    
    # Mock the hardware manager on the agent
    agent.hardware_manager = MagicMock(spec=HardwareManager)
    agent.hardware_manager.get_hardware_info = MagicMock(return_value={
        "audio": {"available": True},
        "gpio": {"available": True}
    })
    
    # Mock the provider manager
    agent.provider_manager = MagicMock()
    agent.provider_manager.health_check = AsyncMock(return_value={
        "llm_provider": {"status": "ok"},
        "tts_provider": {"status": "ok"}
    })
    
    return agent

@pytest.fixture
def mock_story_library():
    """Provides a mock StoryLibrary."""
    library = MagicMock(spec=StoryLibrary)
    library.get_recent_sessions = AsyncMock(return_value=[])
    return library

@pytest.fixture
def client(mock_agent, mock_story_library):
    """Provides a TestClient for the FastAPI app."""
    app = create_app()
    
    # Use dependency overrides to inject mocks
    from storyteller.web.app import web_app
    web_app.agent = mock_agent
    web_app.story_library = mock_story_library
    
    with TestClient(app) as test_client:
        yield test_client

def test_get_status_endpoint(client, mock_agent):
    """
    Tests the /api/status endpoint.
    Verifies that it calls get_hardware_info instead of get_status.
    """
    response = client.get("/api/status")
    
    assert response.status_code == 200
    
    # Verify that the correct hardware method was called
    mock_agent.hardware_manager.get_hardware_info.assert_called_once()
    
    # Check the response body
    data = response.json()
    assert data["state"] == "idle"
    assert data["hardware_status"]["audio"]["available"] is True

def test_list_stories_endpoint(client, mock_story_library):
    """
    Tests the /api/stories endpoint.
    Verifies that it correctly handles limit and offset parameters.
    """
    response = client.get("/api/stories?limit=10&offset=5")
    
    assert response.status_code == 200
    
    # Verify that get_recent_sessions was called with the correct arguments
    mock_story_library.get_recent_sessions.assert_called_once_with(limit=10, offset=5)
    
    # Check the response body
    assert response.json() == []