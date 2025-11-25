#!/usr/bin/with-contenv bashio

# Read configuration from options.json
EMAIL=$(bashio::config 'email')
PASSWORD=$(bashio::config 'password')
HOST_NAME=$(bashio::config 'host_name')
BASE_URL=$(bashio::config 'base_url')
UPDATE_INTERVAL=$(bashio::config 'update_interval')

# Export environment variables for Python app
export CHARGER_EMAIL="${EMAIL}"
export CHARGER_PASSWORD="${PASSWORD}"
export CHARGER_HOST_NAME="${HOST_NAME}"
export CHARGER_BASE_URL="${BASE_URL}"
export CHARGER_UPDATE_INTERVAL="${UPDATE_INTERVAL}"

# Export MQTT settings - default: core-mosquitto (HA's built-in MQTT broker)
export MQTT_HOST=$(bashio::config 'mqtt_host' 'core-mosquitto')
export MQTT_PORT=$(bashio::config 'mqtt_port' '1883')

# Only export credentials if explicitly configured
if bashio::config.exists 'mqtt_user' && bashio::config.has_value 'mqtt_user'; then
    export MQTT_USER=$(bashio::config 'mqtt_user')
fi
if bashio::config.exists 'mqtt_password' && bashio::config.has_value 'mqtt_password'; then
    export MQTT_PASSWORD=$(bashio::config 'mqtt_password')
fi

# Get Home Assistant API token from Supervisor
export HA_API_TOKEN="${SUPERVISOR_TOKEN}"
export HA_API_URL="http://supervisor/core"

# Log configuration (without password)
bashio::log.info "Starting EV Charger Monitor addon"
bashio::log.info "Email: ${EMAIL}"
bashio::log.info "Host Name: ${HOST_NAME}"
bashio::log.info "Base URL: ${BASE_URL}"
bashio::log.info "Update Interval: ${UPDATE_INTERVAL} minutes"
bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"
if [ -n "${SUPERVISOR_TOKEN}" ]; then
    bashio::log.info "Home Assistant API token: SET"
else
    bashio::log.warning "Home Assistant API token: NOT SET"
fi

# Start Python application
exec python3 -m app.main

