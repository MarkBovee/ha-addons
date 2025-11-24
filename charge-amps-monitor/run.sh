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

# Get Home Assistant API token from Supervisor
# SUPERVISOR_TOKEN should be automatically available as environment variable
export HA_API_TOKEN="${SUPERVISOR_TOKEN}"
export HA_API_URL="http://supervisor/core"

# Log configuration (without password)
bashio::log.info "Starting EV Charger Monitor addon"
bashio::log.info "Email: ${EMAIL}"
bashio::log.info "Host Name: ${HOST_NAME}"
bashio::log.info "Base URL: ${BASE_URL}"
bashio::log.info "Update Interval: ${UPDATE_INTERVAL} minutes"
if [ -n "${SUPERVISOR_TOKEN}" ]; then
    bashio::log.info "Home Assistant API token: SET"
else
    bashio::log.warning "Home Assistant API token: NOT SET"
fi

# Start Python application
exec python3 -m app.main

