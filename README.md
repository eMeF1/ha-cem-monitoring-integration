[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
![Version](https://img.shields.io/github/v/release/eMeF1/ha-cem-monitoring-integration)
![Downloads](https://img.shields.io/github/downloads/eMeF1/ha-cem-monitoring-integration/total)
![License](https://img.shields.io/github/license/eMeF1/ha-cem-monitoring-integration)



# CEM Monitoring Integration — Home Assistant

A custom Home Assistant integration that retrieves **CEM account data, objects (places), meters, counters, and last readings**.  
This project is community‑maintained and **not affiliated with CEM or Softlink**.

---

## Features

- Login to the CEM API
- Fetch account information
- Discover objects (`mis_id`)
- Discover meters (`me_id`, including serial numbers)
- Discover counters (`var_id`) per meter
- Hierarchical counter selection during setup — choose which counters to expose
- Configurable update intervals — control how often counter readings are refreshed (default: 30 minutes, range: 1–1440 minutes)
- Expose eligible counters as sensors with:
  - Meter ID (`me_id`)
  - Counter ID (`var_id`)
  - Meter serial (when available)
  - Unit metadata from CEM (e.g. `m³`, `kWh`, …)
- Automatic device structure for account and objects
- Debug service (`get_raw`) for inspecting raw CEM API responses

---

## Installation

### Via HACS (recommended)

1. In Home Assistant, open **HACS → Integrations → Custom repositories**.
2. Add this repository URL as a **Custom repository** (category: *Integration*).
3. Search for **CEM Monitoring Integration** in HACS and install it.
4. Restart Home Assistant.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](
  https://my.home-assistant.io/redirect/hacs_repository/?owner=eMeF1&repository=ha-cem-monitoring-integration&category=integration
)

### Manual installation

1. Download the latest release from GitHub.
2. Copy the folder:

   ```text
   custom_components/cem_monitor
   ```

   into your Home Assistant `config/custom_components` directory.

3. Restart Home Assistant.

---

## Configuration

### Initial Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **CEM Monitoring Integration**.
3. Enter your CEM credentials (username and password).
4. After authentication, you'll be presented with a hierarchical counter selection screen showing:
   - Objects (places) with their `mis_id`
   - Meters within each object with serial numbers and counter types
   - Individual counters (`var_id`) with their names
5. Select the counters you want to expose as sensors (you can select multiple).
6. Complete the setup.

Multiple CEM accounts are supported — each account is configured separately.

### Reconfiguration (Options)

To change your counter selection or update interval after initial setup:

1. Go to **Settings → Devices & Services**.
2. Find your **CEM Monitoring Integration** entry.
3. Click **Configure** (or the three-dot menu → **Configure**).
4. You can:
   - Select/deselect counters — modify which counters are exposed as sensors
   - Adjust update interval — set how often counter readings are refreshed
     - Default: 30 minutes
     - Range: 1–1440 minutes (1 minute to 24 hours)
     - Lower intervals mean more frequent updates but higher API usage

Changes take effect after saving and the integration automatically reloads.

---

## Devices & Entities

### CEM Account `<DISPLAY_NAME>`

One device per configured CEM account.

- **Account**  
  `sensor.cem_account_<slug>_<company_id>_account`  
  Attributes:
  - `company_id`
  - `customer_id`
  - `person_id`
  - `company_name`
  - `display_name`
  - `login_valid_from`
  - `login_valid_to`

- **Status**  
  `sensor.cem_account_<slug>_<company_id>_status`  
  Attributes:
  - `token_expires_at_iso`
  - `cookie_present`
  - `company_id`

---

### CEM Object `<OBJECT_NAME>`

One device per place (`mis_id`).

For each meter and selected counter, the integration exposes a sensor.  
The exact entity IDs depend on the counter type, but follow this pattern:

- **Generic counter**  
  `sensor.cem_object_<slug>_<base_name>_<me_serial>`
  
  Where:
  - `<slug>` = object name slugified (e.g., `a_133`)
  - `<base_name>` = counter type key (lt_key) slugified (e.g., `lb_poctyp_sv`)
  - `<me_serial>` = meter serial number (e.g., `41020614`)

  Attributes:
  - `Company ID (fir_id)`
  - `Place ID (mis_id)`
  - `Place name (mis_nazev)`
  - `Meter ID (me_id)`
  - `Meters serial (me_serial)`
  - `Counter ID (var_id)`
  - `Counter description (poc_desc)`
  - `Counter type ID (pot_id)`
  - `Counter value type (cik_nazev)`
  - `Unit (jed_zkr)`
  - `Language key for counter type name (lt_key)`
  - `Readout timestamp`
  - `Last updated`

Example structure:

```text
CEM Account <DISPLAY_NAME>
 ├─ sensor.cem_account_<slug>_<company_id>_status
 └─ sensor.cem_account_<slug>_<company_id>_account

CEM Object <OBJECT_NAME>
 ├─ sensor.cem_object_<slug>_<base_name>_<me_serial>
 └─ sensor.cem_object_<slug>_<base_name>_<me_serial>
```

---

## How the integration talks to CEM

The integration performs **read‑only** HTTP calls against the CEM API. All API endpoints and their usage are detailed in the [Architecture](#architecture) section below. The integration is designed to keep API load minimal by using batch requests and caching counter type metadata (7-day TTL, persists across Home Assistant reloads).

For more details about the CEM API, see the public API documentation:

- https://cemapi.unimonitor.eu/

---

## Architecture

The integration uses a coordinator-based architecture following Home Assistant's best practices. Coordinators manage data fetching, caching, and updates for different aspects of the CEM API.

### Coordinator Hierarchy

```
CEMAuthCoordinator (Base)
├─ Purpose: Authentication & token management
├─ Update Frequency: Dynamic (~5 min before expiry, min 5 min)
├─ API Endpoint: id=4 (Login)
└─ Provides: access_token, cookie, token expiry

CEMBaseCoordinator (Base class)
├─ Provides: 401 error handling, token refresh logic
└─ Inherited by all data coordinators

Data Coordinators (all inherit from CEMBaseCoordinator):
│
├─ CEMUserInfoCoordinator
│  ├─ Purpose: Account/user information
│  ├─ Update Frequency: 12 hours
│  ├─ API Endpoint: id=9
│  └─ Provides: company_id, display_name, login validity
│
├─ CEMObjectsCoordinator
│  ├─ Purpose: Objects/sites list (mis_id)
│  ├─ Update Frequency: 12 hours
│  ├─ API Endpoint: id=23
│  └─ Provides: mis_id, mis_name, mis_idp (parent relationships)
│
├─ CEMMetersCoordinator
│  ├─ Purpose: Meters list (me_id)
│  ├─ Update Frequency: 12 hours
│  ├─ API Endpoint: id=108
│  └─ Provides: me_id, mis_id, me_name, me_serial
│
├─ CEMMeterCountersCoordinator (one per meter)
│  ├─ Purpose: Counters list for a specific meter
│  ├─ Update Frequency: 12 hours
│  ├─ API Endpoint: id=107&me_id=...
│  └─ Provides: var_id, pot_id, counter metadata
│
└─ CEMCounterReadingCoordinator (one per var_id)
   ├─ Purpose: Latest reading for a specific counter
   ├─ Update Frequency: Manual (batch refresh, default 30 min)
   ├─ API Endpoint: id=8&var_id=... (or batch POST id=8)
   └─ Provides: value, timestamp_ms, timestamp_iso
```

### API Endpoints

The integration uses the following CEM API endpoints (all **read‑only**):

1. **id=4** – Login  
   - Used by: `CEMAuthCoordinator`
   - Returns: `access_token`, `valid_to`, sets `CEMAPI` cookie
   - Called: During authentication and token refresh

2. **id=9** – User info  
   - Used by: `CEMUserInfoCoordinator`
   - Returns: `company_id`, `customer_id`, `person_id`, `company_name`, `display_name`, `login_valid_from`, `login_valid_to`
   - Called: Every 12 hours

3. **id=23** – Objects (places) list  
   - Used by: `CEMObjectsCoordinator`
   - Returns: List of objects with `mis_id`, `mis_nazev`, `mis_idp` (parent relationships)
   - Called: Every 12 hours

4. **id=108** – Meters per object  
   - Used by: `CEMMetersCoordinator`
   - Returns: List of meters with `me_id`, `met_id`, `me_serial`, `mis_id`, `me_name`
   - Called: Every 12 hours

5. **id=107** – Counters per meter  
   - Used by: `CEMMeterCountersCoordinator` (one per meter)
   - Parameters: `me_id` (meter ID)
   - Returns: List of counters with `var_id`, `me_id`, `pot_id`, counter metadata
   - Called: Every 12 hours (per meter)

6. **id=8** – Last counter values  
   - Used by: `CEMCounterReadingCoordinator` (one per var_id)
   - Parameters: `var_id` (counter ID) or batch POST with array of `var_id` objects
   - Returns: Latest reading with `value`, `timestamp` (ms), `var_id`
   - Called: Batch refresh at configured interval (default: 30 minutes)

7. **id=11** – Counter value types  
   - Used by: Setup/initialization (not a coordinator)
   - Parameters: `cis=50`
   - Returns: Mapping of `pot_type` (via `cik_fk`) → `cik_nazev` (human-readable counter value type names)
   - Examples: "Přírustková", "Absolutní", "Výčtová", "Absolutní součtová"
   - Called: Once per account setup (cached with 7-day TTL, persists across Home Assistant reloads)

8. **id=222** – Global counter types / units  
   - Used by: Setup/initialization (not a coordinator)
   - Returns: Global mapping of `pot_id` → unit and type metadata:
     - `jed_zkr` (unit abbreviation, e.g. `m³`)
     - `jed_nazev` (unit name, e.g. `metr krychlový`)
     - `pot_type` (counter type: 0=instantaneous, 1=cumulative/total, 2=state, 3=derived)
     - `lt_key` (label key for counter type)
   - Used to filter counters: only types 0, 1, and 3 are exposed as sensors (type 2 state counters like door/contact sensors are excluded)
   - Called: Once per account setup (cached with 7-day TTL, persists across Home Assistant reloads)

**Call Chain During Setup:**

```
┌─────────────────────────────────────────────────────────────┐
│                    ID 23: Places                            │
│         Returns: mis_id, mis_nazev                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ID 108: Meters                           │
│         Returns: me_id, me_serial, met_id, mis_id           │
│         (per object from ID 23)                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ID 107: Counters                         │
│         Returns: var_id, pot_id                             │
│         (per me_id from ID 108)                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ID 222: Unit & Type Mapping              │
│         Returns: jed_zkr, jed_nazev, pot_type, lt_key       │
│         (global, once, cached with 7-day TTL)               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ID 11: Counter Value Types               │
│         Returns: cik_fk → cik_nazev mapping                 │
│         (global, once, cis=50, cached with 7-day TTL)       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Filter by pot_type                       │
│         Exclude type 2 (state counters)                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ID 8: Last Values                        │
│         Returns: value, timestamp for selected var_ids      │
└─────────────────────────────────────────────────────────────┘
```

All calls are designed to keep API load minimal. The integration uses endpoints id=222 and id=11 to fetch all counter type definitions and value type names once during setup (cached with 7-day TTL, persists across Home Assistant reloads), then filters counters based on `pot_type` before exposing them as sensors.

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Integration Setup                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              CEMAuthCoordinator (id=4)                      │
│         Authenticates and provides token/cookie             │
│         Update: Dynamic (before token expiry)               │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ UserInfo     │   │ Objects      │   │ Meters       │
│ (id=9)       │   │ (id=23)      │   │ (id=108)     │
│ 12h interval │   │ 12h interval │   │ 12h interval │
└──────────────┘   └──────────────┘   └──────────────┘
        │                   │                   │
        │                   │                   ▼
        │                   │         ┌─────────────────────┐
        │                   │         │ MeterCounters       │
        │                   │         │ (id=107, per me_id) │
        │                   │         │ 12h interval        │
        │                   │         └─────────────────────┘
        │                   │                   │
        │                   │                   ▼
        │                   │         ┌─────────────────────┐
        │                   │         │ CounterReading      │
        │                   │         │ (id=8, per var_id)  │
        │                   │         │ Batch refresh       │
        │                   │         │ (default: 30 min)   │
        │                   │         └─────────────────────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Sensor Entities                          │
│  - CEMApiStatusSensor (uses CEMAuthCoordinator)             │
│  - CEMAccountSensor (uses CEMUserInfoCoordinator)           │
│  - CEMCounterSensor (uses CEMCounterReadingCoordinator)     │
└─────────────────────────────────────────────────────────────┘
```

### Update Strategy

1. **Authentication**: `CEMAuthCoordinator` refreshes tokens automatically before expiry (minimum 5 minutes between refreshes)

2. **Metadata Coordinators** (UserInfo, Objects, Meters, MeterCounters):
   - Update every 12 hours automatically
   - Used for discovery and setup
   - Changes infrequently, so 12-hour interval is appropriate

3. **Counter Readings**:
   - No automatic periodic updates at coordinator level
   - Batch refresh mechanism in `__init__.py`:
     - Collects all `var_id` values
     - Uses batch API (POST id=8) when possible
     - Falls back to individual requests if batch fails
     - Default interval: 30 minutes (configurable via integration options)
     - Range: 1-1440 minutes

4. **Error Handling**:
   - All coordinators inherit 401 error handling from `CEMBaseCoordinator`
   - On 401: automatically refresh token and retry once
   - Prevents stale token issues

### Key Design Decisions

- **Shared Counter Readings**: One `CEMCounterReadingCoordinator` per `var_id` across all meters (counters can be shared)
- **Batch Updates**: Counter readings use batch API to minimize API calls
- **Lazy Loading**: Counter reading coordinators are created only for selected counters
- **Token Management**: Centralized in `CEMAuthCoordinator`, all other coordinators depend on it

---

## Services

### `cem_monitor.get_raw`

Call a CEM API endpoint and receive the raw JSON response via a Home Assistant event. This service is useful for debugging and inspecting the CEM API responses.

**Service Data:**
- `endpoint` (required): The CEM endpoint to call. Available options:
  - `user_info` — User/company information (id=9)
  - `objects` — List of objects/places (id=23)
  - `meters` — List of meters (id=108)
  - `counters_by_meter` — Counters for a specific meter (id=107)
  - `counter_last` — Last reading for a specific counter (id=8)
- `mis_id` (optional): Object ID, required for `meters` endpoint
- `me_id` (optional): Meter ID, required for `counters_by_meter` endpoint
- `var_id` (optional): Counter ID, required for `counter_last` endpoint

**Event:**
After calling the service, a `cem_monitor_raw_response` event is fired with:
- `endpoint`: The endpoint that was called
- `data`: The raw JSON response from the CEM API
- `context_id`: The context ID of the service call

**Example:**
```yaml
service: cem_monitor.get_raw
data:
  endpoint: counter_last
  var_id: 104437
```

Then listen for the event:
```yaml
event: cem_monitor_raw_response
```

---

## Troubleshooting

- **Names not updating**  
  Try removing the device from Home Assistant, then reload the integration.

- **Statistics warnings after unit changes**  
  If units were changed in a newer version, you may need to clear or realign old statistics in Home Assistant.

- **Missing serial numbers**  
  Some meters in CEM do not expose `me_serial`. In that case, entity names fall back to `me_id`.

- **No counters or missing entities**  
  - Verify the CEM web portal shows meters and counters for your account.
  - Check Home Assistant logs for messages from `custom_components.cem_monitor`.
  - Remember that only counters you selected during setup (or in options) are exposed. If you want to add more counters, use the **Configure** option in the integration settings.

- **Counter not showing up**  
  - The counter may not have been selected during setup. Go to **Settings → Devices & Services → CEM Monitoring Integration → Configure** and ensure the counter is selected.
  - Some counter types (state counters like door/contact sensors) are automatically excluded. Only numeric counters (instantaneous, cumulative, and derived) are exposed.

- **Counters not updating**  
  - Check the update interval setting in the integration options (default: 30 minutes).
  - If you need more frequent updates, reduce the interval (minimum: 1 minute). Note that very short intervals may increase API load.
  - Check Home Assistant logs for any errors during refresh.

- **Too many API calls**  
  - Increase the counter update interval in the integration options to reduce API usage.
  - Consider selecting only the counters you actually need rather than all available counters.

---

## Privacy

- Credentials are stored and managed by Home Assistant.
- Only **read‑only** CEM API calls are used.
- No data is sent to any third‑party services other than CEM itself.

---

## Disclaimer

This is an **unofficial** Home Assistant integration.  
It is provided as‑is by the community. Use at your own risk.

---

## License

MIT
