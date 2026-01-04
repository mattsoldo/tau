"""
Tau Hardware Interface - LabJack, GPIO, and OLA drivers

This module provides hardware abstraction for:
- LabJack U3 for analog input (switches) and PWM output (LED drivers)
- Raspberry Pi GPIO for switch inputs and PWM outputs
- OLA (Open Lighting Architecture) for DMX512 control

Both mock and real implementations are provided for testing and production.

On Raspberry Pi, the GPIO driver can be used instead of LabJack for
switch inputs and LED PWM control.
"""

from tau.hardware.base import HardwareDriver, LabJackInterface, OLAInterface
from tau.hardware.manager import HardwareManager

__all__ = [
    "HardwareDriver",
    "LabJackInterface",
    "OLAInterface",
    "HardwareManager",
]
