import json
import os
import sys
from pathlib import Path
from loguru import logger

# user_data/ must be next to the EXE (persistent), not inside _internal/
if getattr(sys, 'frozen', False):
    _ROOT = Path(sys.executable).parent
else:
    _ROOT = Path(__file__).parent.parent

CONFIG_DIR = _ROOT / "user_data"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "sms": {
        "default": "simsms",
        "simsms": {"api_key": "", "enabled": True},
        "grizzly": {"api_key": "", "enabled": False}
    },
    "captcha": {
        "capguru": {"api_key": "", "enabled": True},
        "twocaptcha": {"api_key": "", "enabled": True},
        "capsolver": {"api_key": "", "enabled": True}
    },

    "proxy_providers": {
        "asocks": {"api_key": "", "enabled": True},
        "proxy6": {"api_key": "", "enabled": True},
        "belurk": {"api_key": "", "enabled": True},
        "iproyal": {"api_key": "", "enabled": True}
    },
    "auto_buy": {
        "enabled": False,
        "max_spend_usd": 10.0,
        "mobile_provider": "asocks",
        "residential_provider": "iproyal"
    },

    "proxies": [],
    "browser": {
        "headless": False,
        "threads": 1
    },
    "warmup": {
        "schedule": {
            "day_1_3": {"min": 1, "max": 3},
            "day_4_7": {"min": 5, "max": 10},
            "day_8_14": {"min": 10, "max": 20},
            "day_15_21": {"min": 20, "max": 50},
            "day_22_30": {"min": 50, "max": 100}
        },
        "same_provider_days": 7,
        "human_delay_min_sec": 2,
        "human_delay_max_sec": 15,
        "pause_between_emails_min": 300,
        "pause_between_emails_max": 1800
    },
    "sending": {
        "per_day_min": 25,
        "per_day_max": 75,
        "delay_min_sec": 30,
        "delay_max_sec": 180,
        "schedule_start_hour": 8,
        "schedule_end_hour": 22,
        "start_jitter_min": 40
    },
    "proxy_monitor": {
        "check_interval_sec": 300,
        "max_fail_count": 3,
        "auto_replace": True
    }
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            # Deep merge with defaults for any missing keys
            merged = _deep_merge(DEFAULT_CONFIG, config)
            return merged
        except Exception as e:
            logger.error(f"Config load error: {e}")
    return _deep_copy(DEFAULT_CONFIG)


def _deep_merge(defaults: dict, override: dict) -> dict:
    """Merge override into defaults, preserving nested structure."""
    result = defaults.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _deep_copy(d: dict) -> dict:
    return json.loads(json.dumps(d))


def save_config(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("Config saved")


def get_api_key(service: str) -> str | None:
    config = load_config()
    if service == "grizzly":
        key = config.get("sms", {}).get("grizzly", {}).get("api_key", "")
        return key if key else None
    elif service == "simsms":
        key = config.get("sms", {}).get("simsms", {}).get("api_key", "")
        return key if key else None
    elif service == "capguru":
        key = config.get("captcha", {}).get("capguru", {}).get("api_key", "")
        return key if key else None
    elif service == "twocaptcha":
        key = config.get("captcha", {}).get("twocaptcha", {}).get("api_key", "")
        return key if key else None
    elif service == "capsolver":
        key = config.get("captcha", {}).get("capsolver", {}).get("api_key", "")
        return key if key else None
    elif service == "5sim":
        key = config.get("sms", {}).get("5sim", {}).get("api_key", "")
        return key if key else None
    elif service in ("asocks", "proxy6", "belurk", "iproyal"):
        key = config.get("proxy_providers", {}).get(service, {}).get("api_key", "")
        return key if key else None

    return None


def get_warmup_schedule() -> dict:
    config = load_config()
    return config.get("warmup", {}).get("schedule", DEFAULT_CONFIG["warmup"]["schedule"])


def get_warmup_config() -> dict:
    config = load_config()
    return config.get("warmup", DEFAULT_CONFIG["warmup"])


def get_sending_config() -> dict:
    config = load_config()
    return config.get("sending", DEFAULT_CONFIG["sending"])


def mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def init_directories():
    """Create all user_data subdirectories on startup."""
    dirs = [
        CONFIG_DIR,
        CONFIG_DIR / "databases",
        CONFIG_DIR / "templates",
        CONFIG_DIR / "farms",
        CONFIG_DIR / "profiles",
        CONFIG_DIR / "names",
        CONFIG_DIR / "logs",
        CONFIG_DIR / "logs" / "errors",
        CONFIG_DIR / "screenshots",
        CONFIG_DIR / "links",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    logger.info(f"Initialized {len(dirs)} directories in user_data/")
