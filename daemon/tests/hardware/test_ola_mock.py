"""
Unit tests for MockOLAInterface

Tests the mock OLA (DMX) hardware interface.
"""
import pytest


class TestOLAMockConnection:
    """Tests for OLA connection management."""

    @pytest.mark.asyncio
    async def test_connect(self, mock_ola):
        """Test connecting to mock OLA."""
        result = await mock_ola.connect()

        assert result is True
        assert mock_ola.is_connected() is True

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_ola):
        """Test disconnecting from mock OLA."""
        await mock_ola.connect()

        await mock_ola.disconnect()

        assert mock_ola.is_connected() is False

    @pytest.mark.asyncio
    async def test_health_check_connected(self, mock_ola):
        """Test health check when connected."""
        await mock_ola.connect()

        result = await mock_ola.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self, mock_ola):
        """Test health check when disconnected."""
        result = await mock_ola.health_check()

        assert result is False


class TestOLAMockDMXChannel:
    """Tests for single DMX channel operations."""

    @pytest.mark.asyncio
    async def test_set_dmx_channel(self, mock_ola):
        """Test setting a single DMX channel."""
        await mock_ola.connect()

        await mock_ola.set_dmx_channel(0, 1, 128)

        assert mock_ola.get_channel(0, 1) == 128

    @pytest.mark.asyncio
    async def test_set_dmx_channel_not_connected(self, mock_ola):
        """Test setting channel when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await mock_ola.set_dmx_channel(0, 1, 128)

    @pytest.mark.asyncio
    async def test_set_dmx_channel_invalid_universe(self, mock_ola):
        """Test setting channel with invalid universe."""
        await mock_ola.connect()

        with pytest.raises(ValueError, match="Invalid universe"):
            await mock_ola.set_dmx_channel(10, 1, 128)

    @pytest.mark.asyncio
    async def test_set_dmx_channel_invalid_channel(self, mock_ola):
        """Test setting channel with invalid channel number."""
        await mock_ola.connect()

        with pytest.raises(ValueError, match="Invalid channel"):
            await mock_ola.set_dmx_channel(0, 0, 128)  # Channel 0 is invalid

        with pytest.raises(ValueError, match="Invalid channel"):
            await mock_ola.set_dmx_channel(0, 513, 128)  # > 512

    @pytest.mark.asyncio
    async def test_set_dmx_channel_invalid_value(self, mock_ola):
        """Test setting channel with invalid value."""
        await mock_ola.connect()

        with pytest.raises(ValueError, match="Invalid value"):
            await mock_ola.set_dmx_channel(0, 1, 256)

        with pytest.raises(ValueError, match="Invalid value"):
            await mock_ola.set_dmx_channel(0, 1, -1)


class TestOLAMockDMXChannelsBatch:
    """Tests for batch DMX channel operations."""

    @pytest.mark.asyncio
    async def test_set_dmx_channels(self, mock_ola):
        """Test setting multiple DMX channels."""
        await mock_ola.connect()

        await mock_ola.set_dmx_channels(0, {1: 100, 2: 150, 3: 200})

        assert mock_ola.get_channel(0, 1) == 100
        assert mock_ola.get_channel(0, 2) == 150
        assert mock_ola.get_channel(0, 3) == 200

    @pytest.mark.asyncio
    async def test_set_dmx_channels_not_connected(self, mock_ola):
        """Test setting channels when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await mock_ola.set_dmx_channels(0, {1: 128})

    @pytest.mark.asyncio
    async def test_set_dmx_channels_invalid_values(self, mock_ola):
        """Test setting channels with invalid values."""
        await mock_ola.connect()

        with pytest.raises(ValueError, match="Invalid channel"):
            await mock_ola.set_dmx_channels(0, {0: 128})  # Channel 0 invalid

        with pytest.raises(ValueError, match="Invalid value"):
            await mock_ola.set_dmx_channels(0, {1: 300})  # Value > 255


class TestOLAMockDMXUniverse:
    """Tests for full universe operations."""

    @pytest.mark.asyncio
    async def test_set_dmx_universe(self, mock_ola):
        """Test setting entire DMX universe."""
        await mock_ola.connect()
        data = bytes([i % 256 for i in range(512)])

        await mock_ola.set_dmx_universe(0, data)

        # Check first few channels
        assert mock_ola.get_channel(0, 1) == 0
        assert mock_ola.get_channel(0, 2) == 1
        assert mock_ola.get_channel(0, 100) == 99

    @pytest.mark.asyncio
    async def test_set_dmx_universe_invalid_length(self, mock_ola):
        """Test setting universe with wrong data length."""
        await mock_ola.connect()
        data = bytes([0] * 100)  # Wrong length

        with pytest.raises(ValueError, match="Invalid data length"):
            await mock_ola.set_dmx_universe(0, data)

    @pytest.mark.asyncio
    async def test_get_dmx_universe(self, mock_ola):
        """Test getting entire DMX universe."""
        await mock_ola.connect()
        await mock_ola.set_dmx_channel(0, 1, 100)
        await mock_ola.set_dmx_channel(0, 10, 200)

        data = await mock_ola.get_dmx_universe(0)

        assert len(data) == 512
        assert data[0] == 100  # Channel 1
        assert data[9] == 200  # Channel 10

    @pytest.mark.asyncio
    async def test_get_dmx_universe_not_connected(self, mock_ola):
        """Test getting universe when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await mock_ola.get_dmx_universe(0)


class TestOLAMockMultipleUniverses:
    """Tests for multi-universe support."""

    @pytest.mark.asyncio
    async def test_multiple_universes(self, mock_ola):
        """Test setting channels across multiple universes."""
        await mock_ola.connect()

        await mock_ola.set_dmx_channel(0, 1, 100)
        await mock_ola.set_dmx_channel(1, 1, 150)
        await mock_ola.set_dmx_channel(2, 1, 200)

        assert mock_ola.get_channel(0, 1) == 100
        assert mock_ola.get_channel(1, 1) == 150
        assert mock_ola.get_channel(2, 1) == 200

    @pytest.mark.asyncio
    async def test_universe_isolation(self, mock_ola):
        """Test that universes are isolated from each other."""
        await mock_ola.connect()

        # Set channel 1 in universe 0
        await mock_ola.set_dmx_channel(0, 1, 255)

        # Channel 1 in other universes should still be 0
        assert mock_ola.get_channel(1, 1) == 0
        assert mock_ola.get_channel(2, 1) == 0


class TestOLAMockStatistics:
    """Tests for statistics tracking."""

    @pytest.mark.asyncio
    async def test_statistics_initial(self, mock_ola):
        """Test initial statistics."""
        stats = mock_ola.get_statistics()

        assert stats["connected"] is False
        assert stats["channel_set_count"] == 0
        assert stats["universe_set_count"] == 0
        assert stats["total_channels_updated"] == 0
        assert stats["non_zero_channels"] == 0

    @pytest.mark.asyncio
    async def test_statistics_after_channel_set(self, mock_ola):
        """Test statistics after setting channels."""
        await mock_ola.connect()
        await mock_ola.set_dmx_channel(0, 1, 100)
        await mock_ola.set_dmx_channel(0, 2, 200)
        await mock_ola.set_dmx_channels(0, {3: 128, 4: 64})

        stats = mock_ola.get_statistics()

        assert stats["connected"] is True
        assert stats["channel_set_count"] == 4
        assert stats["total_channels_updated"] == 4
        assert stats["non_zero_channels"] == 4

    @pytest.mark.asyncio
    async def test_statistics_after_universe_set(self, mock_ola):
        """Test statistics after setting full universe."""
        await mock_ola.connect()
        data = bytes([128] * 512)

        await mock_ola.set_dmx_universe(0, data)

        stats = mock_ola.get_statistics()

        assert stats["universe_set_count"] == 1
        assert stats["total_channels_updated"] == 512
        assert stats["non_zero_channels"] == 512


class TestOLAMockHelpers:
    """Tests for testing helper methods."""

    @pytest.mark.asyncio
    async def test_get_channel(self, mock_ola):
        """Test getting a channel value directly."""
        await mock_ola.connect()
        await mock_ola.set_dmx_channel(0, 50, 175)

        value = mock_ola.get_channel(0, 50)

        assert value == 175

    def test_get_channel_invalid_universe(self, mock_ola):
        """Test getting channel from invalid universe."""
        with pytest.raises(ValueError, match="Invalid universe"):
            mock_ola.get_channel(10, 1)

    def test_get_channel_invalid_channel(self, mock_ola):
        """Test getting invalid channel number."""
        with pytest.raises(ValueError, match="Invalid channel"):
            mock_ola.get_channel(0, 0)

        with pytest.raises(ValueError, match="Invalid channel"):
            mock_ola.get_channel(0, 600)

    @pytest.mark.asyncio
    async def test_get_universe_summary(self, mock_ola):
        """Test getting universe summary."""
        await mock_ola.connect()
        await mock_ola.set_dmx_channel(0, 1, 100)
        await mock_ola.set_dmx_channel(0, 5, 200)
        await mock_ola.set_dmx_channel(0, 10, 50)

        summary = mock_ola.get_universe_summary(0)

        assert summary["universe"] == 0
        assert summary["total_channels"] == 512
        assert summary["non_zero_channels"] == 3
        assert summary["max_value"] == 200
