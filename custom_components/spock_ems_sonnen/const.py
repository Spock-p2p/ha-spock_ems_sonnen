"""Constantes para la integración Spock EMS Sonnen."""

DOMAIN = "spock_ems_sonnen"

# --- API Spock ---
API_ENDPOINT = "https://ems-ha.spock.es/api/ems_sonnen"

# --- Constantes de Configuración ---
CONF_API_TOKEN = "api_token"
CONF_PLANT_ID = "plant_id"
CONF_SONNEN_IP = "sonnen_ip"
CONF_SONNEN_TOKEN = "sonnen_token"

# --- Plataformas ---
PLATFORMS: list[str] = ["switch", "sensor"]

# --- Defaults ---
DEFAULT_SCAN_INTERVAL_S = 60
