"""Constants for the Samsung DMS (legacy firmware) integration."""

from __future__ import annotations

DOMAIN = "samsung_dms_legacy"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CONTROL_ENABLED = "control_enabled"
CONF_PROTECTED_ADDRESSES = "protected_addresses"

DEFAULT_USERNAME = "admin"
DEFAULT_SCAN_INTERVAL = 30  # seconds
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 300

# Sentinel the panel uses for "no value".
INVALID_TEMP = -1000.0

# Map DMS opMode string -> HA HVACMode string (lowercase, matches HVACMode values)
OPMODE_TO_HVAC = {
    "auto": "auto",
    "heat": "heat",
    "cool": "cool",
    "dry": "dry",
    "fan": "fan_only",
    "fanonly": "fan_only",
}
# Reverse, for control (DMS expects these in <operationMode>)
HVAC_TO_OPMODE = {
    "auto": "auto",
    "heat": "heat",
    "cool": "cool",
    "dry": "dry",
    "fan_only": "fan",
}

# Fan speed mapping (DMS <fanSpeed> values)
FAN_MODES = ["auto", "low", "mid", "high"]
