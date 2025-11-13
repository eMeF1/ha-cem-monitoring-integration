# CEM Monitor (Unofficial) — Home Assistant Integration

A custom integration that pulls **CEM** account, objects (places), meters, and **water readings** into Home Assistant.  
**This project is not affiliated with CEM. Use at your own risk.**

---

## What it creates

### Devices
- **CEM Account _&lt;DISPLAY_NAME&gt;_**  
  - `sensor.cem_account_<account_slug>_<company_id>_status` — connection status  
    - attrs: `token_expires_at_iso`, `cookie_present`, `company_id`
  - `sensor.cem_account_<account_slug>_<company_id>_account` — concise account info  
    - attrs: `company_id`, `customer_id`, `person_id`, `company_name`, `display_name`, `login_valid_from`, `login_valid_to`

- **CEM Object _&lt;OBJECT_NAME&gt;_** (one per `mis_id`)  
  - **Water [SN]** sensors (one per selected counter / `var_id`)  
    - device class: **water**  
    - state class: **total_increasing**  
    - unit: **m³** (liters are auto-converted to m³)  
    - entity name includes **meter serial** when available; falls back to `me<id>`

**Example**
```
Devices
├─ CEM Account <DISPLAY_NAME>
│  ├─ sensor.cem_account_<account_slug>_<company_id>_status
│  └─ sensor.cem_account_<account_slug>_<company_id>_account
└─ CEM Object <OBJECT_NAME>
   ├─ sensor.cem_object_<object_slug>_water_[<serial_or_meid>]_var_<VAR_ID_1>
   └─ sensor.cem_object_<object_slug>_water_[<serial_or_meid>]_var_<VAR_ID_2>
```

> Notes
> - Account **device name** shows only the display name (e.g., “CEM Account &lt;DISPLAY_NAME&gt;”).  
> - `<company_id>` is **kept in entity_ids** for uniqueness when multiple accounts are added.

---

## How data flows (CEM API)

The integration performs these read-only calls:

1. **Login** — `id=4` → tokens/cookie  
2. **User info** — `id=9` → `company_id`, display name  
3. **Objects (places)** — `id=23` → list of `mis_id`, names  
4. **Meters** — `id=108` → list of meters per object (`me_id`, `mis_id`, **`me_serial`**)  
5. **Counters per meter** — `id=107` → `var_id` list and metadata  
6. **Last counter readings** — `id=8` → `value`, `timestamp` per `var_id` (water sensors)

Only water-like counters are exposed (by unit/name heuristics). If none match, all counters may be considered.

---

## Installation

### HACS (recommended)
1. HACS → **Integrations** → **Custom repositories** → add this repo (category: *Integration*).
2. Search for **“CEM Monitor (Unofficial)”** → Install.
3. **Restart Home Assistant**.

### Manual
1. Copy this repo to:  
   `<config>/custom_components/cem_monitor`
2. **Restart Home Assistant**.

---

## Configuration

1. Home Assistant → **Settings** → **Devices & Services** → **Add Integration** → **CEM Monitor (Unofficial)**.
2. Enter **username** and **password**.
3. The integration discovers your objects, meters, and water counters automatically.

**Multiple accounts** are supported; entity IDs include `<company_id>` to avoid collisions.

---

## Entity naming & IDs

- **Account device name**: `CEM Account <DISPLAY_NAME>`  
- **Account entities**:
  - `sensor.cem_account_<account_slug>_<company_id>_status`
  - `sensor.cem_account_<account_slug>_<company_id>_account`

- **Object device name**: `CEM Object <OBJECT_NAME>` (falls back to `CEM Object <mis_id>`)  
- **Water entity name**: `Water [<serial>|me<id>]`  
- **Water entity_id** pattern:  
  `sensor.cem_object_<object_slug>_water_[<serial_or_meid>]_var_<VAR_ID>`

---

## Privacy & API usage

- Credentials are stored by Home Assistant’s config entry system.
- Tokens are cached and refreshed when needed.
- The integration is **read-only** and uses a conservative polling cadence to limit API load.

---

## Troubleshooting

- **Names not updating**: Remove the device and re-add the integration, or reload the integration from Developer Tools → YAML.
- **Statistics unit warnings**: Sensors report **m³**. If you previously had `None`/different units, clear old statistics in Developer Tools → Statistics.
- **Missing serial in the name**: Some meters may not report `me_serial`. The sensor falls back to `me<id>`.

---

## Disclaimer

This is an **unofficial** community project. It is not endorsed by, directly connected to, or supported by CEM.  
Use at your own risk.

---

## License

MIT