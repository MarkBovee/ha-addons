#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Battery Manager add-on..."

export ENABLED=$(bashio::config 'enabled' 'true')
export DRY_RUN=$(bashio::config 'dry_run' 'false')

export UPDATE_INTERVAL=$(bashio::config 'timing.update_interval' '3600')
export MONITOR_INTERVAL=$(bashio::config 'timing.monitor_interval' '60')

export MAX_CHARGE_POWER=$(bashio::config 'power.max_charge_power' '8000')
export MAX_DISCHARGE_POWER=$(bashio::config 'power.max_discharge_power' '8000')
export MIN_DISCHARGE_POWER=$(bashio::config 'power.min_discharge_power' '4000')

export MIN_SOC=$(bashio::config 'soc.min_soc' '5')
export CONSERVATIVE_SOC=$(bashio::config 'soc.conservative_soc' '40')
export TARGET_EOD_SOC=$(bashio::config 'soc.target_eod_soc' '20')

export TOP_X_CHARGE_HOURS=$(bashio::config 'heuristics.top_x_charge_hours' '3')
export TOP_X_DISCHARGE_HOURS=$(bashio::config 'heuristics.top_x_discharge_hours' '2')
export EXCESS_SOLAR_THRESHOLD=$(bashio::config 'heuristics.excess_solar_threshold' '1000')

export TEMP_DISCHARGE_ENABLED=$(bashio::config 'temperature_based_discharge.enabled' 'true')
export TEMP_DISCHARGE_THRESHOLDS=$(bashio::config 'temperature_based_discharge.thresholds')

export EV_CHARGER_ENABLED=$(bashio::config 'ev_charger.enabled' 'true')
export EV_CHARGER_THRESHOLD=$(bashio::config 'ev_charger.charging_threshold' '500')
export EV_CHARGER_ENTITY_ID=$(bashio::config 'ev_charger.entity_id' 'sensor.ev_charger_power')

export MQTT_HOST=$(bashio::config 'mqtt_host' 'core-mosquitto')
export MQTT_PORT=$(bashio::config 'mqtt_port' '1883')

if bashio::config.exists 'mqtt_user' && bashio::config.has_value 'mqtt_user'; then
    export MQTT_USER=$(bashio::config 'mqtt_user')
fi
if bashio::config.exists 'mqtt_password' && bashio::config.has_value 'mqtt_password'; then
    export MQTT_PASSWORD=$(bashio::config 'mqtt_password')
fi

bashio::log.info "Enabled: ${ENABLED}"
bashio::log.info "Dry run: ${DRY_RUN}"
bashio::log.info "Update interval: ${UPDATE_INTERVAL}s"
bashio::log.info "Monitor interval: ${MONITOR_INTERVAL}s"
bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"

cd /app
exec python3 -m app.main
