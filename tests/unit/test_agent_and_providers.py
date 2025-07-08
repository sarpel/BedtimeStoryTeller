import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import httpx
import json

# Add project root to the Python path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from storyteller.core.agent import StorytellingAgent, StorySession, AgentState
from storyteller.storage.story_library import StoryLibrary
from storyteller.providers.llm.openai_provider import OpenAILLMProvider
from storyteller.providers.base import ProviderError

@pytest.mark.asyncio
async def test_agent_awaits_callbacks():
    """
    Verifies that the StorytellingAgent correctly awaits the
    on_story_started and on_story_completed callbacks.
    """
    # GIVEN a StorytellingAgent with mocked dependencies and async callbacks
    mock_provider_manager = MagicMock()
    mock_hardware_manager = MagicMock()
    mock_safety_filter = MagicMock()
    
    agent = StorytellingAgent(mock_provider_manager, mock_hardware_manager, mock_safety_filter)
    agent.is_running = True # Simulate initialization
    
    # Mock the story pipeline to avoid running the full generation
    agent._execute_story_pipeline = AsyncMock()

    # Mock the async callbacks
    agent.on_story_started = AsyncMock()
    agent.on_story_completed = AsyncMock()

    # WHEN tell_story is called
    await agent.tell_story("A story about a brave little robot.")

    # THEN the callbacks should have been awaited
    agent.on_story_started.assert_awaited_once()
    agent.on_story_completed.assert_awaited_once()

@pytest.mark.asyncio
async def test_log_event_in_transaction(tmp_path):
    """
    Verifies that log_event flushes instead of committing when inside
    an existing transaction, preventing session errors.
    """
    # GIVEN a StoryLibrary with a mocked session
    mock_session = AsyncMock()
    mock_session.in_transaction.return_value = True # Simulate being in a transaction
    library = StoryLibrary(mock_session)

    # WHEN log_event is called
    await library.log_event("test_event", "This is a test")

    # THEN flush should be called, but commit should not
    mock_session.add.assert_called_once()
    mock_session.flush.assert_awaited_once()
    mock_session.commit.assert_not_awaited()

@pytest.mark.asyncio
async def test_openai_provider_handles_network_error():
    """
    Verifies that the OpenAILLMProvider correctly handles httpx.RequestError
    and wraps it in a ProviderError.
    """
    # GIVEN an OpenAI provider
    provider = OpenAILLMProvider(api_key="test_key")

    # WHEN a request is made that results in a network error
    with patch('httpx.AsyncClient.stream', side_effect=httpx.ConnectError("Connection failed")):
        with pytest.raises(ProviderError) as excinfo:
            # The async generator needs to be iterated to trigger the code
            async for _ in provider.generate_story_stream(MagicMock()):
                pass

    # THEN a ProviderError should be raised with the correct details
    assert excinfo.value.error_type == "network_error"
    assert "ConnectError" in excinfo.value.message
