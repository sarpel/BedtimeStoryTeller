"""
Integration tests for the complete story generation pipeline.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from storyteller.core.agent import StorytellingAgent, AgentState
from storyteller.core.story_generator import StoryRequest, StorySession


class TestStoryPipeline:
    """Test the complete story generation pipeline."""
    
    @pytest.fixture
    async def story_agent(self, mock_provider_manager, mock_hardware_manager, mock_safety_filter):
        """Create a story agent for testing."""
        agent = StorytellingAgent(
            provider_manager=mock_provider_manager,
            hardware_manager=mock_hardware_manager,
            safety_filter=mock_safety_filter
        )
        await agent.initialize()
        return agent
    
    @pytest.mark.asyncio
    async def test_complete_story_generation_flow(
        self, 
        story_agent, 
        sample_story_request,
        mock_llm_provider,
        mock_tts_provider
    ):
        """Test complete story generation from request to audio output."""
        
        # Setup mock responses
        story_chunks = [
            "Once upon a time, there was a little cat.",
            "The cat lived in a beautiful garden.",
            "Every day, the cat would play with butterflies.",
            "And they all lived happily ever after."
        ]
        
        async def mock_story_stream():
            for chunk in story_chunks:
                yield chunk
                await asyncio.sleep(0.1)  # Simulate streaming delay
        
        mock_llm_provider.generate_story_stream.return_value = mock_story_stream()
        mock_tts_provider.synthesize_speech.return_value = b'fake_audio_data'
        
        # Start story generation
        session = await story_agent.tell_story(sample_story_request.prompt)
        
        # Wait for story to complete
        timeout = 5.0
        start_time = asyncio.get_event_loop().time()
        
        while session.status != "completed" and (asyncio.get_event_loop().time() - start_time) < timeout:
            await asyncio.sleep(0.1)
        
        # Verify story generation
        assert session.status == "completed"
        assert session.paragraphs_generated == len(story_chunks)
        
        # Verify LLM was called
        mock_llm_provider.generate_story_stream.assert_called_once()
        
        # Verify TTS was called for each chunk
        assert mock_tts_provider.synthesize_speech.call_count == len(story_chunks)
    
    @pytest.mark.asyncio
    async def test_concurrent_story_requests(self, story_agent, mock_llm_provider):
        """Test handling of concurrent story requests."""
        
        # Setup mock for concurrent requests
        async def mock_story_stream():
            yield "Story content"
            await asyncio.sleep(0.5)
        
        mock_llm_provider.generate_story_stream.return_value = mock_story_stream()
        
        # Start first story
        session1 = await story_agent.tell_story("First story")
        
        # Try to start second story while first is running
        with pytest.raises(RuntimeError, match="Agent is busy"):
            await story_agent.tell_story("Second story")
        
        # Wait for first story to complete
        await asyncio.sleep(1.0)
        
        # Now second story should work
        session2 = await story_agent.tell_story("Second story")
        assert session2.session_id != session1.session_id
    
    @pytest.mark.asyncio
    async def test_story_pipeline_with_safety_filtering(
        self, 
        story_agent,
        mock_llm_provider,
        mock_safety_filter
    ):
        """Test story pipeline with safety filtering."""
        
        # Setup unsafe content
        unsafe_chunks = [
            "Once upon a time, there was a scary monster.",
            "The monster attacked everyone in the village.",
            "Blood was everywhere."
        ]
        
        safe_chunks = [
            "Once upon a time, there was a friendly dragon.",
            "The dragon helped everyone in the village.", 
            "Everyone was happy."
        ]
        
        async def mock_unsafe_stream():
            for chunk in unsafe_chunks:
                yield chunk
        
        mock_llm_provider.generate_story_stream.return_value = mock_unsafe_stream()
        
        # Configure safety filter to detect unsafe content and provide replacements
        def mock_filter_content(text):
            if "scary" in text or "monster" in text or "attacked" in text or "blood" in text:
                # Return safe replacement
                index = unsafe_chunks.index(text) if text in unsafe_chunks else 0
                return safe_chunks[min(index, len(safe_chunks) - 1)]
            return text
        
        mock_safety_filter.is_content_safe.side_effect = lambda text: "scary" not in text and "blood" not in text
        mock_safety_filter.filter_content.side_effect = mock_filter_content
        
        # Generate story
        session = await story_agent.tell_story("Tell me a story")
        
        # Wait for completion
        await asyncio.sleep(1.0)
        
        # Verify safety filter was called
        assert mock_safety_filter.is_content_safe.call_count > 0
        assert mock_safety_filter.filter_content.call_count > 0
    
    @pytest.mark.asyncio
    async def test_story_pipeline_error_handling(
        self,
        story_agent,
        mock_llm_provider,
        mock_tts_provider,
        network_error
    ):
        """Test error handling in story pipeline."""
        
        # Test LLM provider error
        mock_llm_provider.generate_story_stream.side_effect = network_error
        
        with pytest.raises(Exception):
            await story_agent.tell_story("Test story")
        
        # Verify agent returns to idle state after error
        assert story_agent.state == AgentState.IDLE
        
        # Test TTS provider error
        mock_llm_provider.generate_story_stream.side_effect = None
        async def mock_story_stream():
            yield "Test content"
        mock_llm_provider.generate_story_stream.return_value = mock_story_stream()
        
        mock_tts_provider.synthesize_speech.side_effect = network_error
        
        session = await story_agent.tell_story("Test story")
        await asyncio.sleep(0.5)
        
        # Should handle TTS error gracefully
        assert session.status in ["failed", "completed"]
    
    @pytest.mark.asyncio
    async def test_story_session_lifecycle(self, story_agent, mock_llm_provider):
        """Test story session lifecycle and state transitions."""
        
        # Setup mock story stream
        async def mock_story_stream():
            yield "Part 1"
            await asyncio.sleep(0.1)
            yield "Part 2"
            await asyncio.sleep(0.1)
            yield "Part 3"
        
        mock_llm_provider.generate_story_stream.return_value = mock_story_stream()
        
        # Track state changes
        state_changes = []
        
        def track_state_change(new_state):
            state_changes.append(new_state)
        
        story_agent.on_state_change = track_state_change
        
        # Start story
        session = await story_agent.tell_story("Test story")
        
        # Initial state should be active
        assert session.status == "active"
        
        # Wait for completion
        await asyncio.sleep(1.0)
        
        # Verify state transitions
        assert AgentState.PROCESSING in state_changes
        assert AgentState.PLAYING in state_changes or AgentState.IDLE in state_changes
    
    @pytest.mark.asyncio
    async def test_story_content_streaming(self, story_agent, mock_llm_provider, mock_tts_provider):
        """Test streaming of story content and audio generation."""
        
        story_parts = [
            "Once upon a time, in a magical forest,",
            "there lived a wise old owl named Oliver.",
            "Oliver loved to tell stories to young animals.",
            "One day, a little rabbit came to visit.",
            "And that's how their friendship began."
        ]
        
        async def mock_story_stream():
            for part in story_parts:
                yield part
                await asyncio.sleep(0.1)
        
        mock_llm_provider.generate_story_stream.return_value = mock_story_stream()
        
        # Track audio synthesis calls
        audio_calls = []
        
        async def track_audio_synthesis(text, **kwargs):
            audio_calls.append(text)
            return b'fake_audio_' + text.encode()
        
        mock_tts_provider.synthesize_speech.side_effect = track_audio_synthesis
        
        # Start story generation
        session = await story_agent.tell_story("Tell me about Oliver the owl")
        
        # Wait for streaming to complete
        await asyncio.sleep(2.0)
        
        # Verify all parts were processed
        assert len(audio_calls) == len(story_parts)
        
        # Verify content was streamed in order
        for i, expected_part in enumerate(story_parts):
            assert expected_part in audio_calls[i]
    
    @pytest.mark.asyncio
    async def test_memory_usage_during_story_generation(
        self,
        story_agent,
        mock_llm_provider,
        performance_monitor
    ):
        """Test memory usage during story generation."""
        
        # Create a longer story to test memory usage
        async def mock_long_story():
            for i in range(20):  # Generate 20 paragraphs
                yield f"This is paragraph {i+1} of a longer story for memory testing."
                await asyncio.sleep(0.05)
        
        mock_llm_provider.generate_story_stream.return_value = mock_long_story()
        
        performance_monitor.start()
        
        # Generate story
        session = await story_agent.tell_story("Long story for memory test")
        
        # Wait for completion
        await asyncio.sleep(3.0)
        
        metrics = performance_monitor.stop()
        
        # Memory usage should be reasonable (less than 100MB increase)
        assert metrics["memory_delta"] < 100 * 1024 * 1024
        
        # Story should complete successfully
        assert session.paragraphs_generated > 0
    
    @pytest.mark.asyncio
    async def test_audio_playback_synchronization(
        self,
        story_agent,
        mock_llm_provider,
        mock_tts_provider,
        mock_hardware_manager
    ):
        """Test synchronization between story generation and audio playback."""
        
        story_chunks = ["Part 1", "Part 2", "Part 3"]
        audio_chunks = [b'audio1', b'audio2', b'audio3']
        
        async def mock_story_stream():
            for chunk in story_chunks:
                yield chunk
                await asyncio.sleep(0.2)
        
        # Mock TTS to return different audio for each chunk
        async def mock_tts(text, **kwargs):
            index = story_chunks.index(text) if text in story_chunks else 0
            return audio_chunks[index]
        
        mock_llm_provider.generate_story_stream.return_value = mock_story_stream()
        mock_tts_provider.synthesize_speech.side_effect = mock_tts
        
        # Track audio playback calls
        playback_calls = []
        
        async def track_audio_playback(audio_data):
            playback_calls.append(audio_data)
        
        mock_hardware_manager.audio.play_audio.side_effect = track_audio_playback
        
        # Start story
        session = await story_agent.tell_story("Synchronization test")
        
        # Wait for completion
        await asyncio.sleep(2.0)
        
        # Verify audio was played for each chunk
        assert len(playback_calls) == len(story_chunks)
        
        # Verify audio chunks were played in order
        for i, expected_audio in enumerate(audio_chunks):
            assert playback_calls[i] == expected_audio
    
    @pytest.mark.asyncio
    async def test_story_cancellation(self, story_agent, mock_llm_provider):
        """Test cancellation of ongoing story generation."""
        
        # Create a long-running story stream
        async def mock_infinite_story():
            i = 0
            while True:
                yield f"This is part {i} of an infinite story."
                i += 1
                await asyncio.sleep(0.5)
        
        mock_llm_provider.generate_story_stream.return_value = mock_infinite_story()
        
        # Start story
        session = await story_agent.tell_story("Infinite story")
        
        # Let it run for a bit
        await asyncio.sleep(1.0)
        
        # Cancel the story
        await story_agent.stop_current_story()
        
        # Verify agent returns to idle state
        assert story_agent.state == AgentState.IDLE
        
        # Verify session is marked as cancelled or stopped
        assert session.status in ["cancelled", "stopped", "failed"]


if __name__ == "__main__":
    pytest.main([__file__])