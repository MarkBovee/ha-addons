#!/usr/bin/with-contenv bashio

# Print startup message
bashio::log.info "Starting Energy Prices add-on..."

# Run Python application as a module to support relative imports
cd /app
python3 -m app.main
