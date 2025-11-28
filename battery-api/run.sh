#!/usr/bin/with-contenv bashio

# Print startup message
bashio::log.info "Starting Battery API add-on..."

# Export SAJ credentials for Python app
export SAJ_USERNAME=$(bashio::config 'saj_username')
export SAJ_PASSWORD=$(bashio::config 'saj_password')
export SAJ_DEVICE_SERIAL=$(bashio::config 'device_serial_number')
export SAJ_PLANT_UID=$(bashio::config 'plant_uid')

# Export behavior settings
export POLL_INTERVAL=$(bashio::config 'poll_interval_seconds' '60')
export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export SIMULATION_MODE=$(bashio::config 'simulation_mode' 'false')

# Export MQTT settings for Python app
# Default: core-mosquitto (HA's built-in MQTT broker)
export MQTT_HOST=$(bashio::config 'mqtt_host' 'core-mosquitto')
export MQTT_PORT=$(bashio::config 'mqtt_port' '1883')

# Only export credentials if explicitly configured
if bashio::config.exists 'mqtt_user' && bashio::config.has_value 'mqtt_user'; then
    export MQTT_USER=$(bashio::config 'mqtt_user')
fi
if bashio::config.exists 'mqtt_password' && bashio::config.has_value 'mqtt_password'; then
    export MQTT_PASSWORD=$(bashio::config 'mqtt_password')
fi

bashio::log.info "SAJ Device: ${SAJ_DEVICE_SERIAL}"
bashio::log.info "Poll interval: ${POLL_INTERVAL}s"
bashio::log.info "Simulation mode: ${SIMULATION_MODE}"
bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"

# Run the Python application
cd /app
exec python3 -m app.main
