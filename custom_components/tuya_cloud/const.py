"""Constants for the Tuya Cloud integration."""

DOMAIN = "tuya_cloud"

CONF_API_KEY = "api_key"

DEFAULT_SCAN_INTERVAL = 120

PREFIX_TO_BASE_URL: dict[str, str] = {
    "AY": "https://openapi.tuyacn.com",
    "AZ": "https://openapi.tuyaus.com",
    "EU": "https://openapi.tuyaeu.com",
    "IN": "https://openapi.tuyain.com",
    "UE": "https://openapi-ueaz.tuyaus.com",
    "WE": "https://openapi-weaz.tuyaeu.com",
    "SG": "https://openapi-sg.iotbing.com",
}

PREFIX_TO_WS_URI: dict[str, str] = {
    "AY": "wss://wsmsgs.tuyacn.com",
    "AZ": "wss://wsmsgs.iot-wus.com",
    "EU": "wss://wsmsgs.iot-eu.com",
    "IN": "wss://wsmsgs.iot-ap.com",
    "UE": "wss://wsmsgs.iot-eus.com",
    "WE": "wss://wsmsgs.iot-weu.com",
    "SG": "wss://wsmsgs.iot-sea.com",
}

LIGHT_CATEGORIES = {"dj", "dd", "fwl", "xdd", "dc", "fsd", "jsq", "tgq"}
SWITCH_CATEGORIES = {"cz", "pc", "kg", "tdq", "bh", "cwysj"}
CLIMATE_CATEGORIES = {"kt", "wk", "wkf"}
COVER_CATEGORIES = {"cl", "clkg"}
SENSOR_CATEGORIES = {"wsdcg", "mcs", "ywbj", "rqbj", "pir", "ldcg", "pm2.5"}

PLATFORMS: list[str] = ["light", "switch", "climate", "sensor", "cover"]
