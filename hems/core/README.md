# hems (core)
Hardware-agnostic planning core for HEMS v2. No Home Assistant imports.
- prices.py   import/export price contract (saldering on/off)
- battery.py  DP planner, rolling horizon, wear margin, SoC floor, charge->discharge cycle
- balancer.py priority load balancer, default grid limit 15 kW, hysteresis
- forecast.py median hour-of-day consumption baseline
- trace.py    JSONL decision trace
Run: `pip install pytest && pytest`
Next: HA integration shell (coordinator, sensors), Open-Meteo forecast, capability contracts.
