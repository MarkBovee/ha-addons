"""Status management for Water Heater Scheduler.

Handles status entity updates and visual indicators.
"""

from datetime import datetime
from typing import Optional, Tuple

from shared.ha_api import HomeAssistantApi
from .models import ProgramType
from .constants import STATUS_TEXT_ENTITY, WINTER_MONTHS


def get_status_visual(program: ProgramType, current_time: datetime) -> Tuple[str, Optional[str]]:
    """Return icon + color to match the current program and season."""
    is_winter = current_time.month in WINTER_MONTHS
    light_blue = "#ADD8E6"
    
    if program in (ProgramType.DAY, ProgramType.NIGHT):
        icon = "mdi:snowflake-thermometer" if is_winter else "mdi:water-thermometer"
        color = light_blue
    elif program == ProgramType.NEGATIVE_PRICE:
        icon = "mdi:lightning-bolt-circle"
        color = "#ffb300"
    elif program == ProgramType.LEGIONELLA:
        icon = "mdi:shield-heat"
        color = "#ff7043"
    elif program == ProgramType.BATH:
        icon = "mdi:bathtub"
        color = "#4dd0e1"
    elif program == ProgramType.AWAY:
        icon = "mdi:bag-suitcase"
        color = "#78909c"
    else:
        icon = "mdi:information-outline"
        color = "#b0bec5"
    return icon, color


def update_status_entity(ha_api: HomeAssistantApi, status_msg: str, 
                         program: ProgramType, target_temp: int,
                         status_icon: str, status_color: Optional[str]):
    """Update the status input_text entity."""
    attributes = {
        "friendly_name": "Heating Schedule Status",
        "icon": status_icon,
        "program": program.value,
        "target_temp": target_temp,
    }
    if status_color:
        attributes["icon_color"] = status_color
    
    ha_api.create_or_update_entity(
        entity_id=STATUS_TEXT_ENTITY,
        state=status_msg,
        attributes=attributes,
        log_success=False
    )
