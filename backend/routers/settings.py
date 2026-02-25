from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from ..config import load_config, save_config, mask_key, get_api_key
from ..services.sms_provider import GrizzlySMS
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
    headless: Optional[bool] = None
    threads: Optional[int] = None

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
            }
        },

        "browser": config.get("browser", {}),
        "proxies_count": len(config.get("proxies", []))
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
    if update.headless is not None:
        config.setdefault("browser", {})["headless"] = update.headless
    if update.threads is not None:
        config.setdefault("browser", {})["threads"] = update.threads
    
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
        return {"status": "ok", "message": "Key configured (test on first solve)"}
    
    elif service == "twocaptcha":
        try:
            from ..services.captcha_provider import TwoCaptchaProvider
            tc = TwoCaptchaProvider(key)
            balance = tc.get_balance()
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
