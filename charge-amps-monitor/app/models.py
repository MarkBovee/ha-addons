"""Data models for Charge Amps API responses."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Connector:
    """Represents a connector on a charge point."""
    
    connector_id: int
    name: Optional[str] = None
    mode: Optional[str] = None
    is_charging: bool = False
    total_consumption_kwh: float = 0.0
    current1: float = 0.0
    current2: float = 0.0
    current3: float = 0.0
    voltage1: float = 0.0
    voltage2: float = 0.0
    voltage3: float = 0.0
    ocpp_status: Optional[str] = None
    error_code: Optional[str] = None
    enabled: bool = True
    
    @property
    def current_power_w(self) -> float:
        """Calculate current power in watts from voltage and current."""
        return (self.voltage1 * self.current1 + 
                self.voltage2 * self.current2 + 
                self.voltage3 * self.current3)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Connector":
        """Create Connector from API response dictionary."""
        return cls(
            connector_id=data.get("connectorId", 0),
            name=data.get("name"),
            mode=data.get("mode"),
            is_charging=data.get("isCharging", False),
            total_consumption_kwh=data.get("totalConsumptionKwh", 0.0),
            current1=data.get("current1", 0.0),
            current2=data.get("current2", 0.0),
            current3=data.get("current3", 0.0),
            voltage1=data.get("voltage1", 0.0),
            voltage2=data.get("voltage2", 0.0),
            voltage3=data.get("voltage3", 0.0),
            ocpp_status=data.get("ocppStatus"),
            error_code=data.get("errorCode"),
            enabled=data.get("enabled", True)
        )


@dataclass
class ChargePoint:
    """Represents a Charge Amps charge point."""
    
    id: Optional[str] = None
    name: Optional[str] = None
    serial_number: Optional[str] = None
    product_name: Optional[str] = None
    product_type: Optional[str] = None
    charge_point_status: Optional[str] = None
    is_charging: bool = False
    company_id: Optional[str] = None
    owner_id: Optional[str] = None
    connectors: List[Connector] = None
    
    def __post_init__(self):
        """Initialize connectors list if None."""
        if self.connectors is None:
            self.connectors = []
    
    @property
    def is_online(self) -> bool:
        """Check if charge point is online."""
        return self.charge_point_status == "Online"
    
    @classmethod
    def from_dict(cls, data: dict) -> "ChargePoint":
        """Create ChargePoint from API response dictionary."""
        connectors = []
        if "connectors" in data and data["connectors"]:
            connectors = [Connector.from_dict(c) for c in data["connectors"]]
        
        return cls(
            id=data.get("id"),
            name=data.get("name"),
            serial_number=data.get("serialNumber"),
            product_name=data.get("productName"),
            product_type=data.get("productType"),
            charge_point_status=data.get("chargePointStatus"),
            is_charging=data.get("isCharging", False),
            company_id=data.get("companyId"),
            owner_id=data.get("ownerId"),
            connectors=connectors
        )

