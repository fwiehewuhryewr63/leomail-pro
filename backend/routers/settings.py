from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from ..config import load_config, save_config, mask_key, get_api_key
from ..services.sms_provider import GrizzlySMS
from ..services.proxy_manager import ProxyManager
from loguru import logger

router = APIRouter(prefix="/api/settings", tags=["settings"])

class ProxyConfig(BaseModel):
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "socks5"
    expires_days: int = 30

class SettingsUpdate(BaseModel):
    grizzly_key: Optional[str] = None
    simsms_key: Optional[str] = None
    fivesim_key: Optional[str] = None
    capguru_key: Optional[str] = None
    twocaptcha_key: Optional[str] = None
    capsolver_key: Optional[str] = None
    headless: Optional[bool] = None
    threads: Optional[int] = None
    # Proxy usage limits per provider group
    gmail_proxy_limit: Optional[int] = None
    yahoo_aol_proxy_limit: Optional[int] = None   # Yahoo+AOL combined
    outlook_hotmail_proxy_limit: Optional[int] = None  # Outlook+Hotmail combined
    protonmail_proxy_limit: Optional[int] = None
    tuta_proxy_limit: Optional[int] = None

@router.get("/")
async def get_settings():
    config = load_config()
    return {
        "sms": {
            "grizzly": {
                "api_key": mask_key(config.get("sms", {}).get("grizzly", {}).get("api_key", "")),
                "enabled": config.get("sms", {}).get("grizzly", {}).get("enabled", True)
            },
            "simsms": {
                "api_key": mask_key(config.get("sms", {}).get("simsms", {}).get("api_key", "")),
                "enabled": config.get("sms", {}).get("simsms", {}).get("enabled", True)
            },
            "5sim": {
                "api_key": mask_key(config.get("sms", {}).get("5sim", {}).get("api_key", "")),
                "enabled": config.get("sms", {}).get("5sim", {}).get("enabled", True)
            }
        },
        "captcha": {
            "capguru": {
                "api_key": mask_key(config.get("captcha", {}).get("capguru", {}).get("api_key", "")),
                "enabled": config.get("captcha", {}).get("capguru", {}).get("enabled", True)
            },
            "twocaptcha": {
                "api_key": mask_key(config.get("captcha", {}).get("twocaptcha", {}).get("api_key", "")),
                "enabled": config.get("captcha", {}).get("twocaptcha", {}).get("enabled", True)
            },
            "capsolver": {
                "api_key": mask_key(config.get("captcha", {}).get("capsolver", {}).get("api_key", "")),
                "enabled": config.get("captcha", {}).get("capsolver", {}).get("enabled", True)
            }
        },

        "browser": config.get("browser", {}),
        "proxies_count": len(config.get("proxies", [])),
        # Proxy limits — read from config, fallback to ProxyManager defaults
        "proxy_limits": {
            "gmail": config.get("proxy_limits", {}).get("gmail", ProxyManager.GMAIL_LIMIT),
            "yahoo_aol": config.get("proxy_limits", {}).get("yahoo_aol", ProxyManager.YA_LIMIT),
            "outlook_hotmail": config.get("proxy_limits", {}).get("outlook_hotmail", ProxyManager.OH_LIMIT),
            "protonmail": config.get("proxy_limits", {}).get("protonmail", ProxyManager.PT_LIMIT),
            "tuta": config.get("proxy_limits", {}).get("tuta", ProxyManager.TT_LIMIT),
        }
    }

@router.post("/")
async def update_settings(update: SettingsUpdate):
    config = load_config()
    
    if update.grizzly_key is not None:
        config.setdefault("sms", {}).setdefault("grizzly", {})["api_key"] = update.grizzly_key
    if update.simsms_key is not None:
        config.setdefault("sms", {}).setdefault("simsms", {})["api_key"] = update.simsms_key
    if update.fivesim_key is not None:
        config.setdefault("sms", {}).setdefault("5sim", {})["api_key"] = update.fivesim_key
    if update.capguru_key is not None:
        config.setdefault("captcha", {}).setdefault("capguru", {})["api_key"] = update.capguru_key
    if update.twocaptcha_key is not None:
        config.setdefault("captcha", {}).setdefault("twocaptcha", {})["api_key"] = update.twocaptcha_key
    if update.capsolver_key is not None:
        config.setdefault("captcha", {}).setdefault("capsolver", {})["api_key"] = update.capsolver_key
    if update.headless is not None:
        config.setdefault("browser", {})["headless"] = update.headless
    if update.threads is not None:
        config.setdefault("browser", {})["threads"] = update.threads
    
    # Proxy limits — save to config AND update ProxyManager class constants
    limits = config.setdefault("proxy_limits", {})
    if update.gmail_proxy_limit is not None:
        v = max(1, update.gmail_proxy_limit)
        limits["gmail"] = v
        ProxyManager.GMAIL_LIMIT = v
    if update.yahoo_aol_proxy_limit is not None:
        v = max(1, update.yahoo_aol_proxy_limit)
        limits["yahoo_aol"] = v
        ProxyManager.YA_LIMIT = v
    if update.outlook_hotmail_proxy_limit is not None:
        v = max(1, update.outlook_hotmail_proxy_limit)
        limits["outlook_hotmail"] = v
        ProxyManager.OH_LIMIT = v
    if update.protonmail_proxy_limit is not None:
        v = max(1, update.protonmail_proxy_limit)
        limits["protonmail"] = v
        ProxyManager.PT_LIMIT = v
    if update.tuta_proxy_limit is not None:
        v = max(1, update.tuta_proxy_limit)
        limits["tuta"] = v
        ProxyManager.TT_LIMIT = v
    
    save_config(config)
    return {"status": "saved"}

@router.post("/test/{service}")
async def test_service(service: str):
    key = get_api_key(service)
    if not key:
        return {"status": "error", "message": f"No API key configured for {service}"}
    
    if service == "grizzly":
        try:
            sms = GrizzlySMS(key)
            balance = sms.get_balance()
            return {"status": "ok", "message": f"Connected! Balance: {balance}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    elif service == "simsms":
        try:
            from ..services.simsms_provider import SimSmsProvider
            sms = SimSmsProvider(key)
            balance = sms.get_balance()
            if balance < 0:
                return {"status": "error", "message": "Неверный API ключ SimSMS"}
            return {"status": "ok", "message": f"Connected! Баланс: {balance}₽"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    elif service == "capguru":
        try:
            from ..services.captcha_provider import CaptchaProvider
            cp = CaptchaProvider(key)
            balance = cp.get_balance()
            return {"status": "ok", "message": f"Connected! Balance: ${balance:.2f}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    elif service == "twocaptcha":
        try:
            from ..services.captcha_provider import TwoCaptchaProvider
            tc = TwoCaptchaProvider(key)
            balance = tc.get_balance()
            return {"status": "ok", "message": f"Connected! Balance: ${balance:.2f}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    elif service == "capsolver":
        try:
            from ..services.captcha_provider import CapSolverProvider
            cs = CapSolverProvider(key)
            balance = cs.get_balance()
            return {"status": "ok", "message": f"Connected! Balance: ${balance:.2f}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    elif service == "5sim":
        try:
            from ..services.fivesim_provider import FiveSimProvider
            sms = FiveSimProvider(key)
            balance = sms.get_balance()
            if balance <= 0:
                return {"status": "error", "message": "Неверный API ключ 5sim или нулевой баланс"}
            return {"status": "ok", "message": f"Connected! Баланс: {balance}₽"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    return {"status": "error", "message": "Unknown service"}
