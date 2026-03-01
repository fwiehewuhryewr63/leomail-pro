"""
Leomail v4 — Proxy Provider API Clients
Supports: ASocks, Proxy6, Belurk, IPRoyal
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
# Proxy6.net — IPv4/IPv6 proxies (datacenter, but user confirmed they work)
# API: https://px6.link/api/{key}/
# ═══════════════════════════════════════════════════════════════════════════════

class Proxy6Provider(ProxyProviderBase):
    """Proxy6.net — IPv4/IPv6 proxies with full buy/list/prolong API."""
    name = "proxy6"
    BASE_URL = "https://px6.link/api"

    def _url(self, method: str) -> str:
        return f"{self.BASE_URL}/{self.api_key}/{method}"

    def get_balance(self) -> float:
        try:
            r = requests.get(self._url("getproxy"), timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "yes":
                return float(data.get("balance", 0))
            return -1
        except Exception as e:
            logger.error(f"[Proxy6] Balance error: {e}")
            return -1

    def list_proxies(self) -> list[dict]:
        """List all active proxies from Proxy6 account."""
        try:
            r = requests.get(self._url("getproxy"), timeout=15)
            r.raise_for_status()
            data = r.json()
            if data.get("status") != "yes":
                logger.warning(f"[Proxy6] API error: {data.get('error', 'unknown')}")
                return []

            proxies = []
            proxy_list = data.get("list", {})
            for pid, p in proxy_list.items():
                if str(p.get("active")) != "1":
                    continue
                proxies.append({
                    "host": p.get("host", ""),
                    "port": int(p.get("port", 0)),
                    "username": p.get("user", ""),
                    "password": p.get("pass", ""),
                    "protocol": "socks5" if p.get("type") == "socks" else "http",
                    "geo": (p.get("country", "") or "").upper(),
                    "expires_at": p.get("date_end"),
                    "proxy_type": "residential",
                    "external_id": str(p.get("id", pid)),
                })
            return proxies
        except Exception as e:
            logger.error(f"[Proxy6] List proxies error: {e}")
            return []

    def buy_proxies(self, count: int, country: str = "ru", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """Buy IPv4 proxies from Proxy6."""
        try:
            r = requests.get(
                self._url("buy"),
                params={
                    "count": count,
                    "period": period_days,
                    "country": country.lower(),
                    "version": 4,  # IPv4
                    "type": "http",
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("status") != "yes":
                logger.error(f"[Proxy6] Buy error: {data.get('error', 'unknown')}")
                return []

            proxies = []
            for pid, p in data.get("list", {}).items():
                proxies.append({
                    "host": p.get("host", ""),
                    "port": int(p.get("port", 0)),
                    "username": p.get("user", ""),
                    "password": p.get("pass", ""),
                    "protocol": "socks5" if p.get("type") == "socks" else "http",
                    "geo": country.upper(),
                    "expires_at": p.get("date_end"),
                    "proxy_type": "residential",
                    "external_id": str(p.get("id", pid)),
                })
            logger.info(f"[Proxy6] Bought {len(proxies)} proxies for {data.get('price')} {data.get('currency', 'RUB')}")
            return proxies
        except Exception as e:
            logger.error(f"[Proxy6] Buy error: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════════
# Belurk.ru — IPv4/IPv6 proxies
# API: https://belurk.com/api/v1/
# ═══════════════════════════════════════════════════════════════════════════════

class BelurkProvider(ProxyProviderBase):
    """Belurk.ru — IPv4/IPv6 proxies with order-based API."""
    name = "belurk"
    BASE_URL = "https://belurk.com/api/v1"

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def get_balance(self) -> float:
        try:
            r = requests.get(
                f"{self.BASE_URL}/balance",
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return float(data.get("balance", data.get("amount", 0)))
        except Exception as e:
            logger.error(f"[Belurk] Balance error: {e}")
            return -1

    def list_proxies(self) -> list[dict]:
        """List active proxies from Belurk orders."""
        try:
            r = requests.get(
                f"{self.BASE_URL}/orders",
                headers=self._headers(),
                params={"status": "active"},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            orders = data if isinstance(data, list) else data.get("data", data.get("orders", []))

            proxies = []
            for order in orders:
                order_proxies = order.get("proxies", order.get("list", []))
                if isinstance(order_proxies, dict):
                    order_proxies = list(order_proxies.values())
                for p in order_proxies:
                    if isinstance(p, str):
                        # Format: host:port:user:pass or host:port
                        parts = p.strip().split(":")
                        if len(parts) >= 2:
                            proxies.append({
                                "host": parts[0],
                                "port": int(parts[1]),
                                "username": parts[2] if len(parts) > 2 else "",
                                "password": parts[3] if len(parts) > 3 else "",
                                "protocol": "http",
                                "geo": "", 
                                "expires_at": order.get("expires_at", order.get("date_end")),
                                "proxy_type": "residential",
                                "external_id": str(order.get("id", "")),
                            })
                    elif isinstance(p, dict):
                        proxies.append({
                            "host": p.get("ip", p.get("host", "")),
                            "port": int(p.get("port", 0)),
                            "username": p.get("login", p.get("user", p.get("username", ""))),
                            "password": p.get("password", p.get("pass", "")),
                            "protocol": p.get("type", "http").lower().replace("https", "http"),
                            "geo": (p.get("country", "") or "").upper(),
                            "expires_at": p.get("date_end", order.get("expires_at")),
                            "proxy_type": "residential",
                            "external_id": str(p.get("id", "")),
                        })
            return proxies
        except Exception as e:
            logger.error(f"[Belurk] List proxies error: {e}")
            return []

    def buy_proxies(self, count: int, country: str = "ru", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """Buy proxies via Belurk order API."""
        try:
            # First get available products
            r = requests.get(
                f"{self.BASE_URL}/products",
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            products = r.json()
            prod_list = products if isinstance(products, list) else products.get("data", [])

            # Find IPv4 product
            product_id = None
            for prod in prod_list:
                if "ipv4" in str(prod.get("name", "")).lower() or prod.get("type") == "ipv4":
                    product_id = prod.get("id")
                    break
            if not product_id and prod_list:
                product_id = prod_list[0].get("id")

            if not product_id:
                logger.error("[Belurk] No products available")
                return []

            # Create order
            r = requests.post(
                f"{self.BASE_URL}/orders",
                headers=self._headers(),
                json={"product_id": product_id, "quantity": count},
                timeout=20,
            )
            r.raise_for_status()
            order = r.json()
            order_data = order.get("data", order)

            # Extract proxies from order
            return self._parse_order_proxies(order_data)
        except Exception as e:
            logger.error(f"[Belurk] Buy error: {e}")
            return []

    def _parse_order_proxies(self, order: dict) -> list[dict]:
        """Parse proxy list from an order response."""
        proxy_list = order.get("proxies", order.get("list", []))
        if isinstance(proxy_list, dict):
            proxy_list = list(proxy_list.values())
        proxies = []
        for p in proxy_list:
            if isinstance(p, dict):
                proxies.append({
                    "host": p.get("ip", p.get("host", "")),
                    "port": int(p.get("port", 0)),
                    "username": p.get("login", p.get("user", "")),
                    "password": p.get("password", p.get("pass", "")),
                    "protocol": "http",
                    "geo": (p.get("country", "") or "").upper(),
                    "expires_at": p.get("date_end"),
                    "proxy_type": "residential",
                    "external_id": str(p.get("id", "")),
                })
        return proxies


# ═══════════════════════════════════════════════════════════════════════════════
# Factory + Tiered Auto-Buy
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "asocks": ASocksProvider,
    "proxy6": Proxy6Provider,
    "belurk": BelurkProvider,
    "iproyal": IPRoyalProvider,
}

# Tiered auto-buy order:
# Gmail → ASocks (mobile)
# Everything else → tier 1 (Proxy6, Belurk) → tier 2 (IPRoyal, Webshare)
AUTO_BUY_TIERS = {
    "gmail": [("asocks", "mobile")],
    "default": [
        ("proxy6", "residential"),
        ("belurk", "residential"),
        ("iproyal", "residential"),
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
      Gmail → ASocks (mobile 4G)
      Others → Proxy6 + Belurk (tier 1) → IPRoyal + Webshare (tier 2)
    
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
            logger.debug(f"[AutoBuy] Skipping {svc_name} — no API key")
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

