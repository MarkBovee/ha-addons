"""Status management for Water Heater Scheduler.

Handles status entity updates and visual indicators.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple

from shared.ha_api import HomeAssistantApi
from .models import ProgramType
from .constants import STATUS_TEXT_ENTITY, WINTER_MONTHS, LEGIONELLA_ENTITY, LEGIONELLA_INTERVAL_DAYS


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


def update_legionella_entity(ha_api: HomeAssistantApi, last_protection: Optional[datetime]) -> None:
    """Update the legionella protection tracking entity.
    
    Shows when legionella protection last ran and when it's next due.
    """
    now = datetime.now()
    
    if last_protection is None:
        state = "Never"
        days_ago = "N/A"
        next_due = "Now"
        needs_protection = True
    else:
        days_since = (now - last_protection).days
        days_ago = f"{days_since} days ago" if days_since > 0 else "Today"
        state = last_protection.strftime("%Y-%m-%d %H:%M")
        
        # Calculate next due date
        next_due_date = last_protection + timedelta(days=LEGIONELLA_INTERVAL_DAYS)
        if next_due_date <= now:
            next_due = "Now"
            needs_protection = True
        else:
            days_until = (next_due_date - now).days
            next_due = f"In {days_until} days" if days_until > 0 else "Tomorrow"
            needs_protection = False
    
    attributes = {
        "friendly_name": "Last Legionella Protection",
        "icon": "mdi:shield-check" if not needs_protection else "mdi:shield-alert",
        "device_class": "timestamp" if last_protection else None,
        "days_ago": days_ago,
        "next_due": next_due,
        "needs_protection": needs_protection,
        "interval_days": LEGIONELLA_INTERVAL_DAYS,
    }
    
    # Remove None values
    attributes = {k: v for k, v in attributes.items() if v is not None}
    
    ha_api.create_or_update_entity(
        entity_id=LEGIONELLA_ENTITY,
        state=state,
        attributes=attributes,
        log_success=False
    )
