"""
Leomail v4 — Proxy Provider API Clients
Supports: ASocks, IPRoyal, Webshare
Each provider: fetch balance, list active proxies, buy new proxies.
"""
import requests
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
# ASocks — mobile + residential proxies
# API: https://api.asocks.com/v2/
# ═══════════════════════════════════════════════════════════════════════════════

class ASocksProvider(ProxyProviderBase):
    """ASocks.com — mobile & residential proxies, pay-per-GB."""
    name = "asocks"
    BASE_URL = "https://api.asocks.com/v2"

    def get_balance(self) -> float:
        try:
            r = requests.get(
                f"{self.BASE_URL}/balance",
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
                f"{self.BASE_URL}/proxy/ports",
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
        try:
            results = []
            for _ in range(count):
                r = requests.post(
                    f"{self.BASE_URL}/proxy/ports",
                    params={"apiKey": self.api_key},
                    json={
                        "country": country.upper(),
                        "type": "socks5" if proxy_type == "mobile" else "http",
                        "networkType": "mobile" if proxy_type == "mobile" else "residential",
                    },
                    timeout=15,
                )
                r.raise_for_status()
                data = r.json()
                if data:
                    port_data = data.get("data", data) if isinstance(data, dict) else data
                    if isinstance(port_data, dict):
                        results.append({
                            "host": port_data.get("host", port_data.get("ip", "")),
                            "port": int(port_data.get("port", 0)),
                            "username": port_data.get("login", port_data.get("username", "")),
                            "password": port_data.get("password", ""),
                            "protocol": port_data.get("type", "http"),
                            "geo": country.upper(),
                            "expires_at": None,
                            "proxy_type": proxy_type,
                            "external_id": str(port_data.get("id", "")),
                        })
            return results
        except Exception as e:
            logger.error(f"[ASocks] Buy proxies error: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════════
# Webshare — residential proxies
# API: https://proxy.webshare.io/api/v2/
# ═══════════════════════════════════════════════════════════════════════════════

class WebshareProvider(ProxyProviderBase):
    """Webshare.io — residential proxies with free tier."""
    name = "webshare"
    BASE_URL = "https://proxy.webshare.io/api/v2"

    def _headers(self):
        return {"Authorization": f"Token {self.api_key}"}

    def get_balance(self) -> float:
        try:
            r = requests.get(
                f"{self.BASE_URL}/subscription/",
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            # Webshare returns bandwidth info
            bw = data.get("bandwidth_remaining_gb", data.get("bandwidth", 0))
            return float(bw)
        except Exception as e:
            logger.error(f"[Webshare] Balance error: {e}")
            return -1

    def list_proxies(self) -> list[dict]:
        """Fetch all proxies from Webshare account (paginated)."""
        proxies = []
        page = 1
        try:
            while True:
                r = requests.get(
                    f"{self.BASE_URL}/proxy/list/",
                    headers=self._headers(),
                    params={"mode": "direct", "page": page, "page_size": 100},
                    timeout=15,
                )
                r.raise_for_status()
                data = r.json()
                results = data.get("results", [])
                if not results:
                    break

                for p in results:
                    proxies.append({
                        "host": p.get("proxy_address", ""),
                        "port": int(p.get("port", 0)),
                        "username": p.get("username", ""),
                        "password": p.get("password", ""),
                        "protocol": "http",
                        "geo": (p.get("country_code", "") or "").upper(),
                        "expires_at": None,
                        "proxy_type": "residential",
                        "external_id": str(p.get("id", "")),
                    })

                # Check if there's a next page
                if not data.get("next"):
                    break
                page += 1

            return proxies
        except Exception as e:
            logger.error(f"[Webshare] List proxies error: {e}")
            return []

    def buy_proxies(self, count: int, country: str = "us", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """Webshare is subscription-based. Use list_proxies instead."""
        logger.warning("[Webshare] Auto-buy not supported — subscription model. Use Sync.")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# IPRoyal — residential proxies
# API: https://resi-api.iproyal.com/v1/
# ═══════════════════════════════════════════════════════════════════════════════

class IPRoyalProvider(ProxyProviderBase):
    """IPRoyal — residential proxies with reseller API."""
    name = "iproyal"
    BASE_URL = "https://resi-api.iproyal.com/v1"

    def _headers(self):
        return {"X-Access-Token": self.api_key}

    def get_balance(self) -> float:
        try:
            r = requests.get(
                f"{self.BASE_URL}/access/traffic-balance",
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            # Returns traffic balance in bytes, convert to GB
            balance_bytes = float(data.get("traffic_remaining", data.get("balance", 0)))
            return round(balance_bytes / (1024 ** 3), 2)
        except Exception as e:
            logger.error(f"[IPRoyal] Balance error: {e}")
            return -1

    def list_proxies(self) -> list[dict]:
        """
        IPRoyal residential uses a gateway model (single endpoint, rotating IPs).
        Generate a proxy list with their API.
        """
        try:
            r = requests.post(
                f"{self.BASE_URL}/access/generate-proxy-list",
                headers=self._headers(),
                json={
                    "format": "{ip}:{port}:{username}:{password}",
                    "hostname": "geo.iproyal.com",
                    "port": 12321,
                    "rotation": "random",
                    "count": 20,
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()

            proxies = []
            proxy_lines = data if isinstance(data, list) else data.get("proxies", [])
            for line in proxy_lines:
                if isinstance(line, str):
                    parts = line.strip().split(":")
                    if len(parts) >= 4:
                        proxies.append({
                            "host": parts[0],
                            "port": int(parts[1]),
                            "username": parts[2],
                            "password": parts[3],
                            "protocol": "http",
                            "geo": "",
                            "expires_at": None,
                            "proxy_type": "residential",
                            "external_id": "",
                        })
                elif isinstance(line, dict):
                    proxies.append({
                        "host": line.get("ip", line.get("host", "")),
                        "port": int(line.get("port", 0)),
                        "username": line.get("username", ""),
                        "password": line.get("password", ""),
                        "protocol": "http",
                        "geo": (line.get("country", "") or "").upper(),
                        "expires_at": None,
                        "proxy_type": "residential",
                        "external_id": str(line.get("id", "")),
                    })
            return proxies
        except Exception as e:
            logger.error(f"[IPRoyal] List proxies error: {e}")
            return []

    def buy_proxies(self, count: int, country: str = "us", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """IPRoyal residential is pay-per-GB. Generate proxy list entries."""
        return self.list_proxies()


# ═══════════════════════════════════════════════════════════════════════════════
# Factory + helpers
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "asocks": ASocksProvider,
    "webshare": WebshareProvider,
    "iproyal": IPRoyalProvider,
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


def auto_buy_proxies(provider_name: str, count: int, country: str = "us",
                     proxy_type: str = "residential") -> list[dict]:
    """
    Auto-buy proxies from a specific provider.
    Called by ProxyManager when pool is exhausted.
    """
    provider = get_proxy_provider(provider_name)
    if not provider:
        logger.warning(f"[AutoBuy] No API key for {provider_name}")
        return []

    logger.info(f"[AutoBuy] Buying {count} {proxy_type} proxies from {provider_name}")
    return provider.buy_proxies(count, country, proxy_type=proxy_type)
