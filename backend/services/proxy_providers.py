"""
Leomail v4 - Proxy Provider API Clients
Supports: ASocks, Proxy6, Belurk, IPRoyal
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
        try:
            results = []
            for _ in range(count):
                r = requests.post(
                    f"{self.BASE_URL}/proxy/create-port",
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
# Proxy6.net - IPv4/IPv6 proxies (datacenter, but user confirmed they work)
# API: https://px6.link/api/{key}/
# ═══════════════════════════════════════════════════════════════════════════════

class Proxy6Provider(ProxyProviderBase):
    """Proxy6.net - IPv4/IPv6 proxies with full buy/list/prolong API."""
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
# Belurk.ru - IPv4/IPv6 proxies
# API docs: https://dev.belurk.ru/
# Auth: x-api-token header
# ═══════════════════════════════════════════════════════════════════════════════

class BelurkProvider(ProxyProviderBase):
    """Belurk.ru - IPv4/IPv6 proxies via dev.belurk.ru API."""
    name = "belurk"
    BASE_URL = "https://api.belurk.ru"

    def _headers(self):
        return {"x-api-token": self.api_key, "Content-Type": "application/json"}

    def get_balance(self) -> float:
        """GET /accounts/get-balance → {"data": {"balance": "123.45"}}"""
        try:
            r = requests.get(
                f"{self.BASE_URL}/accounts/get-balance",
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return float(data.get("data", {}).get("balance", 0))
        except Exception as e:
            logger.error(f"[Belurk] Balance error: {e}")
            return -1

    def list_proxies(self) -> list[dict]:
        """GET /proxy/get-all → {"data": {"items": {"ipv4": [...], "ipv6": [...]}}}"""
        try:
            r = requests.get(
                f"{self.BASE_URL}/proxy/get-all",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("data", {}).get("items", {})

            proxies = []
            # Iterate all proxy types: ipv4, ipv6, ipv4_shared
            for proxy_type, proxy_list in items.items():
                if not isinstance(proxy_list, list):
                    continue
                for p in proxy_list:
                    if p.get("is_expired"):
                        continue
                    ports = p.get("ports", {})
                    http_port = ports.get("http", 0)
                    socks_port = ports.get("socks", 0)
                    country = p.get("country", {})
                    geo = country.get("code", "") if isinstance(country, dict) else str(country)

                    proxies.append({
                        "host": p.get("ip_address", ""),
                        "port": int(http_port) if http_port else int(socks_port),
                        "username": p.get("login", ""),
                        "password": p.get("password", ""),
                        "protocol": "socks5" if not http_port and socks_port else "http",
                        "geo": geo.upper(),
                        "expires_at": p.get("expired_at"),
                        "proxy_type": proxy_type,
                        "external_id": str(p.get("credential_id", "")),
                    })
            return proxies
        except Exception as e:
            logger.error(f"[Belurk] List proxies error: {e}")
            return []

    def buy_proxies(self, count: int, country: str = "ru", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """
        1. GET /products/get-all → find matching product variant_id
        2. POST /orders/create {"product_id": variant_id, "quantity": count}
        """
        try:
            # Get available products
            r = requests.get(
                f"{self.BASE_URL}/products/get-all",
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            products = r.json().get("data", {})

            # Find IPv4 product with matching country
            variant_id = None
            country_upper = country.upper()
            # Prefer ipv4, then ipv4_shared, then ipv6
            for ptype in ("ipv4", "ipv4_shared", "ipv6"):
                cat = products.get(ptype, {})
                variants = cat.get("variants", [])
                for v in variants:
                    if v.get("country_code", "").upper() == country_upper:
                        variant_id = v.get("variant_id")
                        break
                if variant_id:
                    break

            # Fallback: first available ipv4 variant
            if not variant_id:
                for ptype in ("ipv4", "ipv4_shared"):
                    cat = products.get(ptype, {})
                    variants = cat.get("variants", [])
                    if variants:
                        variant_id = variants[0].get("variant_id")
                        break

            if not variant_id:
                logger.error("[Belurk] No products available")
                return []

            # Create order
            r = requests.post(
                f"{self.BASE_URL}/orders/create",
                headers=self._headers(),
                json={"product_id": variant_id, "quantity": count},
                timeout=20,
            )
            r.raise_for_status()
            order = r.json()
            order_id = order.get("data", {}).get("order_id")
            logger.info(f"[Belurk] Order created: {order_id}")

            # Fetch the new proxies
            return self.list_proxies()
        except Exception as e:
            logger.error(f"[Belurk] Buy error: {e}")
            return []

# ═══════════════════════════════════════════════════════════════════════════════
# Proxy-Cheap - Residential backconnect proxies (Tier 4, ~$3.49/GB)
# API: https://api.proxy-cheap.com
# Auth: X-Api-Key + X-Api-Secret headers
# Proxy format: backconnect (rp.proxy-cheap.com with user:pass auth)
# No identity verification required
# ═══════════════════════════════════════════════════════════════════════════════

class ProxyCheapProvider(ProxyProviderBase):
    """Proxy-Cheap - 6M+ residential IPs, HTTP+SOCKS5, backconnect gateway."""
    name = "proxycheap"
    BASE_URL = "https://api.proxy-cheap.com"

    # Backconnect gateway
    GATEWAY_HOST = "rp.proxy-cheap.com"
    GATEWAY_PORT_HTTP = 11223
    GATEWAY_PORT_SOCKS5 = 11224

    def _parse_keys(self):
        """Parse combined 'api_key:api_secret' from stored key."""
        if ":" in self.api_key:
            parts = self.api_key.split(":", 1)
            return parts[0].strip(), parts[1].strip()
        # If no separator, use same value for both
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
        Proxy-Cheap has no public balance API for regular users.
        Instead, test connectivity through the backconnect proxy.
        Returns 1.0 if proxy works, -1 if not.
        """
        try:
            # Build one test proxy
            test_proxies = self._build_backconnect_proxies(1, "us", "http", "rotating")
            if not test_proxies:
                return -1

            tp = test_proxies[0]
            proxy_url = f"http://{tp['username']}:{tp['password']}@{tp['host']}:{tp['port']}"

            r = requests.get(
                "https://httpbin.org/ip",
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=15,
            )
            if r.ok:
                ip = r.json().get("origin", "unknown")
                logger.info(f"[ProxyCheap] Proxy test OK, IP: {ip}")
                return 1.0  # Proxy works
            return -1
        except Exception as e:
            logger.error(f"[ProxyCheap] Connection test error: {e}")
            return -1

    def list_proxies(self, country: str = None, count: int = 10,
                     protocol: str = "http", session_type: str = "sticky") -> list[dict]:
        """
        Generate backconnect proxy entries.
        Proxy-Cheap uses backconnect: single gateway, auth via user:pass.
        Country targeting is embedded in the username.
        """
        return self._build_backconnect_proxies(count, country or "us", protocol, session_type)

    def _build_backconnect_proxies(self, count: int, country: str = "us",
                                    protocol: str = "http",
                                    session_type: str = "sticky") -> list[dict]:
        """
        Build backconnect proxy entries.
        Proxy-Cheap backconnect format:
          Host: rp.proxy-cheap.com
          Port: 11223 (HTTP) or 11224 (SOCKS5)
          Username: account_username-country-XX-session-RANDOM
          Password: account_password
        """
        import hashlib
        import time

        api_key, api_secret = self._parse_keys()
        port = self.GATEWAY_PORT_SOCKS5 if protocol == "socks5" else self.GATEWAY_PORT_HTTP
        proxies = []

        for i in range(count):
            session_id = hashlib.md5(f"{time.time()}_{i}_{random.random()}".encode()).hexdigest()[:10]

            # Username with targeting
            username_parts = [api_key, f"country-{country.lower()}"]
            if session_type == "sticky":
                username_parts.append(f"session-{session_id}")

            username = "-".join(username_parts)

            proxies.append({
                "host": self.GATEWAY_HOST,
                "port": port,
                "username": username,
                "password": api_secret,
                "protocol": protocol,
                "geo": country.upper(),
                "expires_at": None,
                "proxy_type": "residential",
                "external_id": f"proxycheap_bc_{session_id}",
            })

        logger.info(f"[ProxyCheap] Built {len(proxies)} backconnect proxies ({protocol}, {country}, {session_type})")
        return proxies

    def get_available_services(self) -> list[dict]:
        """Get list of available proxy services and their pricing."""
        try:
            r = requests.get(
                f"{self.BASE_URL}/services",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json() if isinstance(r.json(), list) else [r.json()]
        except Exception as e:
            logger.error(f"[ProxyCheap] Services error: {e}")
            return []

    def buy_proxies(self, count: int, country: str = "us", period_days: int = 7,
                    proxy_type: str = "residential") -> list[dict]:
        """
        Proxy-Cheap is pay-per-GB (backconnect).
        Returns backconnect proxies ready to use (traffic deducted on use).
        """
        balance = self.get_balance()
        logger.info(f"[ProxyCheap] Balance: ${balance}")

        if balance == 0:
            logger.warning("[ProxyCheap] Zero balance")
            return []

        protocol = "socks5" if proxy_type == "residential" else "http"

        proxies = self._build_backconnect_proxies(
            count=count,
            country=country,
            protocol=protocol,
            session_type="sticky",
        )

        logger.info(f"[ProxyCheap] Generated {len(proxies)} {proxy_type} proxies for {country}")
        return proxies


# ═══════════════════════════════════════════════════════════════════════════════
# Factory + Tiered Auto-Buy
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "asocks": ASocksProvider,
    "proxy6": Proxy6Provider,
    "belurk": BelurkProvider,
    "proxycheap": ProxyCheapProvider,
}

# ── 4-Tier proxy chain (cheapest → most expensive) ──
# Tier 1: Uploaded proxies (handled in proxy_manager, not here)
# Tier 2: Belurk + Proxy6 (cheap datacenter IPv4, ~$1-2/proxy/week)
# Tier 3: ASocks (residential/mobile, pay-per-GB, ~$3-5/GB)
# Tier 4: Proxy-Cheap (residential backconnect, ~$3.49/GB, last resort)
#
# Gmail = mobile ONLY → ASocks mobile, then uploaded mobile
# Yahoo/AOL = residential ONLY → skip datacenter tiers
# Outlook/Proton/Tuta = any → use cheapest first

AUTO_BUY_TIERS = {
    "gmail": [
        ("asocks", "mobile"),
    ],
    "yahoo": [
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "aol": [
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "outlook": [
        ("belurk", "residential"),
        ("proxy6", "residential"),
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "hotmail": [
        ("belurk", "residential"),
        ("proxy6", "residential"),
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "protonmail": [
        ("belurk", "residential"),
        ("proxy6", "residential"),
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "tuta": [
        ("belurk", "residential"),
        ("proxy6", "residential"),
        ("asocks", "residential"),
        ("proxycheap", "residential"),
    ],
    "default": [
        ("belurk", "residential"),
        ("proxy6", "residential"),
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
      Gmail -> ASocks (mobile 4G)
      Yahoo/AOL -> ASocks residential -> Proxy-Cheap (skip datacenter tiers)
      Desktop -> Belurk -> Proxy6 -> ASocks -> Proxy-Cheap
    
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



