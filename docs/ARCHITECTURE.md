# Architecture

The integration uses a coordinator-based architecture following Home Assistant's best practices. Coordinators manage data fetching, caching, and updates for different aspects of the CEM API.

## Coordinator Hierarchy

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

## API Endpoints

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

## Call Chain During Setup

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

## Data Flow

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

## Update Strategy

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

## Key Design Decisions

- **Shared Counter Readings**: One `CEMCounterReadingCoordinator` per `var_id` across all meters (counters can be shared)
- **Batch Updates**: Counter readings use batch API to minimize API calls
- **Lazy Loading**: Counter reading coordinators are created only for selected counters
- **Token Management**: Centralized in `CEMAuthCoordinator`, all other coordinators depend on it

## Code Organization

The codebase is organized into the following structure:

```
custom_components/cem_monitor/
├── __init__.py              # Integration setup and entry points
├── api.py                   # CEM API client
├── cache.py                 # Types cache for pot_types and counter_value_types
├── config_flow.py           # Configuration flow UI
├── const.py                 # Constants
├── sensor.py                # Sensor entities
├── services.yaml            # Service definitions
├── manifest.json            # Integration manifest
├── strings.json             # UI strings
├── coordinators/            # Coordinator classes
│   ├── base.py              # Base coordinator and auth coordinator
│   ├── userinfo.py          # User info coordinator
│   ├── objects.py           # Objects coordinator
│   ├── meters.py            # Meters coordinator
│   ├── meter_counters.py    # Meter counters coordinator
│   └── counter_reading.py   # Counter reading coordinator
└── utils/                   # Utility modules
    ├── discovery.py         # Discovery utilities
    ├── retry.py             # Retry logic
    └── validators.py        # Validation utilities
```

