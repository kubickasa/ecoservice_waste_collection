from __future__ import annotations

from datetime import timedelta

DOMAIN = "ecoservice_waste_collection"
NAME = "Waste Collection Ecoservice Lithuania"
VERSION = "1.0.1"
REPORT_URL = "https://app.powerbi.com/view?r=eyJrIjoiNjY4OWNlMDYtODVmNC00YzIzLWJhZjAtMzE4YzA4N2ZkNDg2IiwidCI6IjNjNmM1MmUyLTkwMzUtNGZmMy1hNmFjLTc2YmQ0ZTY2NzNiMiIsImMiOjl9"
SOURCE_URL = "https://ecoservice.lt/grafikai/"
UPDATE_INTERVAL = timedelta(hours=24)
CONF_MUNICIPALITY = "municipality"
CONF_ADDRESS = "address"
CONF_CONTAINERS = "containers"
CONF_VASA_ENABLED = "vasa_enabled"
CONF_VASA_USERNAME = "vasa_username"
CONF_VASA_PASSWORD = "vasa_password"
VASA_BASE_URL = "https://savitarna.vasa.lt"
VASA_API_URL = "https://SavitarnaAPI.vasa.lt"
VASA_HISTORY_LIMIT = 100
PLATFORMS = ["binary_sensor", "calendar", "sensor"]
