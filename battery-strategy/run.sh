#!/usr/bin/with-contenv bashio

echo "Starting Battery Strategy Optimizer..."
export PYTHONPATH=$PYTHONPATH:/app
exec python3 /app/app/main.py
