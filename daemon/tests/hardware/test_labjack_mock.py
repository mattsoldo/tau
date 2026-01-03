"""
Unit tests for MockLabJackInterface

Tests the mock LabJack hardware interface.
"""
import pytest


class TestLabJackMockConnection:
    """Tests for LabJack connection management."""

    @pytest.mark.asyncio
    async def test_connect(self, mock_labjack):
        """Test connecting to mock LabJack."""
        result = await mock_labjack.connect()

        assert result is True
        assert mock_labjack.is_connected() is True

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_labjack):
        """Test disconnecting from mock LabJack."""
        await mock_labjack.connect()

        await mock_labjack.disconnect()

        assert mock_labjack.is_connected() is False

    @pytest.mark.asyncio
    async def test_health_check_connected(self, mock_labjack):
        """Test health check when connected."""
        await mock_labjack.connect()

        result = await mock_labjack.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self, mock_labjack):
        """Test health check when disconnected."""
        result = await mock_labjack.health_check()

        assert result is False

    def test_is_mock(self, mock_labjack):
        """Test that is_mock() returns True."""
        assert mock_labjack.is_mock() is True


class TestLabJackMockAnalogInput:
    """Tests for analog input reading."""

    @pytest.mark.asyncio
    async def test_read_analog_input(self, mock_labjack):
        """Test reading analog input."""
        await mock_labjack.connect()
        mock_labjack.simulate_analog_input(0, 1.5)

        voltage = await mock_labjack.read_analog_input(0)

        assert voltage == 1.5

    @pytest.mark.asyncio
    async def test_read_analog_input_not_connected(self, mock_labjack):
        """Test reading analog input when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await mock_labjack.read_analog_input(0)

    @pytest.mark.asyncio
    async def test_read_analog_input_invalid_channel(self, mock_labjack):
        """Test reading analog input with invalid channel."""
        await mock_labjack.connect()

        with pytest.raises(ValueError, match="Invalid channel"):
            await mock_labjack.read_analog_input(16)

        with pytest.raises(ValueError, match="Invalid channel"):
            await mock_labjack.read_analog_input(-1)

    @pytest.mark.asyncio
    async def test_read_analog_inputs_batch(self, mock_labjack):
        """Test reading multiple analog inputs."""
        await mock_labjack.connect()
        mock_labjack.simulate_analog_input(0, 1.0)
        mock_labjack.simulate_analog_input(1, 1.5)
        mock_labjack.simulate_analog_input(2, 2.0)

        result = await mock_labjack.read_analog_inputs([0, 1, 2])

        assert result[0] == 1.0
        assert result[1] == 1.5
        assert result[2] == 2.0


class TestLabJackMockPWMOutput:
    """Tests for PWM output control."""

    @pytest.mark.asyncio
    async def test_set_pwm_output(self, mock_labjack):
        """Test setting PWM output."""
        await mock_labjack.connect()

        await mock_labjack.set_pwm_output(0, 0.75)

        assert mock_labjack.pwm_outputs[0] == 0.75

    @pytest.mark.asyncio
    async def test_set_pwm_output_not_connected(self, mock_labjack):
        """Test setting PWM output when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await mock_labjack.set_pwm_output(0, 0.5)

    @pytest.mark.asyncio
    async def test_set_pwm_output_invalid_channel(self, mock_labjack):
        """Test setting PWM output with invalid channel."""
        await mock_labjack.connect()

        with pytest.raises(ValueError, match="Invalid PWM channel"):
            await mock_labjack.set_pwm_output(2, 0.5)

    @pytest.mark.asyncio
    async def test_set_pwm_output_invalid_duty_cycle(self, mock_labjack):
        """Test setting PWM output with invalid duty cycle."""
        await mock_labjack.connect()

        with pytest.raises(ValueError, match="Invalid duty cycle"):
            await mock_labjack.set_pwm_output(0, 1.5)

        with pytest.raises(ValueError, match="Invalid duty cycle"):
            await mock_labjack.set_pwm_output(0, -0.1)

    @pytest.mark.asyncio
    async def test_set_pwm_outputs_batch(self, mock_labjack):
        """Test setting multiple PWM outputs."""
        await mock_labjack.connect()

        await mock_labjack.set_pwm_outputs({0: 0.5, 1: 0.75})

        assert mock_labjack.pwm_outputs[0] == 0.5
        assert mock_labjack.pwm_outputs[1] == 0.75


class TestLabJackMockDigitalIO:
    """Tests for digital I/O."""

    @pytest.mark.asyncio
    async def test_read_digital_input(self, mock_labjack):
        """Test reading digital input."""
        await mock_labjack.connect()
        mock_labjack.simulate_digital_input(5, True)

        result = await mock_labjack.read_digital_input(5)

        assert result is True

    @pytest.mark.asyncio
    async def test_write_digital_output(self, mock_labjack):
        """Test writing digital output."""
        await mock_labjack.connect()

        await mock_labjack.write_digital_output(3, True)

        assert mock_labjack.digital_outputs[3] is True

    @pytest.mark.asyncio
    async def test_digital_io_not_connected(self, mock_labjack):
        """Test digital I/O when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await mock_labjack.read_digital_input(0)

        with pytest.raises(RuntimeError, match="not connected"):
            await mock_labjack.write_digital_output(0, True)


class TestLabJackMockChannelConfiguration:
    """Tests for channel configuration."""

    @pytest.mark.asyncio
    async def test_configure_channel(self, mock_labjack):
        """Test configuring a channel."""
        await mock_labjack.connect()

        await mock_labjack.configure_channel(5, 'digital-in')

        assert mock_labjack.channel_modes[5] == 'digital-in'

    @pytest.mark.asyncio
    async def test_configure_eio_pin_analog_warning(self, mock_labjack):
        """Test that EIO pins (8-15) can't be configured as analog."""
        await mock_labjack.connect()

        # This should warn and set to digital-in
        await mock_labjack.configure_channel(10, 'analog')

        # Should be set to digital-in instead
        assert mock_labjack.channel_modes[10] == 'digital-in'

    @pytest.mark.asyncio
    async def test_configure_channel_invalid_mode(self, mock_labjack):
        """Test configuring with invalid mode."""
        await mock_labjack.connect()

        with pytest.raises(ValueError, match="Invalid mode"):
            await mock_labjack.configure_channel(0, 'invalid')


class TestLabJackMockStatistics:
    """Tests for statistics tracking."""

    @pytest.mark.asyncio
    async def test_statistics_initial(self, mock_labjack):
        """Test initial statistics."""
        stats = mock_labjack.get_statistics()

        assert stats["connected"] is False
        assert stats["read_count"] == 0
        assert stats["write_count"] == 0

    @pytest.mark.asyncio
    async def test_statistics_after_operations(self, mock_labjack):
        """Test statistics after operations."""
        await mock_labjack.connect()
        await mock_labjack.read_analog_input(0)
        await mock_labjack.read_analog_input(1)
        await mock_labjack.set_pwm_output(0, 0.5)

        stats = mock_labjack.get_statistics()

        assert stats["connected"] is True
        assert stats["read_count"] == 2
        assert stats["write_count"] == 1


class TestLabJackMockSimulation:
    """Tests for simulation helper methods."""

    def test_simulate_analog_input(self, mock_labjack):
        """Test simulating analog input values."""
        mock_labjack.simulate_analog_input(5, 2.0)

        assert mock_labjack.analog_inputs[5] == 2.0

    def test_simulate_analog_input_invalid_channel(self, mock_labjack):
        """Test simulating invalid analog input channel."""
        with pytest.raises(ValueError, match="Invalid channel"):
            mock_labjack.simulate_analog_input(20, 1.0)

    def test_simulate_digital_input(self, mock_labjack):
        """Test simulating digital input values."""
        mock_labjack.simulate_digital_input(7, True)

        assert mock_labjack.digital_inputs[7] is True

    def test_simulate_digital_input_invalid_channel(self, mock_labjack):
        """Test simulating invalid digital input channel."""
        with pytest.raises(ValueError, match="Invalid channel"):
            mock_labjack.simulate_digital_input(20, True)
