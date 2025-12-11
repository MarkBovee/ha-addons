#!/usr/bin/with-contenv bashio

bashio::log.info "Starting HEMS add-on..."

cd /app
python3 -m app.main
