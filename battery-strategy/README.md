# Battery Strategy Optimizer

An intelligent battery management add-on that optimizes charging and discharging based on:
- 💰 Electricity Prices (Nord Pool)
- ☀️ Solar Production (Passive "Gap" Charging)
- 🌡️ Outdoor Temperature (Heating demand)
- 🔌 Grid Import/Export limits
- 🚗 EV Charger load

## Features
- **Price-Based Optimization**: Charges during cheapest hours, discharges during most expensive.
- **Passive Solar Mode**: detects excess solar and creates a 0W charge "gap" to allow the inverter to self-consume renewable energy without grid interaction.
- **Temperature Adaptation**: Adjusts discharge duration based on heating needs (1-3 hours).
- **Protection**: Enforces minimum SOC and conservative buffers.

## Configuration
See `config.yaml` for all options.
