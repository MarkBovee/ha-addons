# Energy Prices Add-on - Technical Design

**Change ID:** 1.0-energy-prices-addon  
**Version:** 1.0  
**Last Updated:** 2025-11-25

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Home Assistant                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Entities:                                            │   │
│  │  - sensor.ep_price_import    (state: current cents)  │   │
│  │  - sensor.ep_price_export    (state: current cents)  │   │
│  │  - sensor.ep_price_level     (state: None/Low/Med/Hi)│   │
│  └──────────────────────────────────────────────────────┘   │
│                           ▲                                  │
│                           │ REST API (/api/states/)          │
└───────────────────────────┼──────────────────────────────────┘
                            │
┌───────────────────────────┼──────────────────────────────────┐
│  Energy Prices Add-on     │                                  │
│  ┌────────────────────────┴──────────────────────────────┐  │
│  │ app/main.py (Main Loop)                               │  │
│  │  - Load config from /data/options.json                │  │
│  │  - Initialize API client & template processors        │  │
│  │  - Fetch prices every N minutes                       │  │
│  │  - Calculate import/export prices                     │  │
│  │  - Compute percentiles & price level                  │  │
│  │  - Update HA entities                                 │  │
│  │  - Handle SIGTERM/SIGINT gracefully                   │  │
│  └────┬──────────────┬────────────────┬──────────────────┘  │
│       │              │                │                      │
│  ┌────▼──────┐  ┌────▼─────────┐  ┌──▼──────────────────┐  │
│  │NordPoolApi│  │TemplateProc  │  │ Percentile Calc     │  │
│  │           │  │(import/export)│  │ & Price Level       │  │
│  │fetch_prices│ │calculate_price│ │ Classification      │  │
│  └────┬──────┘  └────┬─────────┘  └─────────────────────┘  │
│       │              │                                       │
│  ┌────▼──────┐  ┌────▼─────────┐                           │
│  │PriceInterval│ │Jinja2 Sandbox│                           │
│  │  model      │ │Environment    │                           │
│  └─────────────┘  └──────────────┘                           │
└──────────────────────────────────────────────────────────────┘
            │
            │ HTTPS GET
            ▼
┌─────────────────────────────────────────────────────────────┐
│  Nord Pool Day-Ahead Prices API                              │
│  https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices │
│  - Returns 96 x 15-min intervals per day                     │
│  - Prices in EUR/MWh                                         │
│  - UTC timestamps                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. NordPoolApi (`app/nordpool_api.py`)

**Purpose:** Fetch day-ahead electricity prices from Nord Pool API

**Key Methods:**
```python
class NordPoolApi:
    def __init__(self):
        """Initialize with requests.Session for connection pooling"""
        
    def fetch_prices(self, date: str, delivery_area: str, currency: str) -> List[PriceInterval]:
        """
        Fetch prices for specific date and delivery area.
        
        Args:
            date: YYYY-MM-DD format
            delivery_area: e.g., "NL" for Netherlands
            currency: e.g., "EUR"
            
        Returns:
            List of PriceInterval objects (sorted by start_time)
            Empty list if data not available (HTTP 204)
            
        Raises:
            requests.HTTPError: If API returns error status
            ValueError: If response format is invalid
        """
```

**Design Decisions:**
- **Session Reuse:** Creates `requests.Session()` in `__init__` for connection pooling and header reuse
- **Error Handling:** Distinguishes between "data not available yet" (HTTP 204) vs actual errors (HTTP 4xx/5xx)
- **Price Conversion:** Converts EUR/MWh → cents/kWh immediately (multiply by 0.1) to avoid repeated conversions
- **Timestamp Handling:** Parses ISO 8601 strings to UTC-aware `datetime` objects using `datetime.fromisoformat()`
- **Logging:** Logs request params, response status, number of intervals, and conversion for first interval

---

### 2. TemplateProcessor (`app/price_calculator.py`)

**Purpose:** Apply user-defined Jinja2 templates to calculate final prices

**Key Methods:**
```python
class TemplateProcessor:
    def __init__(self, template_str: str):
        """
        Initialize and validate Jinja2 template.
        
        Args:
            template_str: Jinja2 template string
            
        Raises:
            jinja2.TemplateSyntaxError: If template has syntax errors
        """
        
    def calculate_price(self, marktprijs_cents: float) -> float:
        """
        Calculate price using template.
        
        Args:
            marktprijs_cents: Market price in cents/kWh
            
        Returns:
            Calculated price rounded to 4 decimals
            
        Raises:
            jinja2.TemplateError: If template rendering fails
            ValueError: If output is not numeric
        """
```

**Design Decisions:**
- **Sandboxed Environment:** Uses `jinja2.sandbox.SandboxedEnvironment` to prevent code injection attacks
- **Fail-Fast Validation:** Template syntax is validated in `__init__`; add-on won't start with invalid templates
- **Simple Context:** Only exposes `marktprijs` variable (cents/kWh) to keep templates simple and predictable
- **Precision Control:** Always rounds output to 4 decimals (0.01 cent precision) to prevent floating-point issues
- **Error Context:** If rendering fails, logs template string, input value, and error message for debugging

**Template Format:**
```jinja2
{# Dutch import price example #}
{% set marktprijs = marktprijs %}
{% set opslag_inc = 2.48 %}
{% set energiebelasting_inc = 12.28 %}
{% set btw = 1.21 %}
{{ (marktprijs * btw + opslag_inc + energiebelasting_inc) | round(4) }}
```

**Why Jinja2 over config values?**
1. Users can see exactly how prices are calculated (transparency)
2. Supports complex formulas (tiered taxes, time-based fees)
3. Easy to adjust for contract changes without code updates
4. Familiar syntax for HA users (used in automations)

---

### 3. PriceInterval Model (`app/models.py`)

**Purpose:** Represent a single 15-minute price interval

**Structure:**
```python
@dataclass
class PriceInterval:
    start_time: datetime  # UTC-aware
    end_time: datetime    # UTC-aware
    price_cents_kwh: float  # Base market price (before templates)
    
    @classmethod
    def from_dict(cls, data: dict, delivery_area: str) -> 'PriceInterval':
        """Create from Nord Pool API JSON entry"""
        
    def to_dict(self) -> dict:
        """Serialize to dict for HA entity attributes"""
```

**Design Decisions:**
- **Immutable:** Uses `@dataclass(frozen=True)` to prevent accidental modification
- **UTC Timestamps:** All times stored in UTC to avoid DST confusion
- **Pre-conversion:** Stores cents/kWh (not EUR/MWh) since that's what templates and users need
- **Serialization:** `to_dict()` formats timestamps as ISO 8601 strings for JSON attributes

---

### 4. Main Loop (`app/main.py`)

**Purpose:** Orchestrate fetching, calculation, and entity updates

**Flow:**
```python
def main():
    # 1. Load config from /data/options.json
    config = load_config()
    
    # 2. Initialize components (fail-fast if templates invalid)
    api = NordPoolApi()
    import_processor = TemplateProcessor(config['import_price_template'])
    export_processor = TemplateProcessor(config['export_price_template'])
    
    # 3. Set up signal handlers for graceful shutdown
    setup_signal_handlers()
    
    # 4. Main loop
    while not shutdown_flag.is_set():
        try:
            # Fetch today + tomorrow prices
            prices = fetch_all_prices(api, config)
            
            # Calculate import/export for each interval
            calculated = calculate_prices(prices, import_processor, export_processor)
            
            # Compute percentiles from import prices
            percentiles = compute_percentiles(calculated)
            
            # Determine current price level
            level = classify_price_level(calculated, percentiles)
            
            # Update HA entities
            update_entities(calculated, percentiles, level)
            
            # Sleep until next fetch (check shutdown flag every second)
            sleep_with_interrupt(config['fetch_interval_minutes'] * 60)
            
        except Exception as e:
            logger.error("Error in main loop: %s", e, exc_info=True)
            sleep_with_interrupt(60)  # Retry after 1 minute
```

**Design Decisions:**
- **Single-threaded:** No threading complexity; simple loop with sleep
- **Graceful Shutdown:** Checks `shutdown_flag` every second during sleep
- **Error Recovery:** Catches exceptions in loop; logs and continues (don't crash on API errors)
- **Fetch Strategy:** Always fetch both today and tomorrow (tomorrow returns 204 before ~13:00 CET)
- **Entity Updates:** Uses POST to `/api/states/{entity_id}` with full state + attributes

---

## Data Flow Example

**Input:** Nord Pool API returns 96 intervals for 2025-11-25 in EUR/MWh

**Step 1: API Fetch**
```json
{
  "deliveryStart": "2025-11-24T23:00:00Z",
  "deliveryEnd": "2025-11-24T23:15:00Z",
  "entryPerArea": {"NL": 97.94}
}
```

**Step 2: Conversion to PriceInterval**
```python
PriceInterval(
    start_time=datetime(2025, 11, 24, 23, 0, 0, tzinfo=timezone.utc),
    end_time=datetime(2025, 11, 24, 23, 15, 0, tzinfo=timezone.utc),
    price_cents_kwh=9.794  # 97.94 * 0.1
)
```

**Step 3: Template Calculation (Import)**
```python
# Template: {{ (marktprijs * 1.21 + 2.48 + 12.28) | round(4) }}
# Input: marktprijs = 9.794
# Output: 26.6307 cents/kWh
```

**Step 4: HA Entity State**
```json
{
  "entity_id": "sensor.ep_price_import",
  "state": "26.6307",
  "attributes": {
    "unit_of_measurement": "cents/kWh",
    "device_class": "monetary",
    "friendly_name": "Energy Price Import",
    "price_curve": [
      {"start": "2025-11-24T23:00:00Z", "end": "2025-11-24T23:15:00Z", "price": 26.6307},
      // ... 95 more intervals
    ],
    "percentiles": {
      "p05": 18.2345,
      "p20": 22.1234,
      "p40": 28.4567,
      "p60": 35.6789,
      "p80": 42.8901,
      "p95": 51.2345
    },
    "last_update": "2025-11-25T10:00:00Z"
  }
}
```

---

## Configuration Schema

**File:** `config.yaml`

```yaml
options:
  delivery_area: "NL"
  currency: "EUR"
  timezone: "CET"
  import_price_template: |
    {% set marktprijs = marktprijs %}
    {% set opslag_inc = 2.48 %}
    {% set energiebelasting_inc = 12.28 %}
    {% set btw = 1.21 %}
    {{ (marktprijs * btw + opslag_inc + energiebelasting_inc) | round(4) }}
  export_price_template: "{{ marktprijs | round(4) }}"
  fetch_interval_minutes: 60

schema:
  delivery_area: str
  currency: str
  timezone: str
  import_price_template: str
  export_price_template: str
  fetch_interval_minutes: int(1,1440)  # 1 min to 24 hours
```

**Why these settings?**
- `delivery_area`: Different countries/regions have different prices (NL vs DE vs SE)
- `timezone`: For display purposes (internally everything is UTC)
- Templates: Max flexibility for different energy contracts
- `fetch_interval_minutes`: Balance between freshness and API load (60 min default)

---

## Percentile Calculation Algorithm

**Purpose:** Classify prices as None/Low/Medium/High based on distribution

**Algorithm:**
```python
def compute_percentiles(prices: List[float]) -> dict:
    """
    Compute percentiles from price list.
    Uses linear interpolation for non-exact percentiles.
    """
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    
    def percentile(p: float) -> float:
        """Calculate pth percentile (p in 0-1)"""
        index = p * (n - 1)
        lower = int(index)
        upper = min(lower + 1, n - 1)
        weight = index - lower
        return sorted_prices[lower] * (1 - weight) + sorted_prices[upper] * weight
    
    return {
        'p05': percentile(0.05),
        'p20': percentile(0.20),
        'p40': percentile(0.40),
        'p60': percentile(0.60),
        'p80': percentile(0.80),
        'p95': percentile(0.95),
    }

def classify_price_level(current_price: float, percentiles: dict) -> str:
    """Classify price into None/Low/Medium/High"""
    if current_price < percentiles['p20']:
        return "None"  # Very cheap (bottom 20%)
    elif current_price < percentiles['p40']:
        return "Low"   # Below average (20-40%)
    elif current_price < percentiles['p60']:
        return "Medium"  # Average (40-60%)
    else:
        return "High"  # Above average (60%+)
```

**Why these thresholds?**
- P20 (20th percentile): Bottom quintile = "None" (best time to use energy)
- P40: Below median = "Low" (still good time)
- P60: Above median = "Medium" (okay time)
- Above P60: "High" (avoid if possible)

**Alternative considered:** Absolute thresholds (e.g., <20 cents = low)
- **Rejected because:** Market prices vary seasonally; relative thresholds adapt automatically

---

## Error Handling Strategy

### Template Validation Errors
- **When:** Add-on startup
- **Action:** Log error with line number and syntax issue; exit with non-zero code
- **Rationale:** Better to fail immediately than produce wrong prices

### Template Rendering Errors
- **When:** During price calculation
- **Action:** Log error with template and input value; skip that interval
- **Rationale:** One bad interval shouldn't crash entire update; price curve will have gaps

### API Network Errors
- **When:** Nord Pool fetch fails (timeout, DNS, connection refused)
- **Action:** Log error; skip this update cycle; retry in next interval
- **Rationale:** Transient network issues shouldn't require manual intervention

### API HTTP Errors
- **When:** Nord Pool returns 4xx/5xx (except 204)
- **Action:** Log error with status code and response body; retry with exponential backoff
- **Rationale:** Might be temporary server issue or rate limiting

### HA API Errors
- **When:** Entity update fails
- **Action:** Log error; continue operation (still fetch/calculate prices)
- **Rationale:** Price data is still valid even if HA temporarily unreachable

---

## Performance Considerations

### Memory Usage
- **Price Storage:** 96 intervals × 2 days × ~100 bytes/interval = ~20KB
- **Peak Memory:** ~50MB (Python runtime + libraries)
- **Target:** <100MB total (suitable for Raspberry Pi)

### CPU Usage
- **Price Fetch:** <1 second (HTTP GET + JSON parse)
- **Template Calculation:** <10ms for 192 intervals
- **Percentile Calculation:** <5ms (simple sort + interpolation)
- **Total Update Cycle:** <2 seconds
- **Target:** <5% CPU on Raspberry Pi 4

### Network Bandwidth
- **API Fetch:** ~10KB per request (JSON response)
- **HA Entity Updates:** ~30KB per update (3 entities with attributes)
- **Total per Hour:** ~40KB (negligible)

### Disk I/O
- **Logs:** ~1MB per day (info level)
- **Config:** Read once at startup
- **No Persistence:** Prices re-fetched on restart (stateless)

---

## Security Considerations

### Template Sandboxing
- **Threat:** Malicious template could execute arbitrary Python code
- **Mitigation:** Use `jinja2.sandbox.SandboxedEnvironment` (restricts access to builtins)
- **Limitation:** Users can still write CPU-intensive templates (e.g., infinite loops)
- **Future:** Add template execution timeout

### API Authentication
- **Nord Pool API:** No authentication required (public data)
- **HA Supervisor API:** Uses supervisor token (automatically provided by HA)
- **Risk:** Low (all communication over local network or HTTPS)

### Configuration Secrets
- **Templates:** May contain sensitive pricing details (e.g., negotiated rates)
- **Mitigation:** Templates stored in `/data/options.json` (accessible only to add-on)
- **No Secrets:** No passwords or API keys required

---

## Testing Strategy

### Unit Tests
- `test_nordpool_api.py`: Mock HTTP responses, verify parsing and conversion
- `test_template_processor.py`: Test valid/invalid templates, precision, error handling
- `test_percentiles.py`: Test with known distributions, edge cases

### Integration Tests
- `test_main_loop.py`: Mock API and HA responses, verify full flow
- Test graceful shutdown behavior
- Test error recovery (API failures, template errors)

### Manual Testing
- Install in HA dev instance
- Verify entities created with correct attributes
- Check price curves have 48h data
- Test template modification (update config, restart)
- Test invalid template (should fail to start with clear error)
- Monitor logs for 24h (check for memory leaks, unexpected errors)

### Performance Testing
- Monitor memory usage over 24h period
- Measure CPU usage during update cycle
- Verify fetch interval is respected (±5 seconds)

---

## Future Enhancements (Out of Scope for v1.0)

1. **Configurable Percentile Thresholds**
   - Allow users to customize P20/P40/P60 values
   - Default remains 20/40/60 for simplicity
   
2. **Historical Price Storage**
   - Store prices in SQLite for analysis
   - Provide "average price last 7 days" sensor
   
3. **Multi-Region Support**
   - Support multiple delivery areas simultaneously
   - Create separate entities per region
   
4. **Intraday Price Updates**
   - Nord Pool publishes intraday corrections
   - Currently only uses day-ahead prices
   
5. **REST API Endpoints**
   - Expose `/api/prices/{date}` endpoint
   - Allow other add-ons to query without parsing entity attributes
   
6. **Template Marketplace**
   - Share template snippets for different countries/contracts
   - Built-in templates for common energy providers

---

## Deployment Checklist

- [ ] Add-on builds successfully in HA Supervisor
- [ ] All configuration options have defaults
- [ ] Templates validate correctly
- [ ] Prices fetch and convert accurately
- [ ] Entities created with correct attributes
- [ ] Price curves have 48h UTC timestamps
- [ ] Percentiles calculated correctly
- [ ] Price level classification works
- [ ] Graceful shutdown responds to SIGTERM
- [ ] Logs are informative but not verbose
- [ ] README documentation is complete
- [ ] Example templates are tested and working
