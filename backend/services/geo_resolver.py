"""
Leomail v4 — GEO Resolver
IP-based geo detection, SMS country auto-priority, GEO consistency validation.
Ensures IP ↔ timezone ↔ language ↔ SMS country are all synchronized.
"""
import requests
from typing import Optional
from loguru import logger
from ..data.geo_data import get_country, COUNTRIES, get_simsms_country_code


# ── IP → Country detection ─────────────────────────────────────────────────────

# Free GeoIP services (fallback chain — no API key needed)
GEOIP_SERVICES = [
    {
        "url": "http://ip-api.com/json/{ip}?fields=countryCode,timezone,city,query",
        "country_field": "countryCode",
        "tz_field": "timezone",
    },
    {
        "url": "https://ipapi.co/{ip}/json/",
        "country_field": "country_code",
        "tz_field": "timezone",
    },
    {
        "url": "https://ipwho.is/{ip}",
        "country_field": "country_code",
        "tz_field": "timezone.id",
    },
]


def resolve_geo_from_ip(ip: str) -> dict | None:
    """
    Detect country code and timezone from an IP address.
    Uses free GeoIP services with fallback chain.
    
    Returns: {"country": "US", "timezone": "America/New_York", "city": "..."}
    """
    for service in GEOIP_SERVICES:
        try:
            url = service["url"].format(ip=ip)
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                continue
            data = resp.json()

            # Extract country code (handles nested fields like "timezone.id")
            country = _extract_field(data, service["country_field"])
            tz = _extract_field(data, service["tz_field"])

            if country:
                result = {
                    "country": country.upper(),
                    "timezone": tz or "",
                    "city": data.get("city", ""),
                }
                logger.debug(f"GEO resolved: {ip} → {result['country']} ({tz})")
                return result
        except Exception as e:
            logger.debug(f"GeoIP service failed ({service['url'][:30]}...): {e}")
            continue

    logger.warning(f"Could not resolve GEO for IP: {ip}")
    return None


def _extract_field(data: dict, field_path: str):
    """Extract nested field like 'timezone.id' from dict."""
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def resolve_proxy_geo(proxy) -> str | None:
    """
    Get GEO country code for a proxy.
    Uses pre-set proxy.geo first, falls back to IP detection.
    """
    # 1. Check pre-set geo field
    if hasattr(proxy, 'geo') and proxy.geo:
        return proxy.geo.upper()

    # 2. Detect from IP
    if hasattr(proxy, 'host') and proxy.host:
        result = resolve_geo_from_ip(proxy.host)
        if result:
            return result["country"]

    return None


# ── SMS Country Priority ───────────────────────────────────────────────────────

def get_sms_countries_priority(proxy_geo: str = None) -> list[str]:
    """
    Get SMS country list prioritized by proxy GEO.
    
    Strategy:
    1. Same country as proxy (if available in SMS service)
    2. Same language countries
    3. Neighboring/similar region countries
    4. Global fallback pool
    
    Returns list of ISO country codes, best-match first.
    """
    priority = []
    seen = set()

    # 1. Exact match
    if proxy_geo:
        country_data = get_country(proxy_geo)
        if country_data and country_data.get("simsms") is not None:
            priority.append(proxy_geo)
            seen.add(proxy_geo)

        # 2. Same language countries
        if country_data:
            lang = country_data.get("lang", "")
            for c in COUNTRIES:
                if c["lang"] == lang and c["code"] not in seen and c.get("simsms") is not None:
                    priority.append(c["code"])
                    seen.add(c["code"])

    # 3. High-quality SMS countries (reliable, fast delivery)
    premium_countries = ["US", "GB", "DE", "NL", "SE", "FI", "PL", "CZ", "EE"]
    for code in premium_countries:
        if code not in seen and get_simsms_country_code(code) is not None:
            priority.append(code)
            seen.add(code)

    # 4. Rest of available countries
    for c in COUNTRIES:
        if c["code"] not in seen and c.get("simsms") is not None:
            priority.append(c["code"])
            seen.add(c["code"])

    return priority


# ── GEO Consistency Resolver ───────────────────────────────────────────────────

def build_geo_profile(proxy_geo: str) -> dict:
    """
    Build a complete, consistent GEO profile from a country code.
    Returns everything needed for anti-detect browser context + SMS ordering.
    
    Usage:
        profile = build_geo_profile("BR")
        # profile = {
        #     "country": "BR",
        #     "timezone": "America/Sao_Paulo",
        #     "language": "pt",
        #     "locale": "pt-BR",
        #     "languages": ["pt-BR", "pt", "en"],
        #     "simsms_code": 10,
        #     "sms_countries": ["BR", "PT", ...],
        # }
    """
    country_data = get_country(proxy_geo)
    if not country_data:
        # Fallback to US
        country_data = get_country("US") or {
            "code": "US", "lang": "en", "tz": "America/New_York", "simsms": 12
        }
        proxy_geo = "US"

    lang = country_data["lang"]
    locale_str = f"{lang}-{proxy_geo}"

    # Build language list like real Chrome
    languages = [locale_str]
    bare = locale_str.split("-")[0]
    if bare != locale_str:
        languages.append(bare)
    if "en" not in languages:
        languages.append("en")

    return {
        "country": proxy_geo,
        "timezone": country_data["tz"],
        "language": lang,
        "locale": locale_str,
        "languages": languages,
        "simsms_code": country_data.get("simsms"),
        "sms_countries": get_sms_countries_priority(proxy_geo),
        "country_name": country_data.get("name", ""),
    }


def validate_geo_consistency(ip_geo: str, browser_tz: str, browser_lang: str) -> dict:
    """
    Validate that IP geo, browser timezone, and browser language are consistent.
    Returns a report with warnings.
    
    Used before registration to detect potential mismatches that trigger alerts.
    """
    warnings = []
    country_data = get_country(ip_geo)

    if not country_data:
        warnings.append(f"Unknown country code: {ip_geo}")
        return {"consistent": False, "warnings": warnings}

    # Check timezone match
    expected_tz = country_data["tz"]
    if browser_tz and browser_tz != expected_tz:
        # Allow same-offset timezones (e.g., America/New_York vs America/Detroit)
        if not _timezones_compatible(browser_tz, expected_tz):
            warnings.append(
                f"Timezone mismatch: IP={ip_geo} expects {expected_tz}, browser has {browser_tz}"
            )

    # Check language match
    expected_lang = country_data["lang"]
    if browser_lang:
        browser_base = browser_lang.split("-")[0].split("_")[0].lower()
        if browser_base != expected_lang:
            warnings.append(
                f"Language mismatch: IP={ip_geo} expects {expected_lang}, browser has {browser_lang}"
            )

    return {
        "consistent": len(warnings) == 0,
        "warnings": warnings,
        "expected": {
            "timezone": expected_tz,
            "language": expected_lang,
        },
    }


def _timezones_compatible(tz1: str, tz2: str) -> bool:
    """Check if two timezones are roughly compatible (same region)."""
    # Simple heuristic: same continent prefix
    region1 = tz1.split("/")[0] if "/" in tz1 else tz1
    region2 = tz2.split("/")[0] if "/" in tz2 else tz2
    return region1 == region2
