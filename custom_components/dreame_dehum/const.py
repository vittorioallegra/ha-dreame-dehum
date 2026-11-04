"""Constants for the Dreame Dehumidifier integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "dreame_dehum"
MANUFACTURER = "Dreame"

CONF_REGION = "region"
CONF_DID = "did"
CONF_MODEL = "model"
CONF_HOST = "host"
CONF_MAC = "mac"
CONF_SCAN_INTERVAL = "scan_interval"

REGIONS = ["eu", "us", "sg", "ru", "kr", "cn"]
DEFAULT_REGION = "eu"

DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 300

# Properties are read in small batches: large get_properties calls can time out.
READ_BATCH_SIZE = 8

# A property missing from this many polls in a row is shown as unavailable.
MAX_MISSED_POLLS = 2

# The cloud lags a few seconds behind writes; refresh after this delay.
POST_WRITE_REFRESH = timedelta(seconds=8)
