"""Constants for Water Heater Scheduler add-on."""

# Status entity to update (compatible with NetDaemon WaterHeater app)
STATUS_TEXT_ENTITY = 'input_text.heating_schedule_status'

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
