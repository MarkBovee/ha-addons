#!/usr/bin/with-contenv bashio

# Read configuration from options.json
EMAIL=$(bashio::config 'email')
PASSWORD=$(bashio::config 'password')
HOST_NAME=$(bashio::config 'host_name')
BASE_URL=$(bashio::config 'base_url')
UPDATE_INTERVAL=$(bashio::config 'update_interval')

OPERATION_MODE=$(bashio::config 'operation_mode' 'standalone')
AUTOMATION_ENABLED=$(bashio::config 'automation_enabled' 'false')
PRICE_SENSOR_ENTITY=$(bashio::config 'price_sensor_entity' 'sensor.energy_prices_electricity_import_price')
TOP_X_CHARGE_COUNT=$(bashio::config 'top_x_charge_count' '16')
PRICE_THRESHOLD=$(bashio::config 'price_threshold' '0.25')
MAX_CURRENT=$(bashio::config 'max_current_per_phase' '16')
CONNECTOR_IDS=$(bashio::config 'connector_ids' '1')

# Export environment variables for Python app
export CHARGER_EMAIL="${EMAIL}"
export CHARGER_PASSWORD="${PASSWORD}"
export CHARGER_HOST_NAME="${HOST_NAME}"
export CHARGER_BASE_URL="${BASE_URL}"
export CHARGER_UPDATE_INTERVAL="${UPDATE_INTERVAL}"
export CHARGER_OPERATION_MODE="${OPERATION_MODE}"
export CHARGER_AUTOMATION_ENABLED="${AUTOMATION_ENABLED}"
export CHARGER_PRICE_SENSOR_ENTITY="${PRICE_SENSOR_ENTITY}"
export CHARGER_TOP_X_CHARGE_COUNT="${TOP_X_CHARGE_COUNT}"
export CHARGER_PRICE_THRESHOLD="${PRICE_THRESHOLD}"
export CHARGER_MAX_CURRENT_PER_PHASE="${MAX_CURRENT}"
export CHARGER_CONNECTOR_IDS="${CONNECTOR_IDS}"

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
export HA_API_URL="http://supervisor/core/api"

# Log configuration (without password)
bashio::log.info "Starting EV Charger Monitor addon"
bashio::log.info "Email: ${EMAIL}"
bashio::log.info "Host Name: ${HOST_NAME}"
bashio::log.info "Base URL: ${BASE_URL}"
bashio::log.info "Update Interval: ${UPDATE_INTERVAL} minutes"
bashio::log.info "Operation mode: ${OPERATION_MODE}"
bashio::log.info "Automation enabled: ${AUTOMATION_ENABLED}"
bashio::log.info "Price sensor entity: ${PRICE_SENSOR_ENTITY}"
bashio::log.info "Top X charge count: ${TOP_X_CHARGE_COUNT}"
bashio::log.info "Price threshold: ${PRICE_THRESHOLD} EUR/kWh"
bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"
if [ -n "${SUPERVISOR_TOKEN}" ]; then
    bashio::log.info "Home Assistant API token: SET"
else
    bashio::log.warning "Home Assistant API token: NOT SET"
fi

# Start Python application
exec python3 -m app.main

