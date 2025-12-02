#!/usr/bin/with-contenv bashio

# Print startup message
bashio::log.info "Starting Water Heater Scheduler add-on..."

# Export MQTT settings for Python app
export MQTT_HOST=$(bashio::config 'mqtt_host' 'core-mosquitto')
export MQTT_PORT=$(bashio::config 'mqtt_port' '1883')

# Only export credentials if explicitly configured
if bashio::config.exists 'mqtt_user' && bashio::config.has_value 'mqtt_user'; then
    export MQTT_USER=$(bashio::config 'mqtt_user')
fi
if bashio::config.exists 'mqtt_password' && bashio::config.has_value 'mqtt_password'; then
    export MQTT_PASSWORD=$(bashio::config 'mqtt_password')
fi

bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"

# Run Python application as a module to support relative imports
cd /app
python3 -m app.main
