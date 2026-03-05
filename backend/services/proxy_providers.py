"""
Leomail v4 - Proxy Provider API Clients
Supports: ASocks, Proxy-Cheap
Each provider: fetch balance, list active proxies, buy new proxies.
"""
import requests
import random
from typing import Optional
from loguru import logger
from ..config import get_api_key


# ═══════════════════════════════════════════════════════════════════════════════
# Base class
# ═══════════════════════════════════════════════════════════════════════════════

class ProxyProviderBase:
    """Base proxy provider with common interface."""
    name: str = "base"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def get_balance(self) -> float:
        """Get account balance. Returns -1 on error."""
        raise NotImplementedError

    def list_proxies(self) -> list[dict]:
        """
        List active proxies from provider account.
        Returns list of dicts: {host, port, username, password, protocol, geo, expires_at, proxy_type}
        """
        raise NotImplementedError

    def buy_proxies(self, count: int, country: str = "us", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """
        Buy N proxies. Returns list of dicts same format as list_proxies.
        Returns empty list if purchase failed.
        """
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════════
# ASocks - mobile + residential proxies
# API: https://api.asocks.com/v2/
# ═══════════════════════════════════════════════════════════════════════════════

class ASocksProvider(ProxyProviderBase):
    """ASocks.com - mobile & residential proxies, pay-per-GB."""
    name = "asocks"
    BASE_URL = "https://api.asocks.com/v2"

    def get_balance(self) -> float:
        try:
            r = requests.get(
                f"{self.BASE_URL}/user/balance",
                params={"apiKey": self.api_key},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return float(data.get("balance", 0))
        except Exception as e:
            logger.error(f"[ASocks] Balance error: {e}")
            return -1

    def list_proxies(self) -> list[dict]:
        """List active proxy ports from ASocks account."""
        try:
            r = requests.get(
                f"{self.BASE_URL}/proxy/port-list",
                params={"apiKey": self.api_key},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            ports = data if isinstance(data, list) else data.get("data", data.get("ports", []))

            proxies = []
            for p in ports:
                proxies.append({
                    "host": p.get("host", p.get("ip", "")),
                    "port": int(p.get("port", 0)),
                    "username": p.get("login", p.get("username", "")),
                    "password": p.get("password", ""),
                    "protocol": p.get("type", "http").lower(),
                    "geo": p.get("country", "").upper(),
                    "expires_at": p.get("expiresAt", p.get("expires_at", None)),
                    "proxy_type": "mobile" if "mobile" in str(p.get("networkType", "")).lower()
                                  else "residential",
                    "external_id": str(p.get("id", "")),
                })
            return proxies
        except Exception as e:
            logger.error(f"[ASocks] List proxies error: {e}")
            return []

    def buy_proxies(self, count: int, country: str = "us", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """ASocks is pay-per-GB, no explicit buy. Create ports instead."""
        # ASocks API v2 field mapping:
        #   proxy_type_id: 1=residential, 3=mobile
        #   type_id: 1=http, 2=socks5
        proxy_type_id = 3 if proxy_type == "mobile" else 1  # residential
        type_id = 2 if proxy_type == "mobile" else 1  # socks5 for mobile, http for residential
        try:
            results = []
            for _ in range(count):
                r = requests.post(
                    f"{self.BASE_URL}/proxy/create-port",
                    params={"apiKey": self.api_key},
                    json={
                        "country_code": country.upper(),
                        "proxy_type_id": proxy_type_id,
                        "type_id": type_id,
                    },
                    timeout=15,
                )
                r.raise_for_status()
                data = r.json()
                if data and data.get("success"):
                    port_data = data.get("data", data) if isinstance(data, dict) else data
                    if isinstance(port_data, dict):
                        results.append({
                            "host": port_data.get("server", port_data.get("host", port_data.get("ip", ""))),
                            "port": int(port_data.get("port", 0)),
                            "username": port_data.get("login", port_data.get("username", "")),
                            "password": port_data.get("password", ""),
                            "protocol": "socks5" if type_id == 2 else "http",
                            "geo": country.upper(),
                            "expires_at": None,
                            "proxy_type": proxy_type,
                            "external_id": str(port_data.get("id", "")),
                        })
                        logger.info(f"[ASocks] Created port: {port_data.get('server')}:{port_data.get('port')}")
            return results
        except Exception as e:
            logger.error(f"[ASocks] Buy proxies error: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════════
# Proxy-Cheap - Residential proxies (Tier 4, ~$3.49/GB)
# API docs: https://docs.proxy-cheap.com
# Auth: X-Api-Key + X-Api-Secret headers (from app.proxy-cheap.com/api-keys)
# API base: https://api.proxy-cheap.com
# Services: rotating-residential, rotating-mobile, static-residential-ipv4
# No identity verification required
# ═══════════════════════════════════════════════════════════════════════════════

class ProxyCheapProvider(ProxyProviderBase):
    """
    Proxy-Cheap - 6M+ residential IPs, HTTP+SOCKS5.
    
    API key format: apiKey:apiSecret
    (from app.proxy-cheap.com → API Keys section)
    
    Uses REST API for ordering; proxy credentials come from purchased orders.
    """
    name = "proxycheap"
    BASE_URL = "https://api.proxy-cheap.com"

    def _parse_keys(self):
        """Parse stored 'apiKey:apiSecret' into two values."""
        if ":" in self.api_key:
            parts = self.api_key.split(":", 1)
            return parts[0].strip(), parts[1].strip()
        return self.api_key.strip(), self.api_key.strip()

    def _headers(self):
        api_key, api_secret = self._parse_keys()
        return {
            "X-Api-Key": api_key,
            "X-Api-Secret": api_secret,
            "Content-Type": "application/json",
        }

    def get_balance(self) -> float:
        """
        Validate API keys by hitting /v2/order (services list).
        Returns 1.0 if keys work, -1 if not.
        """
        try:
            r = requests.get(
                f"{self.BASE_URL}/v2/order",
                headers=self._headers(),
                timeout=15,
            )
            if r.status_code == 401 or r.status_code == 403:
                logger.error(f"[ProxyCheap] Auth failed: {r.status_code}")
                return -1
            if r.ok:
                data = r.json()
                logger.info(f"[ProxyCheap] API connection OK, services: {len(data) if isinstance(data, list) else 'N/A'}")
                return 1.0
            logger.error(f"[ProxyCheap] API error: {r.status_code} {r.text[:200]}")
            return -1
        except Exception as e:
            logger.error(f"[ProxyCheap] Connection error: {e}")
            return -1

    def get_services(self) -> list[dict]:
        """Get available services & plans from /v2/order."""
        try:
            r = requests.get(
                f"{self.BASE_URL}/v2/order",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json() if isinstance(r.json(), list) else [r.json()]
        except Exception as e:
            logger.error(f"[ProxyCheap] Services error: {e}")
            return []

    def get_setup(self, service_id: str, plan_id: str = None) -> dict:
        """Get available configuration (countries, ISPs) for a service."""
        try:
            params = {}
            if plan_id:
                params["planId"] = plan_id
            r = requests.get(
                f"{self.BASE_URL}/v2/order/{service_id}",
                headers=self._headers(),
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"[ProxyCheap] Setup error for {service_id}: {e}")
            return {}

    def get_order_proxies(self, order_id: str) -> list[dict]:
        """Get proxy credentials for a completed order."""
        try:
            r = requests.get(
                f"{self.BASE_URL}/orders/{order_id}/proxies",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            proxies = []
            entries = data if isinstance(data, list) else data.get("data", data.get("proxies", []))
            for entry in entries:
                if isinstance(entry, dict):
                    proxies.append({
                        "host": entry.get("host", entry.get("ip", "")),
                        "port": int(entry.get("port", 0)),
                        "username": entry.get("username", entry.get("user", "")),
                        "password": entry.get("password", entry.get("pass", "")),
                        "protocol": entry.get("protocol", "http"),
                        "geo": entry.get("country", "").upper(),
                        "expires_at": entry.get("expiresAt", None),
                        "proxy_type": "residential",
                        "external_id": f"proxycheap_{entry.get('id', '')}",
                    })
            return proxies
        except Exception as e:
            logger.error(f"[ProxyCheap] Order proxies error: {e}")
            return []

    def list_proxies(self, country: str = None, count: int = 10,
                     protocol: str = "http", session_type: str = "sticky") -> list[dict]:
        """
        Try ordering rotating-residential proxies via API.
        If ordering fails, return empty (user needs to buy traffic on dashboard).
        """
        try:
            # Try to execute an order for rotating residential
            service_id = "rotating-residential"
            payload = {
                "serviceId": service_id,
                "traffic": 1,  # 1 GB minimum
            }
            if country:
                payload["country"] = country.upper()

            r = requests.post(
                f"{self.BASE_URL}/v2/order/{service_id}/execute",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )

            if r.ok:
                data = r.json()
                order_id = data.get("id", data.get("orderId"))
                if order_id:
                    return self.get_order_proxies(str(order_id))

            logger.warning(f"[ProxyCheap] Order failed: {r.status_code} {r.text[:200]}")
            return []
        except Exception as e:
            logger.error(f"[ProxyCheap] List proxies error: {e}")
            return []

    def buy_proxies(self, count: int, country: str = "us", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """
        Buy proxies via Proxy-Cheap API.
        For rotating-residential, purchases traffic (pay-per-GB).
        """
        # First validate API keys
        balance = self.get_balance()
        if balance < 0:
            logger.warning("[ProxyCheap] API validation failed, skipping")
            return []

        proxies = self.list_proxies(
            country=country,
            count=count,
            protocol="socks5" if proxy_type == "residential" else "http",
            session_type="sticky",
        )

        logger.info(f"[ProxyCheap] Got {len(proxies)} proxies for {country}")
        return proxies


# ═══════════════════════════════════════════════════════════════════════════════
# Factory + Tiered Auto-Buy
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "asocks": ASocksProvider,
    "proxycheap": ProxyCheapProvider,
}

# ── 2-Tier proxy chain ──
# Tier 1: Uploaded proxies (handled in proxy_manager, not here)
# Tier 2: ASocks (residential/mobile, pay-per-GB, ~$3-5/GB)
# Tier 3: Proxy-Cheap (residential backconnect, ~$3.49/GB, fallback)
#
# Gmail = validator only (no autoreg)
# All autoreg providers = residential: ASocks → Proxy-Cheap

AUTO_BUY_TIERS = {
    "outlook": [
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "hotmail": [
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "yahoo": [
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "aol": [
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "protonmail": [
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "default": [
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
}


def get_proxy_provider(name: str) -> Optional[ProxyProviderBase]:
    """Get a proxy provider instance by name. Returns None if no API key."""
    cls = PROVIDERS.get(name)
    if not cls:
        return None
    key = get_api_key(name)
    if not key:
        return None
    return cls(api_key=key)


def get_all_providers() -> list[ProxyProviderBase]:
    """Get all configured proxy providers (ones with API keys)."""
    result = []
    for name, cls in PROVIDERS.items():
        key = get_api_key(name)
        if key:
            result.append(cls(api_key=key))
    return result


def tiered_auto_buy(provider: str, count: int, country: str = "us") -> list[dict]:
    """
    Tiered auto-buy:
      All providers -> ASocks residential -> Proxy-Cheap residential
    
    Tries each provider in order until count proxies are acquired.
    """
    prov_lower = provider.lower()
    tiers = AUTO_BUY_TIERS.get(prov_lower, AUTO_BUY_TIERS["default"])

    all_bought = []
    remaining = count

    for svc_name, proxy_type in tiers:
        if remaining <= 0:
            break

        pp = get_proxy_provider(svc_name)
        if not pp:
            logger.debug(f"[AutoBuy] Skipping {svc_name} - no API key")
            continue

        logger.info(f"[AutoBuy] Trying {svc_name}: {remaining} × {proxy_type} for {provider}")
        bought = pp.buy_proxies(remaining, country, proxy_type=proxy_type)
        if bought:
            # Tag source
            for p in bought:
                p["source"] = svc_name
            all_bought.extend(bought)
            remaining -= len(bought)
            logger.info(f"[AutoBuy] Got {len(bought)} from {svc_name}, remaining: {remaining}")

    if not all_bought:
        logger.warning(f"[AutoBuy] Failed to buy any proxies for {provider}")

    return all_bought



