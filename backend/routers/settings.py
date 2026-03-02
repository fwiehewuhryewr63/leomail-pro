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
    # Proxy providers
    asocks_key: Optional[str] = None
    proxy6_key: Optional[str] = None
    belurk_key: Optional[str] = None
    iproyal_key: Optional[str] = None
    proxycheap_key: Optional[str] = None
    auto_buy_enabled: Optional[bool] = None
    auto_buy_max_spend: Optional[float] = None
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
        # Proxy providers
        "proxy_providers": {
            "asocks": {
                "api_key": mask_key(config.get("proxy_providers", {}).get("asocks", {}).get("api_key", "")),
                "enabled": config.get("proxy_providers", {}).get("asocks", {}).get("enabled", True)
            },
            "proxy6": {
                "api_key": mask_key(config.get("proxy_providers", {}).get("proxy6", {}).get("api_key", "")),
                "enabled": config.get("proxy_providers", {}).get("proxy6", {}).get("enabled", True)
            },
            "belurk": {
                "api_key": mask_key(config.get("proxy_providers", {}).get("belurk", {}).get("api_key", "")),
            },
            "iproyal": {
                "api_key": mask_key(config.get("proxy_providers", {}).get("iproyal", {}).get("api_key", "")),
            },
            "proxycheap": {
                "api_key": mask_key(config.get("proxy_providers", {}).get("proxycheap", {}).get("api_key", "")),
            }
        },
        "auto_buy": config.get("auto_buy", {"enabled": False, "max_spend_usd": 10.0}),
        # Proxy limits - read from config, fallback to ProxyManager defaults
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
    # Proxy providers
    if update.asocks_key is not None:
        config.setdefault("proxy_providers", {}).setdefault("asocks", {})["api_key"] = update.asocks_key
    if update.proxy6_key is not None:
        config.setdefault("proxy_providers", {}).setdefault("proxy6", {})["api_key"] = update.proxy6_key
    if update.belurk_key is not None:
        config.setdefault("proxy_providers", {}).setdefault("belurk", {})["api_key"] = update.belurk_key
    if update.iproyal_key is not None:
        config.setdefault("proxy_providers", {}).setdefault("iproyal", {})["api_key"] = update.iproyal_key
    if update.proxycheap_key is not None:
        config.setdefault("proxy_providers", {}).setdefault("proxycheap", {})["api_key"] = update.proxycheap_key
    if update.auto_buy_enabled is not None:
        config.setdefault("auto_buy", {})["enabled"] = update.auto_buy_enabled
    if update.auto_buy_max_spend is not None:
        config.setdefault("auto_buy", {})["max_spend_usd"] = max(1.0, update.auto_buy_max_spend)
    if update.headless is not None:
        config.setdefault("browser", {})["headless"] = update.headless
    if update.threads is not None:
        config.setdefault("browser", {})["threads"] = update.threads
    
    # Proxy limits - save to config AND update ProxyManager class constants
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
                return {"status": "error", "message": "Invalid SimSMS API key"}
            return {"status": "ok", "message": f"Connected! Balance: {balance} RUB"}
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
                return {"status": "error", "message": "Invalid 5sim API key or zero balance"}
            return {"status": "ok", "message": f"Connected! Balance: {balance} RUB"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    elif service == "proxycheap":
        try:
            from ..services.proxy_providers import get_proxy_provider
            provider = get_proxy_provider(service)
            if not provider:
                return {"status": "error", "message": f"No API key for {service}"}
            result = provider.get_balance()
            if result > 0:
                return {"status": "ok", "message": "Proxy connection OK! ✅"}
            return {"status": "error", "message": "API auth failed - check key format (apiKey:apiSecret from dashboard)"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    elif service in ("asocks", "proxy6", "belurk", "iproyal"):
        try:
            from ..services.proxy_providers import get_proxy_provider
            provider = get_proxy_provider(service)
            if not provider:
                return {"status": "error", "message": f"No API key for {service}"}
            balance = provider.get_balance()
            if balance < 0:
                return {"status": "error", "message": f"Invalid API key or connection error"}
            return {"status": "ok", "message": f"Connected! Balance: {balance:.2f} $"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    return {"status": "error", "message": "Unknown service"}


@router.post("/proxy-sync/{provider}")
async def sync_proxies(provider: str):
    """Sync proxies from a provider API into the database."""
    from ..services.proxy_providers import get_proxy_provider
    from ..database import SessionLocal
    from ..models import Proxy, ProxyStatus
    from datetime import datetime

    pp = get_proxy_provider(provider)
    if not pp:
        return {"status": "error", "message": f"No API key configured for {provider}"}

    try:
        proxy_list = pp.list_proxies()
        if not proxy_list:
            return {"status": "error", "message": "No proxies returned from provider"}

        db = SessionLocal()
        added = 0
        skipped = 0
        try:
            for p in proxy_list:
                host = p.get("host", "")
                port = p.get("port", 0)
                if not host or not port:
                    skipped += 1
                    continue

                # Dedup by host:port
                existing = db.query(Proxy).filter(
                    Proxy.host == host, Proxy.port == port
                ).first()
                if existing:
                    skipped += 1
                    continue

                # Parse expires_at
                exp = p.get("expires_at")
                expires_at = None
                if exp:
                    try:
                        expires_at = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                proxy = Proxy(
                    host=host,
                    port=port,
                    username=p.get("username", "") or "",
                    password=p.get("password", "") or "",
                    protocol=p.get("protocol", "http"),
                    proxy_type=p.get("proxy_type", "residential"),
                    status=ProxyStatus.ACTIVE,
                    geo=p.get("geo", "") or "",
                    source=provider,
                    external_id=p.get("external_id", "") or "",
                    expires_at=expires_at,
                )
                db.add(proxy)
                added += 1

            db.commit()
        finally:
            db.close()

        return {
            "status": "ok",
            "message": f"Synced! Added: {added}, Skipped (duplicates): {skipped}",
            "added": added,
            "skipped": skipped,
        }
    except Exception as e:
        logger.error(f"[ProxySync] Error syncing {provider}: {e}")
        return {"status": "error", "message": str(e)}
