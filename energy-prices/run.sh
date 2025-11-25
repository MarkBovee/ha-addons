#!/usr/bin/with-contenv bashio

# Print startup message
bashio::log.info "Starting Energy Prices add-on..."

# Run Python application
python3 /app/app/main.py
