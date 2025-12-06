"""Constants for Water Heater Scheduler add-on."""

# Status entity to update (compatible with NetDaemon WaterHeater app)
STATUS_TEXT_ENTITY = 'input_text.heating_schedule_status'

# Legionella protection tracking entity
LEGIONELLA_ENTITY = 'sensor.wh_last_legionella'

# Legionella protection threshold (temperature that counts as protection)
LEGIONELLA_TEMP_THRESHOLD = 60  # °C

# Days between required legionella protection cycles
LEGIONELLA_INTERVAL_DAYS = 7

# Day of week mapping (matches C# DayOfWeek enum)
DAYS_OF_WEEK = {
    "Sunday": 6,
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
}

# Winter months for seasonal visuals
WINTER_MONTHS = {10, 11, 12, 1, 2, 3}
