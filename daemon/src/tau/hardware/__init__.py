"""
Tau Hardware Interface - LabJack and OLA drivers

This module provides hardware abstraction for:
- LabJack U3 for analog input (switches) and PWM output (LED drivers)
- OLA (Open Lighting Architecture) for DMX512 control

Both mock and real implementations are provided for testing and production.
"""

from tau.hardware.base import HardwareDriver, LabJackInterface, OLAInterface
from tau.hardware.manager import HardwareManager

__all__ = [
    "HardwareDriver",
    "LabJackInterface",
    "OLAInterface",
    "HardwareManager",
]
