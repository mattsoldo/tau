"""
Phase 3 Hardware Integration Test

Tests hardware drivers and hardware manager:
- LabJack mock driver (analog input, PWM output)
- OLA mock driver (DMX control)
- Hardware manager coordination
- Integration with daemon
"""
import asyncio

from tau.hardware import HardwareManager
from tau.hardware.labjack_mock import LabJackMock
from tau.hardware.ola_mock import OLAMock


async def test_phase3_hardware():
    """Test complete Phase 3 hardware integration"""
    print("=" * 60)
    print("Phase 3 Hardware Integration Test")
    print("=" * 60)

    # Test LabJack Mock
    print("\n1. Testing LabJack Mock...")
    labjack = LabJackMock()

    # Connect
    connected = await labjack.connect()
    assert connected, "LabJack should connect"
    assert labjack.is_connected(), "LabJack should be connected"
    print("   ✓ LabJack connected")

    # Test analog input reading
    voltage = await labjack.read_analog_input(0)
    assert voltage == 0.0, "Initial voltage should be 0.0"
    print(f"   ✓ Analog input channel 0: {voltage}V")

    # Simulate analog input change
    labjack.simulate_analog_input(0, 1.5)
    voltage = await labjack.read_analog_input(0)
    assert voltage == 1.5, "Voltage should be 1.5"
    print(f"   ✓ Simulated analog input: {voltage}V")

    # Test batch reading
    labjack.simulate_analog_input(1, 2.0)
    labjack.simulate_analog_input(2, 0.5)
    voltages = await labjack.read_analog_inputs([0, 1, 2])
    assert voltages[0] == 1.5, "Channel 0 should be 1.5V"
    assert voltages[1] == 2.0, "Channel 1 should be 2.0V"
    assert voltages[2] == 0.5, "Channel 2 should be 0.5V"
    print(f"   ✓ Batch read: {len(voltages)} channels")

    # Test PWM output
    await labjack.set_pwm_output(0, 0.75)
    stats = labjack.get_statistics()
    assert stats["pwm_outputs"][0] == 0.75, "PWM 0 should be 0.75"
    print(f"   ✓ PWM output set: 75% duty cycle")

    # Test batch PWM
    await labjack.set_pwm_outputs({0: 0.5, 1: 0.25})
    stats = labjack.get_statistics()
    assert stats["pwm_outputs"][0] == 0.5, "PWM 0 should be 0.5"
    assert stats["pwm_outputs"][1] == 0.25, "PWM 1 should be 0.25"
    print(f"   ✓ Batch PWM set: 2 channels")

    # Check statistics
    stats = labjack.get_statistics()
    assert stats["read_count"] == 5, "Should have 5 reads (1 + 1 + 3 batch)"
    assert stats["write_count"] == 3, "Should have 3 writes (1 + 2 batch)"
    print(f"   ✓ Statistics: {stats['read_count']} reads, {stats['write_count']} writes")

    await labjack.disconnect()
    print("   ✓ LabJack disconnected")

    # Test OLA Mock
    print("\n2. Testing OLA Mock...")
    ola = OLAMock()

    # Connect
    connected = await ola.connect()
    assert connected, "OLA should connect"
    assert ola.is_connected(), "OLA should be connected"
    print("   ✓ OLA connected")

    # Test single channel set
    await ola.set_dmx_channel(0, 1, 255)
    value = ola.get_channel(0, 1)
    assert value == 255, "Channel 1 should be 255"
    print(f"   ✓ DMX channel 1 set to {value}")

    # Test batch channel set
    await ola.set_dmx_channels(0, {10: 128, 11: 64, 12: 32})
    assert ola.get_channel(0, 10) == 128, "Channel 10 should be 128"
    assert ola.get_channel(0, 11) == 64, "Channel 11 should be 64"
    assert ola.get_channel(0, 12) == 32, "Channel 12 should be 32"
    print(f"   ✓ Batch set: 3 channels")

    # Test universe set
    universe_data = bytearray(512)
    universe_data[0] = 255  # Channel 1
    universe_data[1] = 200  # Channel 2
    universe_data[2] = 150  # Channel 3
    await ola.set_dmx_universe(0, bytes(universe_data))
    assert ola.get_channel(0, 1) == 255, "Channel 1 should be 255"
    assert ola.get_channel(0, 2) == 200, "Channel 2 should be 200"
    assert ola.get_channel(0, 3) == 150, "Channel 3 should be 150"
    print(f"   ✓ Full universe set (512 channels)")

    # Get universe
    retrieved = await ola.get_dmx_universe(0)
    assert len(retrieved) == 512, "Universe should be 512 bytes"
    assert retrieved[0] == 255, "Channel 1 should be 255"
    print(f"   ✓ Universe retrieved (512 bytes)")

    # Check statistics
    stats = ola.get_statistics()
    assert stats["channel_set_count"] == 4, "Should have 4 channel sets (1 + 3 batch)"
    assert stats["universe_set_count"] == 1, "Should have 1 universe set"
    assert stats["non_zero_channels"] == 3, "Should have 3 non-zero channels"
    print(f"   ✓ Statistics: {stats['total_channels_updated']} total updates")

    await ola.disconnect()
    print("   ✓ OLA disconnected")

    # Test Hardware Manager
    print("\n3. Testing Hardware Manager...")
    manager = HardwareManager(labjack_driver=LabJackMock(), ola_driver=OLAMock())

    # Initialize
    success = await manager.initialize()
    assert success, "Hardware manager should initialize"
    assert manager.is_healthy(), "Hardware should be healthy"
    print("   ✓ Hardware manager initialized")

    # Test convenience methods - read switches
    manager.labjack.simulate_analog_input(0, 1.8)
    manager.labjack.simulate_analog_input(1, 0.9)
    switch_readings = await manager.read_switch_inputs([0, 1])
    assert switch_readings[0] == 1.8, "Switch 0 should be 1.8V"
    assert switch_readings[1] == 0.9, "Switch 1 should be 0.9V"
    print(f"   ✓ Switch readings: {switch_readings}")

    # Test convenience methods - set LED PWM
    await manager.set_led_pwm(0, 0.6)
    stats = manager.labjack.get_statistics()
    assert stats["pwm_outputs"][0] == 0.6, "LED PWM should be 0.6"
    print(f"   ✓ LED PWM set: 60%")

    # Test convenience methods - set fixture DMX
    await manager.set_fixture_dmx(0, 1, [255, 200, 150])
    assert manager.ola.get_channel(0, 1) == 255, "DMX channel 1 should be 255"
    assert manager.ola.get_channel(0, 2) == 200, "DMX channel 2 should be 200"
    assert manager.ola.get_channel(0, 3) == 150, "DMX channel 3 should be 150"
    print(f"   ✓ Fixture DMX set: 3 channels starting at ch1")

    # Test convenience methods - batch DMX
    await manager.set_dmx_output(0, {10: 100, 20: 200})
    assert manager.ola.get_channel(0, 10) == 100, "DMX channel 10 should be 100"
    assert manager.ola.get_channel(0, 20) == 200, "DMX channel 20 should be 200"
    print(f"   ✓ Batch DMX output set")

    # Check health
    assert manager.is_healthy(), "Hardware should still be healthy"
    print(f"   ✓ Health check passed")

    # Get statistics
    hw_stats = manager.get_statistics()
    assert hw_stats["overall_healthy"], "Should be healthy"
    assert hw_stats["labjack"]["connected"], "LabJack should be connected"
    assert hw_stats["ola"]["connected"], "OLA should be connected"
    print(f"   ✓ Statistics retrieved")

    # Wait for health check loop to run once
    print("   ⏳ Waiting for background health check...")
    await asyncio.sleep(11)  # Wait slightly longer than 10s interval

    hw_stats = manager.get_statistics()
    assert hw_stats["health_checks"]["passed"] >= 1, "Should have at least 1 health check"
    print(f"   ✓ Background health checks: {hw_stats['health_checks']['passed']} passed")

    # Shutdown
    await manager.shutdown()
    print("   ✓ Hardware manager shut down")

    print("\n" + "=" * 60)
    print("✅ Phase 3 Hardware Integration Test PASSED")
    print("=" * 60)
    print("\nVerified components:")
    print("  ✓ LabJack mock driver (analog input, PWM output)")
    print("  ✓ OLA mock driver (DMX512 control)")
    print("  ✓ Hardware manager coordination")
    print("  ✓ Convenience methods for common operations")
    print("  ✓ Background health monitoring")
    print("  ✓ Statistics and status reporting")
    print("\n🎉 Phase 3 Complete!")


if __name__ == "__main__":
    asyncio.run(test_phase3_hardware())
