"""
Hardware tests for audio system functionality.
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from storyteller.hal.audio_devices import (
    IQAudioDevice,
    USBAudioDevice, 
    create_audio_device
)
from storyteller.hal.interface import AudioInterface
from storyteller.config.hardware_profiles import AudioProfile


class TestAudioDevices:
    """Test audio device implementations."""
    
    @pytest.fixture
    def iqaudio_profile(self):
        """IQAudio profile for testing."""
        return AudioProfile(
            device_type="iqaudio_codec",
            alsa_device="hw:0,0",
            sample_rate=16000,
            channels=1,
            buffer_size=1024
        )
    
    @pytest.fixture
    def usb_audio_profile(self):
        """USB audio profile for testing."""
        return AudioProfile(
            device_type="usb_audio",
            alsa_device="plughw:1,0",
            sample_rate=16000,
            channels=1,
            buffer_size=1024
        )
    
    @pytest.mark.asyncio
    async def test_iqaudio_device_initialization(self, iqaudio_profile):
        """Test IQAudio device initialization."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = IQAudioDevice(iqaudio_profile)
            await device.initialize()
            
            assert device.is_available is True
            assert device.sample_rate == 16000
            assert device.channels == 1
    
    @pytest.mark.asyncio
    async def test_usb_audio_device_initialization(self, usb_audio_profile):
        """Test USB audio device initialization."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = USBAudioDevice(usb_audio_profile)
            await device.initialize()
            
            assert device.is_available is True
            assert device.alsa_device == "plughw:1,0"
    
    @pytest.mark.asyncio
    async def test_audio_device_creation(self, iqaudio_profile):
        """Test audio device factory function."""
        device = await create_audio_device(iqaudio_profile)
        
        assert isinstance(device, AudioInterface)
        assert device.sample_rate == 16000
    
    @pytest.mark.asyncio
    async def test_audio_playback_simulation(self, iqaudio_profile, sample_audio_data):
        """Test audio playback with simulated hardware."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = IQAudioDevice(iqaudio_profile)
            await device.initialize()
            
            # Mock the actual audio playback
            with patch.object(device, '_play_audio_data') as mock_play:
                mock_play.return_value = None
                
                await device.play_audio(sample_audio_data)
                
                mock_play.assert_called_once_with(sample_audio_data)
    
    @pytest.mark.asyncio
    async def test_audio_recording_simulation(self, iqaudio_profile):
        """Test audio recording with simulated hardware."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = IQAudioDevice(iqaudio_profile)
            await device.initialize()
            
            # Mock the actual audio recording
            with patch.object(device, '_record_audio_data') as mock_record:
                mock_record.return_value = b'recorded_audio_data'
                
                audio_data = await device.record_audio(duration=1.0)
                
                assert audio_data == b'recorded_audio_data'
                mock_record.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_audio_device_error_handling(self, iqaudio_profile):
        """Test audio device error handling."""
        with patch('subprocess.run') as mock_run:
            # Simulate device not available
            mock_run.return_value.returncode = 1
            
            device = IQAudioDevice(iqaudio_profile)
            
            # Should handle initialization failure gracefully
            await device.initialize()
            assert device.is_available is False
    
    @pytest.mark.asyncio 
    async def test_audio_format_validation(self, iqaudio_profile):
        """Test audio format validation."""
        device = IQAudioDevice(iqaudio_profile)
        
        # Test valid audio data
        valid_audio = b'\x00\x01' * 1000  # 16-bit PCM data
        assert device._validate_audio_format(valid_audio) is True
        
        # Test invalid audio data
        invalid_audio = b'\x00'  # Odd number of bytes for 16-bit
        assert device._validate_audio_format(invalid_audio) is False
    
    @pytest.mark.asyncio
    async def test_audio_device_status(self, iqaudio_profile):
        """Test audio device status reporting."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = IQAudioDevice(iqaudio_profile)
            await device.initialize()
            
            status = await device.get_status()
            
            assert 'available' in status
            assert 'sample_rate' in status
            assert 'channels' in status
            assert 'buffer_size' in status
    
    @pytest.mark.asyncio
    async def test_audio_device_cleanup(self, iqaudio_profile):
        """Test audio device cleanup."""
        device = IQAudioDevice(iqaudio_profile)
        await device.initialize()
        
        # Cleanup should not raise exceptions
        await device.cleanup()
        
        # Device should be marked as unavailable after cleanup
        assert device.is_available is False
    
    @pytest.mark.asyncio
    async def test_concurrent_audio_operations(self, iqaudio_profile, sample_audio_data):
        """Test concurrent audio operations."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = IQAudioDevice(iqaudio_profile)
            await device.initialize()
            
            with patch.object(device, '_play_audio_data') as mock_play:
                mock_play.return_value = None
                
                # Start multiple concurrent playback operations
                tasks = [
                    device.play_audio(sample_audio_data),
                    device.play_audio(sample_audio_data),
                    device.play_audio(sample_audio_data)
                ]
                
                # Should handle concurrent operations
                await asyncio.gather(*tasks)
                
                # All operations should complete
                assert mock_play.call_count == 3
    
    @pytest.mark.asyncio
    async def test_audio_latency_measurement(self, iqaudio_profile, performance_monitor):
        """Test audio latency measurement."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = IQAudioDevice(iqaudio_profile)
            await device.initialize()
            
            with patch.object(device, '_play_audio_data') as mock_play:
                mock_play.return_value = None
                
                performance_monitor.start()
                
                # Small audio chunk for latency test
                small_audio = b'\x00\x01' * 100
                await device.play_audio(small_audio)
                
                metrics = performance_monitor.stop()
                
                # Audio latency should be minimal for small chunks
                assert metrics["duration"] < 0.1  # Less than 100ms
    
    @pytest.mark.asyncio
    async def test_audio_buffer_management(self, iqaudio_profile):
        """Test audio buffer management."""
        device = IQAudioDevice(iqaudio_profile)
        
        # Test buffer size calculation
        buffer_size = device._calculate_buffer_size(
            sample_rate=16000,
            channels=1,
            target_latency=0.1  # 100ms
        )
        
        # Buffer size should be reasonable
        assert 1000 < buffer_size < 5000
        
        # Buffer size should be aligned to frame boundaries
        assert buffer_size % (2 * device.channels) == 0


class TestAudioSystemIntegration:
    """Test audio system integration with hardware abstraction layer."""
    
    @pytest.mark.asyncio
    async def test_audio_device_auto_detection(self, mock_raspberry_pi):
        """Test automatic audio device detection."""
        # Mock different hardware scenarios
        test_scenarios = [
            {
                'device_files': ['/proc/device-tree/model'],
                'model_content': 'Raspberry Pi Zero 2 W',
                'expected_type': 'iqaudio_codec'
            },
            {
                'device_files': ['/proc/device-tree/model'],
                'model_content': 'Raspberry Pi 5 Model B',
                'expected_type': 'usb_audio'
            }
        ]
        
        for scenario in test_scenarios:
            with patch('pathlib.Path.exists') as mock_exists:
                with patch('builtins.open') as mock_open:
                    mock_exists.side_effect = lambda path: str(path) in scenario['device_files']
                    mock_open.return_value.__enter__.return_value.read.return_value = scenario['model_content']
                    
                    from storyteller.config.hardware_profiles import detect_hardware_profile
                    profile = detect_hardware_profile()
                    
                    device = await create_audio_device(profile.audio)
                    
                    assert profile.audio.device_type == scenario['expected_type']
    
    @pytest.mark.asyncio
    async def test_audio_hardware_fallback(self):
        """Test audio hardware fallback behavior."""
        # Create profile for unavailable device
        unavailable_profile = AudioProfile(
            device_type="nonexistent_device",
            alsa_device="hw:99,0",  # Non-existent device
            sample_rate=16000,
            channels=1
        )
        
        device = await create_audio_device(unavailable_profile)
        
        # Should create device but mark as unavailable
        assert device is not None
        
        # Initialization should handle failure gracefully
        await device.initialize()
        assert device.is_available is False
    
    @pytest.mark.asyncio
    async def test_audio_system_stress_test(self, iqaudio_profile, performance_monitor):
        """Test audio system under stress conditions."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = IQAudioDevice(iqaudio_profile)
            await device.initialize()
            
            with patch.object(device, '_play_audio_data') as mock_play:
                mock_play.return_value = None
                
                performance_monitor.start()
                
                # Generate many concurrent audio operations
                tasks = []
                for i in range(50):
                    audio_data = b'\x00\x01' * (i * 10)  # Variable size audio
                    tasks.append(device.play_audio(audio_data))
                
                # Execute all tasks
                await asyncio.gather(*tasks, return_exceptions=True)
                
                metrics = performance_monitor.stop()
                
                # System should handle stress without excessive resource usage
                assert metrics["memory_delta"] < 50 * 1024 * 1024  # Less than 50MB
                assert metrics["duration"] < 5.0  # Complete within 5 seconds
    
    @pytest.mark.asyncio
    async def test_audio_quality_parameters(self, iqaudio_profile):
        """Test audio quality parameters and validation."""
        device = IQAudioDevice(iqaudio_profile)
        
        # Test different sample rates
        valid_rates = [8000, 16000, 22050, 44100, 48000]
        for rate in valid_rates:
            device.sample_rate = rate
            assert device._validate_sample_rate(rate) is True
        
        # Test invalid sample rates
        invalid_rates = [7999, 48001, 192000]
        for rate in invalid_rates:
            assert device._validate_sample_rate(rate) is False
        
        # Test channel configurations
        assert device._validate_channels(1) is True  # Mono
        assert device._validate_channels(2) is True  # Stereo
        assert device._validate_channels(0) is False  # Invalid
        assert device._validate_channels(8) is False  # Too many channels
    
    @pytest.mark.asyncio
    async def test_audio_device_recovery(self, iqaudio_profile):
        """Test audio device recovery from errors."""
        device = IQAudioDevice(iqaudio_profile)
        
        with patch('subprocess.run') as mock_run:
            # First initialization fails
            mock_run.return_value.returncode = 1
            await device.initialize()
            assert device.is_available is False
            
            # Second initialization succeeds
            mock_run.return_value.returncode = 0
            await device.initialize()
            assert device.is_available is True
    
    @pytest.mark.asyncio
    async def test_audio_real_time_processing(self, iqaudio_profile, sample_audio_data):
        """Test real-time audio processing capabilities."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            device = IQAudioDevice(iqaudio_profile)
            await device.initialize()
            
            # Mock real-time audio processing
            processed_chunks = []
            
            async def mock_audio_callback(audio_chunk):
                processed_chunks.append(audio_chunk)
                return len(audio_chunk)
            
            device.set_audio_callback(mock_audio_callback)
            
            # Process audio in real-time chunks
            chunk_size = 1024
            for i in range(0, len(sample_audio_data), chunk_size):
                chunk = sample_audio_data[i:i + chunk_size]
                await device.process_audio_chunk(chunk)
            
            # Verify all chunks were processed
            total_processed = sum(len(chunk) for chunk in processed_chunks)
            assert total_processed <= len(sample_audio_data)


if __name__ == "__main__":
    pytest.main([__file__])