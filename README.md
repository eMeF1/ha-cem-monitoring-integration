[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
![Version](https://img.shields.io/github/v/release/eMeF1/ha-cem-monitoring-integration)
![Downloads](https://img.shields.io/github/downloads/eMeF1/ha-cem-monitoring-integration/total)
![License](https://img.shields.io/github/license/eMeF1/ha-cem-monitoring-integration)



# CEM Monitoring Integration — Home Assistant

A custom Home Assistant integration that retrieves **CEM account data, objects (places), meters, and water readings**. This project is community‑maintained and **not affiliated with CEM or Softlink**.

---

## Features
- Login to CEM API
- Fetch account information
- Discover objects (`mis_id`)
- Discover meters (`me_id`, including serial numbers)
- Expose water counters (`var_id`) as `m³` sensors
- Automatic device structure for account and objects

---

## Devices & Entities

### **CEM Account <DISPLAY_NAME>**
- **Account** (`sensor.cem_account_<slug>_<company_id>_account`)
  - Attributes: `company_id`, `customer_id`, `person_id`, `company_name`, `display_name`, `login_valid_from`, `login_valid_to`
- **Status** (`sensor.cem_account_<slug>_<company_id>_status`)
  - Attributes: `token_expires_at_iso`, `cookie_present`, `company_id`

### **CEM Object <OBJECT_NAME>**
One device per `mis_id`.
- **Water [<serial>|me<id>]** (`sensor.cem_object_<slug>_water_[<label>]_var_<var_id>`)  
  - Device class: `water`
  - Unit: `m³`
  - Auto‑converted from liters
  - Includes meter serial number when available

Example structure:
```
CEM Account <DISPLAY_NAME>
 ├─ sensor.cem_account_<slug>_<company_id>_status
 └─ sensor.cem_account_<slug>_<company_id>_account
CEM Object <OBJECT_NAME>
 ├─ sensor.cem_object_<slug>_water_[sn]_var_12345
 └─ sensor.cem_object_<slug>_water_[sn]_var_67890
```

---

## API Usage
This integration performs the following CEM API requests:
1. **id=4** – Login
2. **id=9** – User info
3. **id=23** – Objects list
4. **id=108** – Meters (serials, mappings)
5. **id=107** – Counters per meter
6. **id=8** – Last counter values

Read‑only. Minimal API load.

---

## Installation

### Via HACS (recommended)
1. HACS → *Integrations* → *Custom repositories*
2. Add repository URL (category: *Integration*)
3. Install **CEM Monitoring Integration**
4. Restart Home Assistant

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eMeF1&repository=ha-cem-monitoring-integration)

### Manual
Copy folder:
```
<config>/custom_components/cem_monitor
```
Restart Home Assistant.

---

## Configuration
1. Home Assistant → *Settings → Devices & Services → Add Integration*
2. Search for **CEM Monitoring Integration**
3. Login with your CEM credentials

Multiple accounts are supported.

---

## Troubleshooting
- **Names not updating** → Delete device + reload integration
- **Statistics warnings** → Clear old statistics after changing units
- **Missing serial numbers** → Not all CEM meters provide `me_serial`

---

## Privacy
- Credentials stored securely by Home Assistant
- Only read‑only API calls are used
- No data is transmitted to third parties

---

## Disclaimer
This is an **unofficial** Home Assistant integration. Use at your own risk.

---

## License
MIT