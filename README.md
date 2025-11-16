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
- Expose eligible counters as sensors with:
  - Meter ID (`me_id`)
  - Counter ID (`var_id`)
  - Meter serial (when available)
  - Unit metadata from CEM (e.g. `m³`, `kWh`, …)
- Automatic device structure for account and objects

> ℹ️ Historically the integration started as “water only”.  
> It now supports **generic counters**, while still fully supporting water meters.

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
  `sensor.cem_object_<slug>_meter_<me_serial_or_id>_var_<var_id>`

  Attributes:
  - `meter_id` (`me_id`)
  - `counter_id` (`var_id`)
  - `reading_timestamp_ms`
  - `last_poll_ms`
  - `me_serial` (if provided by CEM)
  - `mis_id`, `mis_name`
  - `pot_id`
  - `pot_type`
  - `cem_unit_short` (CEM `jed_zkr`, e.g. `m³`)
  - `cem_unit_name` (CEM `jed_nazev`)
  - `cem_lt_key` (CEM `lt_key` for counter type)

Example structure:

```text
CEM Account <DISPLAY_NAME>
 ├─ sensor.cem_account_<slug>_<company_id>_status
 └─ sensor.cem_account_<slug>_<company_id>_account

CEM Object <OBJECT_NAME>
 ├─ sensor.cem_object_<slug>_meter_41020614_var_104437
 └─ sensor.cem_object_<slug>_meter_46147845_var_102496
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
7. **id=222** – Global counter types / units  
   - Maps `pot_id` → unit and type metadata:
     - `jed_zkr` (unit abbreviation, e.g. `m³`)
     - `jed_nazev` (unit name, e.g. `metr krychlový`)
     - `pot_type` (instantaneous / cumulative / state / derived)
     - `lt_key` (label key for counter type)

The integration uses this chain:

```text
ID 23: Places (mis_id, mis_nazev)
   └─ ID 108 (per mis_id): Meters (me_id, me_serial, met_id)
        └─ ID 107 (per me_id): Counters (var_id, pot_id)
             └─ ID 222 (per pot_id): Unit & type (jed_zkr, jed_nazev, pot_type, lt_key)
                  └─ ID 8: Last values for each var_id
```

All calls are **read‑only** and designed to keep API load minimal.

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

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **CEM Monitoring Integration**.
3. Enter your CEM credentials.
4. Select the desired account if prompted.

Multiple CEM accounts are supported.

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