from __future__ import annotations
from homeassistant.const import Platform

DOMAIN = "cem_monitor"

# Endpoints
AUTH_URL = "https://cemapi.unimonitor.eu/api?id=4"
USERINFO_URL = "https://cemapi.unimonitor.eu/api?id=9"     # user/company meta
OBJECTS_URL = "https://cemapi.unimonitor.eu/api?id=23"     # list of objects -> mis_id[]
METERS_URL = "https://cemapi.unimonitor.eu/api?id=108"     # list of meters -> me_id (optionally by mis)
COUNTERS_BY_METER_URL = "https://cemapi.unimonitor.eu/api?id=107"  # counters by meter -> var_id (requires me_id)
COUNTERS_BY_OBJECT_URL = "https://cemapi.unimonitor.eu/api?id=45"  # counters by object -> var_id (requires mis_id)
COUNTER_LAST_URL = "https://cemapi.unimonitor.eu/api?id=8"   # last reading per var_id
COUNTER_VALUE_TYPES_URL = "https://cemapi.unimonitor.eu/api?id=11"  # counter value types (cis parameter)

# Update cadence defaults
DEFAULT_UPDATE_INTERVAL_SECONDS = 1800  # auth: fallback scheduling (will be adjusted to expiry)

# Config keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"

# Optional legacy options (CSV allow-list)
CONF_VAR_ID = "var_id"
CONF_VAR_IDS = "var_ids"
CONF_VAR_IDS_CSV = "var_ids_csv"

# Counter update interval configuration
CONF_COUNTER_UPDATE_INTERVAL_MINUTES = "counter_update_interval_minutes"
DEFAULT_COUNTER_UPDATE_INTERVAL_MINUTES = 30  # Default: 30 minutes
MIN_COUNTER_UPDATE_INTERVAL_MINUTES = 1  # Minimum: 1 minute
MAX_COUNTER_UPDATE_INTERVAL_MINUTES = 1440  # Maximum: 24 hours

# Diagnostic attrs
ATTR_TOKEN_EXPIRES_AT = "token_expires_at"
ATTR_TOKEN_EXPIRES_IN = "token_expires_in_sec"
ATTR_COOKIE_PRESENT = "cookie_present"

PLATFORMS: list[Platform] = [Platform.SENSOR]