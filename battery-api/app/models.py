"""Data models for Battery API add-on.

Port of the C# models from NetDaemonApps/Models/Battery/
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import List, Optional, Tuple


class BatteryChargeType(Enum):
    """Type of battery charging operation."""
    CHARGE = "Charge"
    DISCHARGE = "Discharge"


class BatteryUserMode(Enum):
    """SAJ inverter user mode."""
    UNKNOWN = "Unknown"
    EMS = "EMS"
    TIME_OF_USE = "TimeOfUse"
    BACKUP = "Backup"
    OFF_GRID = "OffGrid"
    
    @classmethod
    def from_api_string(cls, value: Optional[str]) -> "BatteryUserMode":
        """Convert API string to enum value."""
        if not value:
            return cls.UNKNOWN
        
        value_lower = value.lower()
        if "ems" in value_lower:
            return cls.EMS
        if "time" in value_lower or "tou" in value_lower:
            return cls.TIME_OF_USE
        if "backup" in value_lower:
            return cls.BACKUP
        if "off" in value_lower and "grid" in value_lower:
            return cls.OFF_GRID
        return cls.UNKNOWN


@dataclass
class ChargingPeriod:
    """Represents a single charging or discharging period.
    
    Attributes:
        charge_type: Whether this is a charge or discharge period
        start_time: Start time as HH:MM string
        duration_minutes: Duration in minutes
        power_w: Power in watts
        weekdays: Optional weekday bitmask (default: all days)
    """
    charge_type: BatteryChargeType
    start_time: str  # "HH:MM" format
    duration_minutes: int
    power_w: int
    weekdays: str = "1,1,1,1,1,1,1"  # Mon-Sun, all enabled by default
    
    @property
    def end_time(self) -> str:
        """Calculate end time from start time and duration."""
        parts = self.start_time.split(":")
        start_hour = int(parts[0])
        start_min = int(parts[1]) if len(parts) > 1 else 0
        
        total_minutes = start_hour * 60 + start_min + self.duration_minutes
        end_hour = (total_minutes // 60) % 24
        end_min = total_minutes % 60
        
        return f"{end_hour:02d}:{end_min:02d}"
    
    def to_api_format(self) -> str:
        """Convert to SAJ API format string.
        
        Format: "start|end|power_weekdays"
        Example: "02:00|04:00|6000_1,1,1,1,1,1,1"
        
        Returns:
            API-formatted string for this period
        """
        return f"{self.start_time}|{self.end_time}|{self.power_w}_{self.weekdays}"


@dataclass
class BatteryScheduleParameters:
    """Parameters for SAJ API schedule request.
    
    Attributes:
        comm_address: Modbus register addresses (header + slots)
        component_id: Component IDs for each register block
        transfer_id: Data type markers for each register block
        value: Schedule value string with all periods
    """
    comm_address: str
    component_id: str
    transfer_id: str
    value: str


# SAJ API register address mapping for battery schedule periods
# These are Modbus register addresses used by the SAJ H2 inverter
HEADER_REGISTER = "3647"
MAX_CHARGE_SLOTS = 3
MAX_DISCHARGE_SLOTS = 6

# Charge slot register base addresses (each slot uses 3 consecutive registers)
CHARGE_SLOT_REGISTERS = [
    ["3606", "3607", "3608"],  # Charge slot 1
    ["3609", "360A", "360B"],  # Charge slot 2
    ["360C", "360D", "360E"],  # Charge slot 3
]

# Discharge slot register base addresses (each slot uses 3 consecutive registers)
DISCHARGE_SLOT_REGISTERS = [
    ["361B", "361C", "361D"],  # Discharge slot 1
    ["361E", "361F", "3620"],  # Discharge slot 2
    ["3621", "3622", "3623"],  # Discharge slot 3
    ["3624", "3625", "3626"],  # Discharge slot 4
    ["3627", "3628", "3629"],  # Discharge slot 5
    ["362A", "362B", "362C"],  # Discharge slot 6
]


def is_supported_pattern(charges: int, discharges: int) -> bool:
    """Check if charge/discharge combination is supported by SAJ address mapping.
    
    Args:
        charges: Number of charge periods (0-3)
        discharges: Number of discharge periods (0-6)
        
    Returns:
        True if pattern is supported
    """
    return (0 <= charges <= MAX_CHARGE_SLOTS and
            0 <= discharges <= MAX_DISCHARGE_SLOTS and
            (charges + discharges) > 0)  # At least one period required


def generate_address_patterns(charge_count: int, discharge_count: int) -> Tuple[str, str, str]:
    """Generate SAJ API address patterns dynamically.
    
    SAJ API Register Pattern:
    - Header: 0x3647 (enables time-of-use mode)
    - Each slot uses 3 consecutive registers in format: "XXXX|XXXX|XXXX_XXXX"
    - Charge slots: 0x3606+ (3 registers per slot)
    - Discharge slots: 0x361B+ (3 registers per slot)
    - componentId: Always "|30|30|30_30" per slot (4 values per register block)
    - transferId: Always "|5|5|2_1" per slot (data type markers)
    
    Args:
        charge_count: Number of charge periods
        discharge_count: Number of discharge periods
        
    Returns:
        Tuple of (comm_address, component_id, transfer_id)
        
    Raises:
        ValueError: If pattern is not supported
    """
    if not is_supported_pattern(charge_count, discharge_count):
        raise ValueError(
            f"UNSUPPORTED CHARGE/DISCHARGE COMBINATION! Got {charge_count} charge + "
            f"{discharge_count} discharge periods. Supported range: 0-{MAX_CHARGE_SLOTS} "
            f"charge slots, 0-{MAX_DISCHARGE_SLOTS} discharge slots, with at least 1 total period."
        )
    
    comm_parts = [HEADER_REGISTER]
    component_parts = []
    transfer_parts = []
    
    # Add charge slot addresses
    for i in range(charge_count):
        regs = CHARGE_SLOT_REGISTERS[i]
        comm_parts.append(f"{regs[0]}|{regs[1]}|{regs[2]}_{regs[2]}")
        component_parts.append("|30|30|30_30")
        transfer_parts.append("|5|5|2_1")
    
    # Add discharge slot addresses
    for i in range(discharge_count):
        regs = DISCHARGE_SLOT_REGISTERS[i]
        comm_parts.append(f"{regs[0]}|{regs[1]}|{regs[2]}_{regs[2]}")
        component_parts.append("|30|30|30_30")
        transfer_parts.append("|5|5|2_1")
    
    return (
        "|".join(comm_parts),
        "".join(component_parts),
        "".join(transfer_parts),
    )


def build_schedule_parameters(periods: List[ChargingPeriod]) -> BatteryScheduleParameters:
    """Build SAJ API schedule parameters from a list of periods.
    
    Periods are sorted: charges first, then discharges, then by start time within each group.
    
    Args:
        periods: List of charging periods to schedule
        
    Returns:
        BatteryScheduleParameters ready for API call
        
    Raises:
        ValueError: If pattern is not supported
    """
    # Sort periods: charges first, then discharges, then by start time
    sorted_periods = sorted(
        periods,
        key=lambda p: (0 if p.charge_type == BatteryChargeType.CHARGE else 1, p.start_time)
    )
    
    # Count by type
    charge_count = sum(1 for p in sorted_periods if p.charge_type == BatteryChargeType.CHARGE)
    discharge_count = sum(1 for p in sorted_periods if p.charge_type == BatteryChargeType.DISCHARGE)
    
    # Generate address patterns
    comm_address, component_id, transfer_id = generate_address_patterns(charge_count, discharge_count)
    
    # Build value field: "1|" + each period in API format
    value_parts = ["1"]  # Header value (enables schedule)
    for period in sorted_periods:
        value_parts.append(period.to_api_format())
    
    return BatteryScheduleParameters(
        comm_address=comm_address,
        component_id=component_id,
        transfer_id=transfer_id,
        value="|".join(value_parts),
    )
