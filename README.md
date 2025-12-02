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

The integration performs a small set of **read‑only** HTTP calls against the CEM API.

### Main endpoints

1. **id=4** – Login  
2. **id=9** – User info  
3. **id=23** – Objects (places) list  
4. **id=108** – Meters per object  
   - Returns `me_id`, `met_id`, `me_serial`, `mis_id`, …
5. **id=107** – Counters per meter  
   - Returns `var_id`, `me_id`, `pot_id`, last value and timestamp, …
6. **id=8** – Last counter values  
   - Returns latest readings for specific counters (`var_id`)
7. **id=11** – Counter value types  
   - Fetched once per account setup with parameter `cis=50`
   - Maps `pot_type` (via `cik_fk`) → `cik_nazev` (counter value type name)
   - Provides human-readable names for counter value types (e.g., "Přírustková", "Absolutní", "Výčtová", "Absolutní součtová")
8. **id=222** – Global counter types / units  
   - Fetched once per account setup to build a global mapping
   - Maps `pot_id` → unit and type metadata:
     - `jed_zkr` (unit abbreviation, e.g. `m³`)
     - `jed_nazev` (unit name, e.g. `metr krychlový`)
     - `pot_type` (counter type: 0=instantaneous, 1=cumulative/total, 2=state, 3=derived)
     - `lt_key` (label key for counter type)
   - Used to filter counters: only types 0, 1, and 3 are exposed as sensors (type 2 state counters like door/contact sensors are excluded)

The integration uses this chain:

```text
ID 23: Places (mis_id, mis_nazev)
   └─ ID 108: Meters (me_id, me_serial, met_id, mis_id)
        └─ ID 107 (per me_id): Counters (var_id, pot_id)
             └─ ID 222 (global, once): Unit & type mapping (jed_zkr, jed_nazev, pot_type, lt_key)
                  └─ ID 11 (global, once, cis=50): Counter value type names (cik_fk → cik_nazev)
                       └─ Filter by pot_type (exclude type 2)
                            └─ ID 8: Last values for selected var_ids
```

All calls are **read‑only** and designed to keep API load minimal. The integration uses endpoints id=222 and id=11 to fetch all counter type definitions and value type names once during setup, then filters counters based on `pot_type` before exposing them as sensors.

For more details, see the public API site:

- https://cemapi.unimonitor.eu/

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