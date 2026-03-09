"""
Leomail v4 - Birth Helpers
Shared utility functions for all provider registration engines.
"""
import asyncio
import unicodedata
import random
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from loguru import logger

from ...config import load_config, get_api_key
from ...services.captcha_provider import CaptchaProvider, get_captcha_chain, CaptchaChain
from ...services.sms_provider import GrizzlySMS
from ...services.simsms_provider import SimSmsProvider
from ...services.fivesim_provider import FiveSimProvider

from ...database import USER_DATA_DIR as _USER_DATA_DIR
DEBUG_SCREENSHOT_DIR = str(_USER_DATA_DIR / "debug_screenshots")

# ── Auto-export file for market-format accounts ──
ACCOUNTS_EXPORT_FILE = _USER_DATA_DIR / "accounts_export.txt"


def export_account_to_file(account, extra_fields: dict = None):
    """
    Append a newly registered account to the market-format export file.
    Format: email:password:recovery_email:recovery_phone:first_last:birthday:user_agent:birth_ip:profile_path
    
    This creates one line per account in a text file that can be sold on
    account markets or imported into other tools.
    """
    try:
        ACCOUNTS_EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        email = account.email or ""
        password = account.password or ""
        recovery = account.recovery_email or ""
        recovery_phone = account.recovery_phone or ""
        name = f"{account.first_name or ''} {account.last_name or ''}".strip()
        birthday_str = ""
        if account.birthday:
            try:
                birthday_str = account.birthday.strftime("%d.%m.%Y")
            except Exception:
                birthday_str = str(account.birthday)
        ua = account.user_agent or ""
        ip = account.birth_ip or ""
        profile = account.browser_profile_path or ""
        geo = account.geo or ""
        provider = account.provider or ""

        # Extra fields from caller (e.g. phone number used for SMS)
        sms_phone = ""
        if extra_fields:
            sms_phone = extra_fields.get("sms_phone", "")

        # Market format: email:pass:recovery:recovery_phone:sms_phone:name:birthday:geo:ua:ip:profile
        line = ":".join([
            email, password, recovery, recovery_phone, sms_phone,
            name, birthday_str, geo, provider,
        ])

        with open(ACCOUNTS_EXPORT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        logger.info(f"Account exported: {email} -> {ACCOUNTS_EXPORT_FILE}")
    except Exception as e:
        logger.warning(f"Export failed for {getattr(account, 'email', '?')}: {e}")


def get_sms_provider(provider_name: str):
    """Get configured SMS provider."""
    config = load_config()
    if provider_name == "grizzly":
        key = config.get("sms", {}).get("grizzly", {}).get("api_key", "")
        return GrizzlySMS(key) if key else None
    elif provider_name == "5sim":
        key = config.get("sms", {}).get("5sim", {}).get("api_key", "")
        return FiveSimProvider(key) if key else None
    else:
        key = config.get("sms", {}).get("simsms", {}).get("api_key", "")
        return SimSmsProvider(key) if key else None


# SMS provider priority: 5sim first, then GrizzlySMS, then SimSMS
SMS_FALLBACK_ORDER = ["5sim", "grizzly", "simsms"]

# Max attempts per SMS provider before moving to next
SMS_MAX_ATTEMPTS_PER_PROVIDER = 3

# SMS code wait timeout per attempt (5 minutes)
SMS_CODE_TIMEOUT = 300


def get_sms_chain(primary: str = None) -> list:
    """Return ALL configured SMS providers in fixed order: 5sim → GrizzlySMS → SimSMS.
    The 'primary' parameter is ignored — order is always fixed."""
    chain = []
    for name in SMS_FALLBACK_ORDER:
        provider = get_sms_provider(name)
        if provider:
            chain.append((name, provider))
    return chain


# ── Shared Phone ↔ Country Mappings (used by Yahoo, AOL, Gmail) ──

# SMS provider country code -> phone prefix (e.g. "us" -> "1", "br" -> "55")
PHONE_COUNTRY_MAP = {
    "ru": "7", "ua": "380", "kz": "7", "cn": "86", "ph": "63", "id": "62",
    "my": "60", "ke": "254", "tz": "255", "br": "55", "us": "1", "us_v": "1",
    "il": "972", "hk": "852", "pl": "48", "uk": "44", "ng": "234", "eg": "20",
    "in": "91", "ie": "353", "za": "27", "ro": "40", "co": "57", "ee": "372",
    "ca": "1", "de": "49", "nl": "31", "at": "43", "th": "66", "mx": "52",
    "es": "34", "tr": "90", "cz": "420", "pe": "51", "nz": "64", "se": "46",
    "fr": "33", "ar": "54", "vn": "84", "bd": "880", "pk": "92", "cl": "56",
    "be": "32", "bg": "359", "hu": "36", "it": "39", "pt": "351", "gr": "30",
    "fi": "358", "dk": "45", "no": "47", "ch": "41", "au": "61", "jp": "81",
    "ge": "995", "ae": "971", "sa": "966", "cr": "506", "gt": "502", "sk": "421",
    "am": "374", "az": "994", "by": "375", "md": "373", "al": "355", "rs": "381",
    "hr": "385", "si": "386", "lv": "371", "lt": "370", "uy": "598", "bo": "591",
}

# Reverse: phone prefix -> SMS provider country code (e.g. "55" -> "br", "1" -> "us")
PREFIX_TO_SMS_COUNTRY = {}
for _sms_cc, _prefix in PHONE_COUNTRY_MAP.items():
    if _prefix not in PREFIX_TO_SMS_COUNTRY:
        PREFIX_TO_SMS_COUNTRY[_prefix] = _sms_cc
    elif "_v" in PREFIX_TO_SMS_COUNTRY[_prefix] and "_v" not in _sms_cc:
        PREFIX_TO_SMS_COUNTRY[_prefix] = _sms_cc  # prefer real over virtual
PREFIX_TO_SMS_COUNTRY["1"] = "us"   # +1 = US (not Canada or US Virtual)
PREFIX_TO_SMS_COUNTRY["7"] = "ru"   # +7 = Russia (not Kazakhstan)

# ISO2 -> SMS provider country code (e.g. "BR" -> "br", "US" -> "us")
ISO2_TO_SMS_COUNTRY = {
    "RU": "ru", "UA": "ua", "KZ": "kz", "CN": "cn", "PH": "ph", "ID": "id",
    "MY": "my", "KE": "ke", "TZ": "tz", "BR": "br", "US": "us",
    "IL": "il", "HK": "hk", "PL": "pl", "GB": "uk", "NG": "ng", "EG": "eg",
    "IN": "in", "IE": "ie", "ZA": "za", "RO": "ro", "CO": "co", "EE": "ee",
    "CA": "ca", "DE": "de", "NL": "nl", "AT": "at", "TH": "th", "MX": "mx",
    "ES": "es", "TR": "tr", "CZ": "cz", "PE": "pe", "NZ": "nz", "SE": "se",
    "FR": "fr", "AR": "ar", "VN": "vn", "BD": "bd", "PK": "pk", "CL": "cl",
    "BE": "be", "BG": "bg", "HU": "hu", "IT": "it", "PT": "pt", "GR": "gr",
    "FI": "fi", "DK": "dk", "NO": "no", "CH": "ch", "AU": "au", "JP": "jp",
    "GE": "ge", "AE": "ae", "SA": "sa", "CR": "cr", "GT": "gt", "SK": "sk",
    "AM": "am", "AZ": "az", "BY": "by", "MD": "md", "AL": "al", "RS": "rs",
    "HR": "hr", "SI": "si", "LV": "lv", "LT": "lt", "UY": "uy", "BO": "bo",
}

# Reverse: SMS provider country code -> ISO2 (e.g. "br" -> "BR", "uk" -> "GB")
COUNTRY_TO_ISO2 = {v: k for k, v in ISO2_TO_SMS_COUNTRY.items()}

# ── SMS cost tiers (Economist skill: cheap first, escalate if needed) ──
SMS_TIER_CHEAP = ["id", "ph", "in", "bd", "pk", "ke", "tz", "vn"]     # $0.03-0.05
SMS_TIER_MEDIUM = ["ru", "br", "co", "mx", "ua", "ar", "cl", "pe"]    # $0.08-0.15
SMS_TIER_EXPENSIVE = ["us", "uk", "ca", "de", "nl", "se", "fr", "au"]  # $0.30-0.50
SMS_ALL_TIERS = SMS_TIER_CHEAP + SMS_TIER_MEDIUM + SMS_TIER_EXPENSIVE

# Priority order when no specific country detected (cheap → expensive)
COUNTRY_FALLBACK_PRIORITY = SMS_ALL_TIERS + [
    "pl", "es", "it", "at", "cz", "ee", "ro", "ie", "il",
]

# Yahoo-specific SMS country priority (Phase 3 data: sorted by number pool size)
# High pool = less recycled numbers = higher success rate
YAHOO_COUNTRY_PRIORITY = [
    "ca",   # Canada       +1   — 45K numbers
    "uk",   # UK           +44  — 28K numbers
    "se",   # Sweden       +46  — 14K numbers
    "br",   # Brazil       +55  — 13K numbers
    "us",   # USA          +1   — 9K numbers
    "nl",   # Netherlands  +31  — 5K numbers
    "dk",   # Denmark      +45  — 5K numbers
    "ee",   # Estonia      +372 — 5K numbers
    "at",   # Austria      +43  — 5K numbers
    "pl",   # Poland       +48  — 5K numbers
    "ro",   # Romania      +40  — 4K numbers
    "cz",   # Czech Rep    +420 — 4K numbers
    "fi",   # Finland      +358 — 4K numbers
    "ch",   # Switzerland  +41  — 3.5K numbers
    "de",   # Germany      +49  — 3K numbers
    "no",   # Norway       +47  — 3K numbers
    "th",   # Thailand     +66  — 3K numbers
    "fr",   # France       +33  — 3K numbers
    "il",   # Israel       +972 — 2.5K numbers
    "it",   # Italy        +39  — 2K numbers
    "es",   # Spain        +34  — 2K numbers
    "hu",   # Hungary      +36  — 2K numbers
    "mx",   # Mexico       +52  — 2K numbers
    "ie",   # Ireland      +353 — 1.5K numbers
    "jp",   # Japan        +81  — 0.7K (PREMIUM real SIM)
]

# ── Per-provider SMS country rules ──
# mode: "geo_match" = SMS country MUST match proxy IP country (Yahoo/AOL requirement)
#       "tier1"     = use high-quality Tier-1 countries only (Gmail)
#       "flexible"  = any country, broad fallback list (Outlook/Hotmail)
#       "none"      = SMS not used (ProtonMail)
EMAIL_PROVIDER_SMS_RULES = {
    "gmail": {
        "mode": "tier1",
        "countries": ["us", "uk", "ca", "de", "nl", "se", "pl", "fr"],
    },
    "yahoo": {
        "mode": "geo_match",  # SMS country MUST match proxy geo
        "fallback": YAHOO_COUNTRY_PRIORITY,
    },
    "aol": {
        "mode": "geo_match",  # same Verizon engine as Yahoo
        "fallback": YAHOO_COUNTRY_PRIORITY,
    },
    "outlook": {
        "mode": "flexible",
        "countries": SMS_ALL_TIERS,  # cheap first, auto-escalate
    },
    "hotmail": {
        "mode": "flexible",
        "countries": SMS_ALL_TIERS,  # cheap first, auto-escalate
    },
    "protonmail": {
        "mode": "none",
    },
    "webde": {
        "mode": "flexible",
        "countries": SMS_ALL_TIERS,  # Web.de: any country, cheap first
    },
}


def service_country_priority(service: str, proxy_geo: str = None) -> list:
    """Return service-specific country priority list using EMAIL_PROVIDER_SMS_RULES.
    For geo_match mode (Yahoo/AOL): proxy geo country forced first.
    For tier1 mode (Gmail): hardcoded Tier-1 countries.
    For flexible mode (Outlook): broad fallback list.
    """
    rules = EMAIL_PROVIDER_SMS_RULES.get(service, {"mode": "flexible", "countries": COUNTRY_FALLBACK_PRIORITY})
    mode = rules.get("mode", "flexible")

    if mode == "none":
        return []  # ProtonMail doesn't use SMS

    if mode == "geo_match":
        # Yahoo/AOL: proxy geo country MUST be first
        result = []
        if proxy_geo:
            geo_cc = ISO2_TO_SMS_COUNTRY.get(proxy_geo.upper())
            if geo_cc:
                result.append(geo_cc)
        # Then fallback countries (Yahoo pool-size priority)
        for c in rules.get("fallback", YAHOO_COUNTRY_PRIORITY):
            if c not in result:
                result.append(c)
        return result

    if mode == "tier1":
        # Gmail: Tier-1 only (expensive real SIM)
        result = []
        if proxy_geo:
            geo_cc = ISO2_TO_SMS_COUNTRY.get(proxy_geo.upper())
            if geo_cc and geo_cc in rules.get("countries", []):
                result.append(geo_cc)  # proxy geo first IF it's Tier-1
        for c in rules.get("countries", []):
            if c not in result:
                result.append(c)
        return result

    # flexible (Outlook/Hotmail): proxy geo first, then broad list
    result = []
    if proxy_geo:
        geo_cc = ISO2_TO_SMS_COUNTRY.get(proxy_geo.upper())
        if geo_cc:
            result.append(geo_cc)
    for c in rules.get("countries", COUNTRY_FALLBACK_PRIORITY):
        if c not in result:
            result.append(c)
    return result


# ── Per-task SMS chain state tracker ──
# Tracks which provider we're on and how many attempts used
_sms_chain_state = {}  # {service: {"provider_idx": int, "attempt": int, "used_numbers": set}}
_sms_chain_lock = threading.Lock()  # protects _sms_chain_state from concurrent access


def _get_chain_state(service: str) -> dict:
    """Get or create chain state for a service (yahoo, outlook, etc.)."""
    with _sms_chain_lock:
        if service not in _sms_chain_state:
            _sms_chain_state[service] = {
                "provider_idx": 0,
                "attempt": 0,
                "used_numbers": set(),
            }
        return _sms_chain_state[service]


def reset_chain_state(service: str):
    """Reset chain state (call at start of each registration attempt)."""
    with _sms_chain_lock:
        _sms_chain_state.pop(service, None)


async def scrape_phone_dropdown(page, _log=None) -> list[str]:
    """Scrape Yahoo/AOL phone country code dropdown to get available prefixes.
    Returns list of phone prefixes like ['1', '44', '55', ...].
    """
    if _log is None:
        _log = lambda msg: logger.info(msg)
    try:
        prefixes = await page.evaluate("""() => {
            const results = [];
            // Method 1: <select> with country codes
            const selects = document.querySelectorAll('select');
            for (const sel of selects) {
                for (const opt of sel.options) {
                    const m = opt.text.match(/\\+(\\d{1,4})/);
                    if (m && !results.includes(m[1])) results.push(m[1]);
                }
            }
            // Method 2: listbox items
            if (results.length === 0) {
                const items = document.querySelectorAll('[role="option"], [data-country]');
                for (const item of items) {
                    const text = item.textContent || '';
                    const m = text.match(/\\+(\\d{1,4})/);
                    if (m && !results.includes(m[1])) results.push(m[1]);
                }
            }
            return results;
        }""")
        if prefixes and len(prefixes) > 0:
            _log(f"Scraped {len(prefixes)} country prefixes from dropdown")
            return prefixes
    except Exception as e:
        _log(f"Dropdown scrape failed: {e}")
    return []


# ── SMS backoff tracking (prevent hammering providers) ──
_sms_backoff = {}  # {service: {"fails": int, "last_fail": float}}


def _reset_sms_backoff(service: str):
    """Reset backoff after successful SMS order."""
    _sms_backoff.pop(service, None)


def _record_sms_fail(service: str):
    """Record an SMS failure for the service."""
    import time
    if service not in _sms_backoff:
        _sms_backoff[service] = {"fails": 0, "last_fail": 0}
    _sms_backoff[service]["fails"] += 1
    _sms_backoff[service]["last_fail"] = time.time()
    logger.warning(f"[SMS] {service} fail #{_sms_backoff[service]['fails']}")


async def order_sms_with_chain(
    service: str,
    sms_provider,
    proxy_geo: str = None,
    page=None,
    scrape_dropdown: bool = True,
    _log=None,
    _err=None,
) -> tuple:
    """
    Order an SMS number using the fixed provider chain: 5sim → GrizzlySMS → SimSMS.
    
    Always orders the MOST EXPENSIVE / highest quality numbers.
    Ignores the passed sms_provider — uses fixed chain order instead.
    
    Args:
        service: "yahoo", "aol", "gmail", "outlook"
        sms_provider: ignored (kept for API compat), chain always uses fixed order
        proxy_geo: ISO2 country code from proxy (e.g. "BR", "US")
        page: Playwright page for dropdown scraping (Yahoo/AOL only)
        scrape_dropdown: whether to scrape phone country dropdown
        _log: logging function
        _err: error logging function

    Returns:
        (order_dict, active_provider, expanded_countries) or (None, None, [])
        order_dict: {"id": ..., "number": ..., "country": ..., "service": ...}
    """
    if not _log:
        _log = lambda msg: logger.info(msg)
    if not _err:
        _err = lambda msg: logger.error(msg)

    # ── Build ordered country list using EMAIL_PROVIDER_SMS_RULES ──
    expanded_countries = service_country_priority(service, proxy_geo)

    # Enrich with dropdown data (Yahoo/AOL only)
    dropdown_countries = []
    if scrape_dropdown and page:
        prefixes = await scrape_phone_dropdown(page, _log)
        if prefixes:
            for prefix in prefixes:
                cc = PREFIX_TO_SMS_COUNTRY.get(prefix)
                if cc and cc not in dropdown_countries:
                    dropdown_countries.append(cc)
            _log(f"Dropdown countries: {dropdown_countries[:10]}...")

    # Insert dropdown countries after geo but before fallback
    # For geo_match: keep geo first, then dropdown, then fallback
    if dropdown_countries:
        # Find where to insert: after proxy geo (index 0-1) but before general fallback
        insert_at = 1 if proxy_geo else 0
        for c in dropdown_countries:
            if c not in expanded_countries:
                expanded_countries.insert(insert_at, c)
                insert_at += 1

    _log(f"SMS countries (priority): {expanded_countries[:8]}...")

    # ── Build provider chain (FIXED order: 5sim → grizzly → simsms) ──
    sms_chain = get_sms_chain()
    if not sms_chain:
        _err("No SMS providers configured!")
        return None, None, expanded_countries

    _log(f"[SMS] Chain: {[n for n, _ in sms_chain]} | {SMS_MAX_ATTEMPTS_PER_PROVIDER} attempts/provider")

    # ── Try each provider with up to 3 attempts ──
    state = _get_chain_state(service)

    for provider_name, provider in sms_chain:
        _log(f"[SMS] >> Trying provider: {provider_name}")

        # ALWAYS use order_number_from_countries — NEVER order_best_number
        # order_best_number ignores country which causes wrong country numbers!
        # Each provider's order_number_from_countries already sorts by price DESC
        # (most expensive = best quality) within the given country list.
        order = None
        try:
            if hasattr(provider, 'order_number_from_countries'):
                _log(f"[SMS] {provider_name}: ordering from countries {expanded_countries[:5]}... (price DESC)")
                order = await asyncio.to_thread(
                    provider.order_number_from_countries, service, expanded_countries
                )
            else:
                # Fallback: try countries one by one
                for country in expanded_countries[:5]:
                    _log(f"[SMS] {provider_name}: trying {country}...")
                    order = await asyncio.to_thread(provider.order_number, service, country)
                    if order and "error" not in order:
                        break
        except Exception as e:
            _log(f"[SMS] {provider_name} order error: {e}")
            continue

        if order and "error" not in order:
            number = order.get("number", "")
            # Skip if we already used this number
            if number in state["used_numbers"]:
                _log(f"[SMS] Number {number} already used, skipping")
                continue
            
            state["used_numbers"].add(number)
            state["provider_idx"] = SMS_FALLBACK_ORDER.index(provider_name) if provider_name in SMS_FALLBACK_ORDER else 0
            state["attempt"] = 1
            
            _log(f"[OK] {provider_name}: number from {order.get('country', '?')} - {number}")
            _reset_sms_backoff(service)

            # ── Track cost (Economist skill) ──
            try:
                from ...services.cost_tracker import cost_tracker
                country = order.get("country", "")
                # Estimate cost based on tier
                if country in SMS_TIER_CHEAP:
                    est_cost = 0.04
                elif country in SMS_TIER_MEDIUM:
                    est_cost = 0.12
                else:
                    est_cost = 0.35
                cost_tracker.record_sms(
                    provider=provider_name, amount=est_cost,
                    country=country, success=True,
                )
            except Exception:
                pass

            return order, provider, expanded_countries
        
        err_msg = order.get("error", "empty") if order else "no response"
        _log(f"[SMS] {provider_name}: {err_msg}")

    _record_sms_fail(service)
    _err(f"[FAIL] All SMS providers exhausted for {service}")
    return None, None, expanded_countries


async def get_next_sms_number(
    service: str,
    current_provider,
    current_provider_name: str,
    expanded_countries: list,
    _log=None,
    _err=None,
) -> tuple:
    """
    Get the next SMS number after a failure (rejected number or code timeout).
    
    Implements the chain rotation logic:
    - Up to 3 attempts per provider
    - After 3 fails → move to next provider (5sim → grizzly → simsms)
    - Returns (order_dict, provider, provider_name) or (None, None, None)
    """
    if not _log:
        _log = lambda msg: logger.info(msg)
    if not _err:
        _err = lambda msg: logger.error(msg)

    state = _get_chain_state(service)
    sms_chain = get_sms_chain()
    
    if not sms_chain:
        _err("No SMS providers configured!")
        return None, None, None

    # Find current provider index in chain
    current_idx = None
    for i, (name, _) in enumerate(sms_chain):
        if name == current_provider_name:
            current_idx = i
            break
    
    if current_idx is None:
        current_idx = 0

    # Check if we still have attempts left on current provider
    if state["attempt"] < SMS_MAX_ATTEMPTS_PER_PROVIDER:
        state["attempt"] += 1
        provider_name = current_provider_name
        provider = current_provider
        _log(f"[SMS] Retry #{state['attempt']}/{SMS_MAX_ATTEMPTS_PER_PROVIDER} on {provider_name}")
    else:
        # Move to next provider
        next_idx = current_idx + 1
        if next_idx >= len(sms_chain):
            _err(f"[SMS] All providers exhausted ({SMS_MAX_ATTEMPTS_PER_PROVIDER} attempts each × {len(sms_chain)} providers)")
            return None, None, None
        
        provider_name, provider = sms_chain[next_idx]
        state["provider_idx"] = next_idx
        state["attempt"] = 1
        _log(f"[SMS] Switching to {provider_name} (attempt 1/{SMS_MAX_ATTEMPTS_PER_PROVIDER})")

    # Order new number from this provider
    # ALWAYS use order_number_from_countries to respect EMAIL_PROVIDER_SMS_RULES
    order = None
    try:
        if hasattr(provider, 'order_number_from_countries'):
            _log(f"[SMS] {provider_name}: ordering from countries {expanded_countries[:5]}... (price DESC)")
            order = await asyncio.to_thread(
                provider.order_number_from_countries, service, expanded_countries
            )
        else:
            for country in expanded_countries[:5]:
                order = await asyncio.to_thread(provider.order_number, service, country)
                if order and "error" not in order:
                    break
    except Exception as e:
        _log(f"[SMS] {provider_name} order error: {e}")
        # Try to move to next provider recursively
        state["attempt"] = SMS_MAX_ATTEMPTS_PER_PROVIDER  # Force next provider
        return await get_next_sms_number(service, provider, provider_name, expanded_countries, _log, _err)

    if order and "error" not in order:
        number = order.get("number", "")
        if number in state["used_numbers"]:
            _log(f"[SMS] Duplicate number {number}, getting another...")
            return await get_next_sms_number(service, provider, provider_name, expanded_countries, _log, _err)
        
        state["used_numbers"].add(number)
        _log(f"[OK] {provider_name} #{state['attempt']}: {order.get('country', '?')} - {number}")
        return order, provider, provider_name

    err_msg = order.get("error", "empty") if order else "no response"
    _log(f"[SMS] {provider_name}: {err_msg}")
    
    # This attempt failed to get a number — force move to next provider
    state["attempt"] = SMS_MAX_ATTEMPTS_PER_PROVIDER
    return await get_next_sms_number(service, provider, provider_name, expanded_countries, _log, _err)


# Keep backward-compatible alias
async def order_sms_retry(
    service: str,
    active_provider,
    expanded_countries: list,
    used_numbers: set = None,
    _log=None,
) -> dict | None:
    """
    DEPRECATED: Use get_next_sms_number() instead.
    Kept for backward compatibility with existing code.
    """
    if not _log:
        _log = lambda msg: logger.info(msg)

    # Determine provider name
    _cls = type(active_provider).__name__.lower()
    if 'grizzly' in _cls:
        pname = 'grizzly'
    elif 'fivesim' in _cls or '5sim' in _cls:
        pname = '5sim'
    else:
        pname = 'simsms'

    order, provider, provider_name = await get_next_sms_number(
        service=service,
        current_provider=active_provider,
        current_provider_name=pname,
        expanded_countries=expanded_countries,
        _log=_log,
    )
    return order


def get_captcha_provider():
    """Return a CaptchaChain with all configured providers for auto-fallback.
    Falls back to single CapGuru if chain has no providers."""
    chain = get_captcha_chain()
    if chain.providers:
        return chain
    # Legacy fallback: single CapGuru
    key = get_api_key("capguru") or ""
    return CaptchaProvider(api_key=key) if key else None


async def debug_screenshot(page, label: str, _log=None):
    """Capture a debug screenshot at a key flow point. Never crashes."""
    try:
        Path(DEBUG_SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        fname = f"{ts}_{label}.png"
        path = str(Path(DEBUG_SCREENSHOT_DIR) / fname)
        await page.screenshot(path=path, full_page=False)
        if _log:
            _log(f"[SNAP] Screenshot: {fname}")
        return path
    except Exception as e:
        if _log:
            _log(f"[SNAP] Screenshot failed: {e}")
        return None


async def human_delay(min_s=0.5, max_s=2.0):
    """Random human-like delay."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_mouse_to(page, selector):
    """Move mouse to element using Bezier curve (not linear interpolation).
    Uses Gaussian offset from center — humans don't hit dead center."""
    try:
        from ..human_behavior import _move_mouse_to, _generate_bezier_path
        el = page.locator(selector).first
        box = await el.bounding_box()
        if box:
            # Gaussian offset from center (most clicks near center but not exactly)
            cx = box['x'] + box['width'] * 0.5 + random.gauss(0, box['width'] * 0.12)
            cy = box['y'] + box['height'] * 0.5 + random.gauss(0, box['height'] * 0.10)
            # Clamp within element
            cx = max(box['x'] + 3, min(box['x'] + box['width'] - 3, cx))
            cy = max(box['y'] + 2, min(box['y'] + box['height'] - 2, cy))
            await _move_mouse_to(page, cx, cy)
            await asyncio.sleep(random.uniform(0.05, 0.2))
    except Exception:
        pass


async def human_click(page, selector):
    """Bezier-curve move to element, hover dwell, then click with offset."""
    try:
        from ..human_behavior import _move_mouse_to
        el = page.locator(selector).first
        box = await el.bounding_box()
        if box:
            # Gaussian offset from center
            cx = box['x'] + box['width'] * 0.5 + random.gauss(0, box['width'] * 0.13)
            cy = box['y'] + box['height'] * 0.5 + random.gauss(0, box['height'] * 0.12)
            cx = max(box['x'] + 2, min(box['x'] + box['width'] - 2, cx))
            cy = max(box['y'] + 2, min(box['y'] + box['height'] - 2, cy))
            # Bezier approach
            await _move_mouse_to(page, cx, cy)
            # Hover dwell — reading button text (150-400ms)
            await asyncio.sleep(random.uniform(0.15, 0.4))
            await page.mouse.click(cx, cy)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            return
    except Exception:
        pass
    # Fallback
    try:
        await page.locator(selector).first.click()
    except Exception:
        pass
    await human_delay(0.2, 0.5)


async def human_fill(page, selector, text, field_type="default"):
    """Click field with Bezier, clear, then type with human patterns.
    Uses context-aware speed, thinking pauses, and micro-bursts."""
    try:
        from ..human_behavior import _move_mouse_to, TYPING_PROFILES
        el = page.locator(selector).first
        box = await el.bounding_box()
        if box:
            cx = box['x'] + box['width'] * 0.5 + random.gauss(0, box['width'] * 0.10)
            cy = box['y'] + box['height'] * 0.5 + random.gauss(0, box['height'] * 0.08)
            cx = max(box['x'] + 3, min(box['x'] + box['width'] - 3, cx))
            cy = max(box['y'] + 2, min(box['y'] + box['height'] - 2, cy))
            await _move_mouse_to(page, cx, cy)
            await asyncio.sleep(random.uniform(0.15, 0.40))
            await page.mouse.click(cx, cy)
        else:
            await el.click()
        await asyncio.sleep(random.uniform(0.25, 0.55))

        # Clear field
        await el.fill("")
        await asyncio.sleep(random.uniform(0.15, 0.35))

        # Get typing profile for speed context
        profile = TYPING_PROFILES.get(field_type, TYPING_PROFILES["default"])
        base_min = profile["base_min"]
        base_max = profile["base_max"]
        think_chance = profile["think_chance"]

        skip_until = 0  # Track burst-typed chars to avoid double-typing
        for i, char in enumerate(text):
            # Skip chars already typed by a previous burst
            if i < skip_until:
                continue

            # Thinking pause before special characters
            if char in "@._-!#$%&" and random.random() < 0.45:
                await asyncio.sleep(random.uniform(0.35, 0.85))
            elif char.isdigit() and i > 0 and text[i-1].isalpha() and random.random() < 0.30:
                await asyncio.sleep(random.uniform(0.3, 0.6))

            # Random thinking pause
            if random.random() < think_chance:
                await asyncio.sleep(random.uniform(0.4, 0.9))

            delay_ms = random.randint(base_min, base_max)

            # Muscle-memory burst: sometimes 2-3 chars come fast
            if random.random() < 0.12 and i + 2 < len(text):
                burst_len = random.randint(2, 3)
                for j in range(burst_len):
                    if i + j < len(text):
                        await page.keyboard.type(text[i + j], delay=random.randint(35, 65))
                skip_until = i + burst_len  # Skip these chars in main loop
                continue

            await page.keyboard.type(char, delay=delay_ms)

            # Micro-pause every few chars (rhythm variation)
            if i > 0 and i % random.randint(3, 7) == 0 and random.random() < 0.25:
                await asyncio.sleep(random.uniform(0.1, 0.35))

    except Exception:
        try:
            await page.locator(selector).first.fill(text)
        except Exception:
            pass


async def human_type(page, selector, text, thread_log=None, db=None):
    """Type text with human-like delays, thinking pauses, and rhythm variation."""
    el = page.locator(selector)
    await el.click()
    await human_delay(0.3, 0.8)
    for i, char in enumerate(text):
        delay = random.randint(45, 120)
        # Thinking pause before special chars
        if char in "@._-" and random.random() < 0.3:
            await asyncio.sleep(random.uniform(0.2, 0.5))
        # Micro-burst: sometimes 2 chars fast (muscle memory)
        if random.random() < 0.1 and i + 1 < len(text):
            await el.type(char, delay=random.randint(20, 40))
            continue
        await el.type(char, delay=delay)
        if random.random() < 0.15:
            await human_delay(0.2, 0.6)


async def check_error_on_page(page) -> str | None:
    """Check if Microsoft shows an error message (supports both old and new Fluent UI).
    
    IMPORTANT: Must not false-positive on normal page headings like
    'Create your password', 'Add some details', etc.
    """
    # Phase 1: Check known MS error element IDs (most reliable)
    ms_error_ids = [
        '#MemberNameError', '#PasswordError', '#FirstNameError',
        '#LastNameError', '#BirthDateError', '#ServerError',
        '#error', '#hipEnf498', '.alert-error',
    ]
    for sel in ms_error_ids:
        try:
            el = page.locator(sel)
            if await el.count() > 0:
                text = (await el.first.text_content() or "").strip()
                if text and len(text) > 3:
                    return text
        except Exception:
            continue

    # Phase 2: JS scan for specific error text patterns (most accurate)
    # Only matches text that actually indicates an error
    try:
        error_text = await page.evaluate(r"""() => {
            const errorPatterns = [
                'already taken', 'already exists', 'not available',
                'try another', 'choose a different', 'username is taken',
                'is not valid', 'too short', 'too long',
                'use a different', 'can\'t be used',
                'уже занят', 'недоступ', 'уже существует'
            ];
            // Only search near input fields (avoid matching page headings)
            const containers = document.querySelectorAll(
                'div[class*="error"], span[class*="error"], p[class*="error"], ' +
                '.error-text, .field-error, .validation-error, ' +
                '[aria-live="assertive"], [data-testid*="error"]'
            );
            for (const el of containers) {
                const t = (el.textContent || '').trim().toLowerCase();
                if (t.length > 5 && t.length < 200) {
                    for (const pattern of errorPatterns) {
                        if (t.includes(pattern)) return el.textContent.trim();
                    }
                }
            }
            // Broader scan but ONLY for error keywords
            const allEls = document.querySelectorAll('div, span, p');
            for (const el of allEls) {
                const t = (el.textContent || '').trim().toLowerCase();
                if (t.length > 10 && t.length < 150) {
                    for (const pattern of errorPatterns) {
                        if (t.includes(pattern)) {
                            // Double-check: must NOT be a heading/title
                            const tag = el.tagName.toLowerCase();
                            if (tag === 'h1' || tag === 'h2' || tag === 'h3') continue;
                            return el.textContent.trim();
                        }
                    }
                }
            }
            return null;
        }""")
        if error_text:
            return error_text
    except Exception:
        pass
    return None


# ── Multi-locale month names (month number → known translations) ──
# Covers: en, es, pt, fr, de, it, nl, pl, cs, ro, tr, sv, da, nb, fi, hu, el, ja, ko, zh, ar, he, th, vi, id, ms
MONTH_ALIASES = {
    1:  ["January", "enero", "janeiro", "janvier", "Januar", "gennaio", "januari", "styczeń", "leden", "ianuarie", "Ocak", "januari", "januar", "januar", "tammikuu", "január", "Ιανουάριος", "1月", "1월", "一月", "يناير", "ינואר", "มกราคม", "Tháng 1", "Januari", "Januari"],
    2:  ["February", "febrero", "fevereiro", "février", "Februar", "febbraio", "februari", "luty", "únor", "februarie", "Şubat", "februari", "februar", "februar", "helmikuu", "február", "Φεβρουάριος", "2月", "2월", "二月", "فبراير", "פברואר", "กุมภาพันธ์", "Tháng 2", "Februari", "Februari"],
    3:  ["March", "marzo", "março", "mars", "März", "marzo", "maart", "marzec", "březen", "martie", "Mart", "mars", "marts", "mars", "maaliskuu", "március", "Μάρτιος", "3月", "3월", "三月", "مارس", "מרץ", "มีนาคม", "Tháng 3", "Maret", "Mac"],
    4:  ["April", "abril", "abril", "avril", "April", "aprile", "april", "kwiecień", "duben", "aprilie", "Nisan", "april", "april", "april", "huhtikuu", "április", "Απρίλιος", "4月", "4월", "四月", "أبريل", "אפריל", "เมษายน", "Tháng 4", "April", "April"],
    5:  ["May", "mayo", "maio", "mai", "Mai", "maggio", "mei", "maj", "květen", "mai", "Mayıs", "maj", "maj", "mai", "toukokuu", "május", "Μάιος", "5月", "5월", "五月", "مايو", "מאי", "พฤษภาคม", "Tháng 5", "Mei", "Mei"],
    6:  ["June", "junio", "junho", "juin", "Juni", "giugno", "juni", "czerwiec", "červen", "iunie", "Haziran", "juni", "juni", "juni", "kesäkuu", "június", "Ιούνιος", "6月", "6월", "六月", "يونيو", "יוני", "มิถุนายน", "Tháng 6", "Juni", "Jun"],
    7:  ["July", "julio", "julho", "juillet", "Juli", "luglio", "juli", "lipiec", "červenec", "iulie", "Temmuz", "juli", "juli", "juli", "heinäkuu", "július", "Ιούλιος", "7月", "7월", "七月", "يوليو", "יולי", "กรกฎาคม", "Tháng 7", "Juli", "Julai"],
    8:  ["August", "agosto", "agosto", "août", "August", "agosto", "augustus", "sierpień", "srpen", "august", "Ağustos", "augusti", "august", "august", "elokuu", "augusztus", "Αύγουστος", "8月", "8월", "八月", "أغسطس", "אוגוסט", "สิงหาคม", "Tháng 8", "Agustus", "Ogos"],
    9:  ["September", "septiembre", "setembro", "septembre", "September", "settembre", "september", "wrzesień", "září", "septembrie", "Eylül", "september", "september", "september", "syyskuu", "szeptember", "Σεπτέμβριος", "9月", "9월", "九月", "سبتمبر", "ספטמבר", "กันยายน", "Tháng 9", "September", "September"],
    10: ["October", "octubre", "outubro", "octobre", "Oktober", "ottobre", "oktober", "październik", "říjen", "octombrie", "Ekim", "oktober", "oktober", "oktober", "lokakuu", "október", "Οκτώβριος", "10月", "10월", "十月", "أكتوبر", "אוקטובר", "ตุลาคม", "Tháng 10", "Oktober", "Oktober"],
    11: ["November", "noviembre", "novembro", "novembre", "November", "novembre", "november", "listopad", "listopad", "noiembrie", "Kasım", "november", "november", "november", "marraskuu", "november", "Νοέμβριος", "11月", "11월", "十一月", "نوفمبر", "נובמבר", "พฤศจิกายน", "Tháng 11", "November", "November"],
    12: ["December", "diciembre", "dezembro", "décembre", "Dezember", "dicembre", "december", "grudzień", "prosinec", "decembrie", "Aralık", "december", "december", "desember", "joulukuu", "december", "Δεκέμβριος", "12月", "12월", "十二月", "ديسمبر", "דצמבר", "ธันวาคม", "Tháng 12", "Desember", "Disember"],
}

# ── Multi-locale country names (ISO 3166-1 → known translations) ──
# Covers the countries in our proxy pool + common fallback countries
COUNTRY_ALIASES = {
    "US": ["United States", "Estados Unidos", "États-Unis", "Vereinigte Staaten", "Stati Uniti", "Verenigde Staten", "Stany Zjednoczone", "Spojené státy", "Statele Unite", "Amerika Birleşik Devletleri", "Förenta staterna", "USA"],
    "GB": ["United Kingdom", "Reino Unido", "Royaume-Uni", "Vereinigtes Königreich", "Regno Unito", "Verenigd Koninkrijk", "Wielka Brytania", "Spojené království", "Regatul Unit", "Birleşik Krallık", "Storbritannien", "UK"],
    "CA": ["Canada", "Canadá", "Kanada"],
    "AU": ["Australia", "Australie", "Australien", "Australië"],
    "DE": ["Germany", "Alemania", "Allemagne", "Deutschland", "Germania", "Duitsland", "Niemcy", "Německo", "Almanya", "Tyskland"],
    "FR": ["France", "Francia", "Frankreich", "Frankrijk", "Francja", "Francie", "Fransa", "Frankrike", "Ranska"],
    "NL": ["Netherlands", "Países Bajos", "Pays-Bas", "Niederlande", "Paesi Bassi", "Nederland", "Holandia", "Nizozemsko", "Olanda", "Hollanda", "Nederländerna"],
    "SE": ["Sweden", "Suecia", "Suède", "Schweden", "Svezia", "Zweden", "Szwecja", "Švédsko", "Suedia", "İsveç", "Sverige", "Ruotsi"],
    "IE": ["Ireland", "Irlanda", "Irlande", "Irland", "Ierland", "Irlandia", "Irsko", "İrlanda"],
    "NZ": ["New Zealand", "Nueva Zelanda", "Nouvelle-Zélande", "Neuseeland", "Nuova Zelanda", "Nieuw-Zeeland", "Nowa Zelandia", "Nový Zéland", "Noua Zeelandă", "Yeni Zelanda"],
    "AT": ["Austria", "Autriche", "Österreich", "Oostenrijk", "Avusturya", "Rakousko"],
    "BR": ["Brazil", "Brasil", "Brésil", "Brasilien", "Brasile", "Brazilië", "Brazylia", "Brazílie", "Brezilya"],
    "MX": ["Mexico", "México", "Mexique", "Mexiko", "Messico", "Meksyk", "Mexiko", "Meksika"],
    "ES": ["Spain", "España", "Espagne", "Spanien", "Spagna", "Spanje", "Hiszpania", "Španělsko", "Spania", "İspanya", "Spanien"],
    "PL": ["Poland", "Polonia", "Pologne", "Polen", "Polska", "Polsko", "Polonya"],
    "CZ": ["Czechia", "Czech Republic", "República Checa", "Tchéquie", "Tschechien", "Cechia", "Tsjechië", "Česko", "Česká republika", "Çekya"],
    "RO": ["Romania", "Rumania", "Roumanie", "Rumänien", "România", "Roemenië", "Rumunia", "Rumunsko", "Romanya"],
    "TR": ["Turkey", "Turquía", "Turquie", "Türkei", "Turchia", "Turkije", "Turcja", "Turecko", "Turcia", "Türkiye"],
    "IT": ["Italy", "Italia", "Italie", "Italien", "Italië", "Włochy", "Itálie", "İtalya"],
    "PT": ["Portugal", "Portogallo", "Portugalia", "Portugalsko", "Portekiz"],
    "AR": ["Argentina", "Argentine", "Argentinien", "Argentinië", "Argentyna", "Arjantin"],
    "CO": ["Colombia", "Colombie", "Kolumbien", "Colombie", "Kolumbia", "Kolombiya"],
    "CL": ["Chile", "Chili", "Cile"],
    "PE": ["Peru", "Perú", "Pérou", "Perù"],
    "IN": ["India", "Inde", "Indien", "Indie", "Hindistan"],
    "JP": ["Japan", "Japón", "Japon", "Giappone", "Japonia", "Japonsko", "Japonya", "日本"],
    "KR": ["South Korea", "Corea del Sur", "Corée du Sud", "Südkorea", "Corea del Sud", "Zuid-Korea", "Korea Południowa", "Jižní Korea", "Güney Kore", "한국"],
    "RU": ["Russia", "Rusia", "Russie", "Russland", "Rusland", "Rosja", "Rusko", "Rusya", "Россия"],
    "UA": ["Ukraine", "Ucrania", "Oekraïne", "Ukraina", "Ukrajina", "Ukrayna", "Україна"],
    "IL": ["Israel", "Israël", "Israele", "Izrael", "İsrail", "ישראל"],
    "ZA": ["South Africa", "Sudáfrica", "Afrique du Sud", "Südafrika", "Sudafrica", "Zuid-Afrika", "Güney Afrika"],
    "EG": ["Egypt", "Egipto", "Égypte", "Ägypten", "Egitto", "Egypte", "Mısır", "مصر"],
    "NG": ["Nigeria", "Nigéria", "Nijerya"],
    "KE": ["Kenya", "Kenia", "Keňa"],
    "PH": ["Philippines", "Filipinas", "Filippine", "Filipijnen", "Filipiny", "Filipinler"],
    "ID": ["Indonesia", "Indonésie", "Indonesien", "Indonesië", "Indonezja", "Endonezya"],
    "TH": ["Thailand", "Tailandia", "Thaïlande", "Thailandia", "Tajlandia", "Thajsko", "Tayland", "ไทย"],
    "VN": ["Vietnam", "Việt Nam", "Viêt Nam"],
    "MY": ["Malaysia", "Malasia", "Malaisie", "Malesia", "Maleisië", "Malezja", "Malezya"],
    "SG": ["Singapore", "Singapur", "Singapour", "Singapur"],
    "HK": ["Hong Kong"],
    "FI": ["Finland", "Finlandia", "Finlande", "Finnland", "Suomi"],
    "DK": ["Denmark", "Dinamarca", "Danemark", "Dänemark", "Danimarca", "Denemarken", "Dania", "Dánsko", "Danemarca", "Danimarka", "Danmark"],
    "NO": ["Norway", "Noruega", "Norvège", "Norwegen", "Norvegia", "Noorwegen", "Norwegia", "Norsko", "Norveç", "Norge"],
    "HU": ["Hungary", "Hungría", "Hongrie", "Ungarn", "Ungheria", "Hongarije", "Węgry", "Maďarsko", "Ungaria", "Macaristan", "Magyarország"],
    "GR": ["Greece", "Grecia", "Grèce", "Griechenland", "Griekenland", "Grecja", "Řecko", "Yunanistan", "Ελλάδα"],
    "CN": ["China", "中国", "Chine", "Cina", "Chiny", "Čína", "Çin"],
    "TW": ["Taiwan", "Taiwán", "Taïwan", "台灣"],
}


def _normalize_text(text: str) -> str:
    """Normalize text for accent-insensitive comparison.
    'México' → 'mexico', 'Türkiye' → 'turkiye', 'São Paulo' → 'sao paulo'
    """
    # NFKD decomposition splits accented chars into base + combining mark
    nfkd = unicodedata.normalize('NFKD', text)
    # Strip combining characters (accents, tildes, etc.)
    ascii_text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_text.lower().strip()


# ── Locale-aware aliases for country/month combobox matching ──
# MS Outlook shows names in the browser locale. These aliases let us match
# regardless of language (English, Spanish, German, French, Portuguese, etc.)
COUNTRY_ALIASES = {
    "US": ["United States", "Estados Unidos", "États-Unis", "Vereinigte Staaten", "Stati Uniti", "USA", "US"],
    "GB": ["United Kingdom", "Reino Unido", "Royaume-Uni", "Vereinigtes Königreich", "UK"],
    "CA": ["Canada", "Canadá", "Kanada"],
    "AU": ["Australia", "Australie", "Australien"],
    "DE": ["Germany", "Deutschland", "Allemagne", "Alemania", "Germania"],
    "FR": ["France", "Francia", "Frankreich", "França"],
    "NL": ["Netherlands", "Países Bajos", "Pays-Bas", "Niederlande", "Paesi Bassi"],
    "SE": ["Sweden", "Suecia", "Suède", "Schweden", "Svezia"],
    "IE": ["Ireland", "Irlanda", "Irlande", "Irland"],
    "NZ": ["New Zealand", "Nueva Zelanda", "Nouvelle-Zélande", "Neuseeland"],
    "AT": ["Austria", "Österreich", "Autriche"],
    "BR": ["Brazil", "Brasil", "Brésil", "Brasilien", "Brasile"],
    "MX": ["Mexico", "México", "Mexique", "Mexiko", "Messico"],
    "ES": ["Spain", "España", "Espagne", "Spanien", "Spagna"],
    "PL": ["Poland", "Polonia", "Pologne", "Polen"],
    "CZ": ["Czechia", "Czech Republic", "Chequia", "Tchéquie", "Tschechien", "Česko"],
    "RO": ["Romania", "Rumanía", "Roumanie", "Rumänien"],
    "TR": ["Turkey", "Turquía", "Turquie", "Türkei", "Türkiye"],
    "IT": ["Italy", "Italia", "Italie", "Italien"],
    "PT": ["Portugal"],
    "AR": ["Argentina", "Argentine", "Argentinien"],
    "CO": ["Colombia", "Colombie", "Kolumbien"],
    "CL": ["Chile", "Chili"],
    "PE": ["Peru", "Perú", "Pérou"],
    "IN": ["India", "Inde", "Indien"],
    "JP": ["Japan", "Japón", "Japon", "Giappone"],
    "KR": ["South Korea", "Corea del Sur", "Corée du Sud", "Südkorea"],
    "RU": ["Russia", "Rusia", "Russie", "Russland", "Россия"],
    "UA": ["Ukraine", "Ucrania", "Украина"],
    "IL": ["Israel", "Israël"],
    "ZA": ["South Africa", "Sudáfrica", "Afrique du Sud", "Südafrika"],
    "EG": ["Egypt", "Egipto", "Égypte", "Ägypten"],
    "NG": ["Nigeria", "Nigéria"],
    "KE": ["Kenya", "Kenia"],
    "PH": ["Philippines", "Filipinas"],
    "ID": ["Indonesia", "Indonésie", "Indonesien"],
    "TH": ["Thailand", "Tailandia", "Thaïlande"],
    "VN": ["Vietnam", "Viêt Nam"],
    "MY": ["Malaysia", "Malasia", "Malaisie"],
    "SG": ["Singapore", "Singapur", "Singapour"],
    "HK": ["Hong Kong"],
    "FI": ["Finland", "Finlandia", "Finlande", "Finnland"],
    "DK": ["Denmark", "Dinamarca", "Danemark", "Dänemark"],
    "NO": ["Norway", "Noruega", "Norvège", "Norwegen"],
    "HU": ["Hungary", "Hungría", "Hongrie", "Ungarn"],
    "GR": ["Greece", "Grecia", "Grèce", "Griechenland"],
    "CN": ["China", "Chine"],
    "TW": ["Taiwan", "Taiwán", "Taïwan"],
}

MONTH_ALIASES = {
    1:  ["January", "Enero", "Janvier", "Januar", "Gennaio", "Janeiro", "Januari", "Styczeń", "Ocak", "Январь"],
    2:  ["February", "Febrero", "Février", "Februar", "Febbraio", "Fevereiro", "Februari", "Luty", "Şubat", "Февраль"],
    3:  ["March", "Marzo", "Mars", "März", "Março", "Maart", "Marzec", "Mart", "Март"],
    4:  ["April", "Abril", "Avril", "Aprile", "Kwiecień", "Nisan", "Апрель"],
    5:  ["May", "Mayo", "Mai", "Maggio", "Mei", "Maio", "Maj", "Mayıs", "Май"],
    6:  ["June", "Junio", "Juin", "Juni", "Giugno", "Junho", "Czerwiec", "Haziran", "Июнь"],
    7:  ["July", "Julio", "Juillet", "Juli", "Luglio", "Julho", "Lipiec", "Temmuz", "Июль"],
    8:  ["August", "Agosto", "Août", "Augusti", "Sierpień", "Ağustos", "Август"],
    9:  ["September", "Septiembre", "Septembre", "Settembre", "Setembro", "Wrzesień", "Eylül", "Сентябрь"],
    10: ["October", "Octubre", "Octobre", "Oktober", "Ottobre", "Outubro", "Październik", "Ekim", "Октябрь"],
    11: ["November", "Noviembre", "Novembre", "Novembro", "Listopad", "Kasım", "Ноябрь"],
    12: ["December", "Diciembre", "Décembre", "Dezember", "Dicembre", "Dezembro", "Grudzień", "Aralık", "Декабрь"],
}

async def fluent_combobox_select(page, button_selectors: list[str], value: str, label: str, _log, timeout=5000, aliases: list[str] | None = None):
    """Select a value from a Fluent UI combobox (button[role=combobox] + div[role=listbox]).

    MS signup uses Fluent UI - dropdowns are buttons that open a listbox of div[role=option] items.

    Multi-locale support:
    - `value`: primary value to match (English)
    - `aliases`: optional list of alternative names in other languages
    - Uses accent-normalized comparison ('México' matches 'Mexico')

    Has retry logic: if option not found, closes dropdown, waits, re-opens, retries.
    Uses keyboard search for long lists (e.g. 257 countries).
    """
    MAX_RETRIES = 2  # re-open dropdown and retry if not found

    btn = None
    for sel in button_selectors:
        try:
            if await page.locator(sel).count() > 0:
                btn = sel
                break
        except Exception:
            continue

    if not btn:
        _log(f"[WARN] Fluent combobox '{label}' not found")
        return False

    # Build normalized set of all acceptable values
    all_targets = {_normalize_text(value)}
    if aliases:
        for alias in aliases:
            all_targets.add(_normalize_text(alias))

    for attempt in range(1, MAX_RETRIES + 2):  # attempt 1, 2, 3
        # ── Open dropdown ──
        try:
            await page.locator(btn).first.click(force=True)
            await human_delay(0.3, 0.6)
        except Exception as e:
            try:
                await page.locator(btn).first.evaluate("el => el.click()")
                await human_delay(0.3, 0.6)
            except Exception:
                _log(f"[WARN] Failed to click combobox '{label}': {e}")
                if attempt <= MAX_RETRIES:
                    await human_delay(1, 2)
                    continue
                return False

        # ── Wait for listbox with render delay ──
        try:
            await page.wait_for_selector('[role="listbox"]', timeout=4000)
        except Exception:
            _log(f"[WARN] Listbox for '{label}' did not appear (attempt {attempt})")
            if attempt <= MAX_RETRIES:
                await human_delay(1, 2)
                continue
            return False

        # Extra render delay — options may not be populated yet on slow connections
        await human_delay(0.5, 1.0)

        # ── Try keyboard search first (faster for long lists like 257 countries) ──
        if len(value) >= 2:
            try:
                # Type first 2-3 chars to jump to the right section
                search_chars = value[:min(3, len(value))]
                for ch in search_chars:
                    await page.keyboard.press(ch)
                    await asyncio.sleep(random.uniform(0.08, 0.15))
                await human_delay(0.3, 0.6)

                # Check if the highlighted/focused option matches
                focused = page.locator('[role="option"][aria-selected="true"], [role="option"]:focus, [role="option"].ms-Dropdown-item--selected')
                if await focused.count() > 0:
                    focused_text = (await focused.first.inner_text()).strip()
                    focused_norm = _normalize_text(focused_text)
                    if focused_norm in all_targets or focused_text.lower() == value.lower():
                        await focused.first.click()
                        _log(f"[OK] {label}: selected '{focused_text}' (keyboard search)")
                        await human_delay(0.2, 0.4)
                        return True
            except Exception:
                pass

        options = page.locator('[role="listbox"] [role="option"]')
        count = await options.count()

        # Phase 1: exact match (case-insensitive)
        for i in range(count):
            try:
                text = (await options.nth(i).inner_text()).strip()
                if text.lower() == value.lower():
                    try:
                        await options.nth(i).scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    await options.nth(i).click()
                    _log(f"[OK] {label}: selected '{text}' (exact)")
                    await human_delay(0.2, 0.4)
                    return True
            except Exception:
                continue

        # Phase 2: alias match (accent-normalized, case-insensitive)
        for i in range(count):
            try:
                text = (await options.nth(i).inner_text()).strip()
                normalized = _normalize_text(text)
                if normalized in all_targets:
                    try:
                        await options.nth(i).scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    await options.nth(i).click()
                    _log(f"[OK] {label}: selected '{text}' (alias match)")
                    await human_delay(0.2, 0.4)
                    return True
            except Exception:
                continue

        # Phase 3: startswith match (any alias)
        for i in range(count):
            try:
                text = (await options.nth(i).inner_text()).strip()
                normalized = _normalize_text(text)
                for target in all_targets:
                    if normalized.startswith(target) or target.startswith(normalized):
                        try:
                            await options.nth(i).scroll_into_view_if_needed(timeout=2000)
                        except Exception:
                            pass
                        await options.nth(i).click()
                        _log(f"[OK] {label}: selected '{text}' (partial match)")
                        await human_delay(0.2, 0.4)
                        return True
            except Exception:
                continue

        # Phase 4: numeric index fallback
        try:
            idx = int(value) - 1
            if 0 <= idx < count:
                text = (await options.nth(idx).inner_text()).strip()
                await options.nth(idx).click()
                _log(f"[OK] {label}: selected by index '{text}'")
                await human_delay(0.2, 0.4)
                return True
        except (ValueError, Exception):
            pass

        # ── Not found — close dropdown and retry ──
        _log(f"[WARN] '{value}' not found in '{label}' (attempt {attempt}/{MAX_RETRIES + 1}, {count} options)")
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

        if attempt <= MAX_RETRIES:
            await human_delay(1.0, 2.0)
            # Click somewhere neutral to dismiss any stuck dropdown
            try:
                await page.mouse.click(400, 200)
                await human_delay(0.5, 1.0)
            except Exception:
                pass
            continue

    return False


async def wait_for_any(page, selectors: list[str], timeout: int = 20000) -> str | None:
    """Wait for any of the given selectors to appear. Returns which one appeared."""
    for sel in selectors:
        try:
            if await page.locator(sel).count() > 0:
                vis = await page.locator(sel).first.is_visible()
                if vis:
                    return sel
        except Exception:
            pass

    per_sel_timeout = max(2000, timeout // len(selectors))
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=per_sel_timeout, state="visible")
            if await page.locator(sel).count() > 0:
                return sel
        except Exception:
            pass
    return None


async def step_screenshot(page, step_name: str, username: str = "unknown"):
    """Save a debug screenshot for a registration step."""
    import os
    try:
        os.makedirs("user_data/screenshots", exist_ok=True)
        ts = datetime.utcnow().strftime("%H%M%S")
        path = f"user_data/screenshots/{username}_{step_name}_{ts}.png"
        await page.screenshot(path=path)
        return path
    except Exception:
        return None


async def wait_and_find(page, selectors: list[str], step_name: str, 
                         username: str, _log_fn=None, _err_fn=None,
                         timeout: int = 25000, required: bool = True):
    """
    Wait for any selector, screenshot on failure.
    Returns found selector or None. If required=True and not found, logs error.
    """
    found = await wait_for_any(page, selectors, timeout=timeout)
    if not found and required:
        ss = await step_screenshot(page, f"FAIL_{step_name}", username)
        msg = f"Field not found '{step_name}'. URL: {page.url}"
        if ss and _log_fn:
            _log_fn(f"[SNAP] Screenshot: {ss}")
        if _err_fn:
            _err_fn(msg)
        else:
            logger.error(f"[Birth] {msg}")
    return found


async def detect_and_solve_recaptcha(page, captcha_provider, log_fn=None):
    """
    Universal reCAPTCHA detector + solver with CaptchaChain fallback.
    Supports both CaptchaChain (multi-provider) and single CaptchaProvider.
    Returns True if captcha was solved, False if no captcha found.
    """
    if not captcha_provider:
        return False
    # Check if provider is usable
    is_chain = isinstance(captcha_provider, CaptchaChain)
    if not is_chain and not getattr(captcha_provider, 'api_key', None):
        return False
    if is_chain and not captcha_provider.providers:
        return False

    def _log(msg):
        if log_fn:
            log_fn(msg)
        else:
            logger.info(f"[Captcha] {msg}")

    try:
        recaptcha_iframe = page.locator('iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"]')
        captcha_count = await recaptcha_iframe.count()

        if captcha_count == 0:
            grecaptcha = page.locator('.g-recaptcha, [data-sitekey]')
            captcha_count = await grecaptcha.count()

        if captcha_count == 0:
            return False

        _log("[CAPTCHA] reCAPTCHA detected! Solving...")

        sitekey = None
        try:
            el = page.locator('[data-sitekey]').first
            if await el.count() > 0:
                sitekey = await el.get_attribute('data-sitekey')
        except Exception:
            pass

        if not sitekey:
            try:
                iframe = page.locator('iframe[src*="recaptcha"]').first
                src = await iframe.get_attribute('src') or ""
                if "k=" in src:
                    sitekey = src.split("k=")[1].split("&")[0]
            except Exception:
                pass

        if not sitekey:
            _log("Sitekey not found")
            return False

        _log(f"Sitekey: {sitekey[:20]}...")

        page_url = page.url

        # Use CaptchaChain if available (tries all providers in order)
        if is_chain:
            _log(f"[CHAIN] Solving via CaptchaChain ({len(captcha_provider.providers)} providers)")
            token = await asyncio.to_thread(
                captcha_provider.solve, "recaptcha_v2",
                website_url=page_url, website_key=sitekey
            )
        else:
            token = await asyncio.to_thread(
                captcha_provider.solve_captcha, page_url, sitekey
            )

        if not token:
            _log("[FAIL] All CAPTCHA providers failed")
            return False

        _log("[OK] CAPTCHA solved! Injecting token...")

        await page.evaluate(f"""
            (function() {{
                var textareas = document.querySelectorAll('[id*="g-recaptcha-response"], textarea[name="g-recaptcha-response"]');
                for (var i = 0; i < textareas.length; i++) {{
                    textareas[i].innerHTML = '{token}';
                    textareas[i].value = '{token}';
                    textareas[i].style.display = 'block';
                }}
                if (typeof ___grecaptcha_cfg !== 'undefined') {{
                    var keys = Object.keys(___grecaptcha_cfg.clients);
                    for (var k = 0; k < keys.length; k++) {{
                        try {{
                            var client = ___grecaptcha_cfg.clients[keys[k]];
                            var callback = client && client.rr && client.rr.callback;
                            if (callback) callback('{token}');
                        }} catch(e) {{}}
                    }}
                }}
                if (typeof grecaptcha !== 'undefined' && grecaptcha.enterprise) {{
                    try {{ grecaptcha.enterprise.execute(); }} catch(e) {{}}
                }}
            }})();
        """)

        await human_delay(1, 2)
        return True

    except Exception as e:
        logger.debug(f"Captcha detection error: {e}")
        return False


async def detect_and_solve_funcaptcha(page, captcha_provider, log_fn=None):
    """
    Detect and solve FunCaptcha / Arkose Labs on Yahoo pages.
    Yahoo uses FunCaptcha (NOT reCAPTCHA) after phone submit.
    
    Detection: looks for Arkose iframe, data-pkey, or fc-token.
    Solving: extracts publicKey + surl, sends to CaptchaChain (2captcha first).
    Injection: sets fc-token and triggers callback.
    
    Returns True if FunCaptcha was found + solved, False otherwise.
    """
    if not captcha_provider:
        return False

    is_chain = isinstance(captcha_provider, CaptchaChain)
    if not is_chain and not getattr(captcha_provider, 'api_key', None):
        return False
    if is_chain and not captcha_provider.providers:
        return False

    def _log(msg):
        if log_fn:
            log_fn(msg)
        else:
            logger.info(f"[FunCaptcha] {msg}")

    try:
        # ── Detect FunCaptcha on page ──
        fc_data = await page.evaluate(r"""() => {
            // Method 1: Arkose Labs iframe
            const frames = document.querySelectorAll('iframe[src*="arkoselabs"], iframe[src*="funcaptcha"], iframe[data-e2e="enforcement-frame"]');
            let publicKey = null;
            let surl = null;
            
            for (const f of frames) {
                const src = f.getAttribute('src') || '';
                // Extract public key from URL
                const pkMatch = src.match(/[?&]pkey=([^&]+)/i) || src.match(/\/([A-F0-9-]{36})\//i);
                if (pkMatch) publicKey = pkMatch[1];
                // Extract surl
                const surlMatch = src.match(/[?&]surl=([^&]+)/i);
                if (surlMatch) surl = decodeURIComponent(surlMatch[1]);
                if (!surl) {
                    const urlObj = new URL(src, window.location.href);
                    surl = urlObj.origin;
                }
            }
            
            // Method 2: data-pkey attribute on div
            if (!publicKey) {
                const pkey = document.querySelector('[data-pkey]');
                if (pkey) publicKey = pkey.getAttribute('data-pkey');
            }
            
            // Method 3: fc-token input
            if (!publicKey) {
                const fcToken = document.querySelector('input[name="fc-token"], #fc-token');
                if (fcToken) {
                    const val = fcToken.value || '';
                    const m = val.match(/pk=([^|&]+)/);
                    if (m) publicKey = m[1];
                }
            }
            
            // Method 4: window.__arklabsOptions or similar globals
            if (!publicKey) {
                try {
                    if (window.arkose_public_key) publicKey = window.arkose_public_key;
                    if (window.__arkLabsPublicKey) publicKey = window.__arkLabsPublicKey;
                } catch(e) {}
            }
            
            // Method 5: Script tags
            if (!publicKey) {
                const scripts = document.querySelectorAll('script[src*="arkoselabs"], script[data-pkey]');
                for (const s of scripts) {
                    const pk = s.getAttribute('data-pkey');
                    if (pk) { publicKey = pk; break; }
                    const src = s.getAttribute('src') || '';
                    const m = src.match(/\/([A-F0-9-]{36})\//);
                    if (m) { publicKey = m[1]; break; }
                }
            }
            
            if (!publicKey) return null;
            
            // Extract blob data for MS-specific FunCaptcha
            let blob = null;
            try {
                // Method 1: From enforcement frame data attribute
                const enfFrame = document.querySelector('iframe[data-e2e="enforcement-frame"]');
                if (enfFrame) {
                    const src = enfFrame.getAttribute('src') || '';
                    const blobMatch = src.match(/[?&]blob=([^&]+)/i);
                    if (blobMatch) blob = decodeURIComponent(blobMatch[1]);
                }
                // Method 2: From script/config data
                if (!blob) {
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const txt = s.textContent || '';
                        const m = txt.match(/"blob"\s*:\s*"([^"]+)"/);
                        if (m) { blob = m[1]; break; }
                    }
                }
                // Method 3: From window globals
                if (!blob && window.__arkose_config) {
                    blob = window.__arkose_config.blob || window.__arkose_config.data?.blob;
                }
            } catch(e) {}
            
            return {
                publicKey: publicKey,
                surl: surl || 'https://client-api.arkoselabs.com',
                hasIframe: frames.length > 0,
                blob: blob,
            };
        }""")

        if not fc_data:
            return False

        public_key = fc_data.get("publicKey")
        surl = fc_data.get("surl", "https://client-api.arkoselabs.com")
        blob = fc_data.get("blob") or ""
        _log(f"[FUNCAPTCHA] Detected! publicKey={public_key[:20]}... surl={surl}" + (f" blob={blob[:30]}..." if blob else ""))

        page_url = page.url

        # ── Solve via CaptchaChain (2captcha first for FunCaptcha) ──
        if is_chain:
            _log(f"[CHAIN] Solving FunCaptcha via CaptchaChain ({len(captcha_provider.providers)} providers)")
            token = await asyncio.to_thread(
                captcha_provider.solve, "funcaptcha",
                public_key=public_key, page_url=page_url, surl=surl, data_blob=blob
            )
        elif hasattr(captcha_provider, 'solve_funcaptcha'):
            token = await asyncio.to_thread(
                captcha_provider.solve_funcaptcha, public_key, page_url, surl, blob
            )
        else:
            _log("[WARN] Captcha provider doesn't support FunCaptcha")
            return False

        if not token:
            _log("[FAIL] FunCaptcha solve failed - all providers returned None")
            return False

        _log(f"[OK] FunCaptcha solved! Token: {token[:50]}...")

        # ── Inject token into page ──
        injected = await page.evaluate(f"""() => {{
            // Method 1: Set fc-token input
            const fcInput = document.querySelector('input[name="fc-token"], #fc-token');
            if (fcInput) {{
                fcInput.value = '{token}';
                fcInput.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
            
            // Method 2: Call Arkose callback
            try {{
                if (typeof window.ArkoseEnforcement !== 'undefined') {{
                    window.ArkoseEnforcement.setConfig({{data: {{token: '{token}'}}}});
                }}
            }} catch(e) {{}}
            
            // Method 3: Trigger form callbacks
            try {{
                if (typeof window.__arkoseCallback === 'function') {{
                    window.__arkoseCallback('{token}');
                }}
            }} catch(e) {{}}
            
            // Method 4: Yahoo-specific - find and call verification callback
            try {{
                const evt = new CustomEvent('arkose-complete', {{detail: {{token: '{token}'}}}});
                document.dispatchEvent(evt);
            }} catch(e) {{}}
            
            return !!fcInput;
        }}""")

        _log(f"[OK] Token injected (fcInput found: {injected})")
        await human_delay(2, 4)

        # Try submitting the form after token injection
        try:
            submit_btn = await wait_for_any(page, [
                'button[type="submit"]',
                'button:has-text("Verify")',
                'button:has-text("Continue")',
                'button:has-text("Next")',
            ], timeout=3000)
            if submit_btn:
                await human_click(page, submit_btn)
                _log("Clicked submit after FunCaptcha solve")
                await human_delay(3, 6)
        except Exception:
            pass

        return True

    except Exception as e:
        logger.debug(f"FunCaptcha detection error: {e}")
        return False


# Phone country code mappings used by Yahoo/AOL SMS verification
PHONE_COUNTRY_MAP = {
    "ru": "7", "ua": "380", "kz": "7", "cn": "86", "ph": "63", "id": "62",
    "my": "60", "ke": "254", "tz": "255", "br": "55", "us": "1", "us_v": "1",
    "il": "972", "hk": "852", "pl": "48", "uk": "44", "ng": "234", "eg": "20",
    "in": "91", "ie": "353", "za": "27", "ro": "40", "co": "57", "ee": "372",
    "ca": "1", "de": "49", "nl": "31", "at": "43", "th": "66", "mx": "52",
    "es": "34", "tr": "90", "cz": "420", "pe": "51", "nz": "64", "se": "46",
    "fr": "33", "ar": "54", "vn": "84", "bd": "880", "pk": "92", "cl": "56",
    "be": "32", "bg": "359", "hu": "36", "it": "39", "pt": "351", "gr": "30",
    "fi": "358", "dk": "45", "no": "47", "ch": "41", "au": "61", "jp": "81",
    "ge": "995", "ae": "971", "sa": "966", "cr": "506", "gt": "502", "sk": "421",
    "am": "374", "az": "994", "by": "375", "md": "373", "al": "355", "rs": "381",
    "hr": "385", "si": "386", "lv": "371", "lt": "370", "uy": "598", "bo": "591",
}

COUNTRY_TO_ISO2 = {
    "ru": "RU", "ua": "UA", "kz": "KZ", "cn": "CN", "ph": "PH", "id": "ID",
    "my": "MY", "ke": "KE", "tz": "TZ", "br": "BR", "us": "US", "us_v": "US",
    "il": "IL", "hk": "HK", "pl": "PL", "uk": "GB", "ng": "NG", "eg": "EG",
    "in": "IN", "ie": "IE", "za": "ZA", "ro": "RO", "co": "CO", "ee": "EE",
    "ca": "CA", "de": "DE", "nl": "NL", "at": "AT", "th": "TH", "mx": "MX",
    "es": "ES", "tr": "TR", "cz": "CZ", "pe": "PE", "nz": "NZ", "se": "SE",
    "fr": "FR", "ar": "AR", "vn": "VN", "bd": "BD", "pk": "PK", "cl": "CL",
    "be": "BE", "bg": "BG", "hu": "HU", "it": "IT", "pt": "PT", "gr": "GR",
    "fi": "FI", "dk": "DK", "no": "NO", "ch": "CH", "au": "AU", "jp": "JP",
    "ge": "GE", "ae": "AE", "sa": "SA", "cr": "CR", "gt": "GT", "sk": "SK",
    "am": "AM", "az": "AZ", "by": "BY", "md": "MD", "al": "AL", "rs": "RS",
    "hr": "HR", "si": "SI", "lv": "LV", "lt": "LT", "uy": "UY", "bo": "BO",
}

# Reverse map: phone prefix → SMS country code (e.g. "353" → "ie")
PREFIX_TO_SMS_COUNTRY = {v: k for k, v in PHONE_COUNTRY_MAP.items() if k != "us_v"}


# ═══════════════════════════════════════════════════════════
#  Phase 2: Shared Defense Infrastructure
#  Error Taxonomy, Block Scanner, Rate Limiter, Session Clean
# ═══════════════════════════════════════════════════════════

import time
from dataclasses import dataclass, field as dc_field
from typing import Optional


# ── Step 5: Error Taxonomy ──────────────────────────────────


class RegistrationError(Exception):
    """Base class for all registration errors with structured codes."""
    category = "UNKNOWN"
    default_action = "abort"

    def __init__(self, code: str, message: str, screenshot_path: str = None):
        self.code = code
        self.message = message
        self.screenshot_path = screenshot_path
        super().__init__(f"[{code}] {message}")

    @property
    def action(self):
        """Convenience alias for default_action."""
        return self.default_action


class RecoverableError(RegistrationError):
    """E1xx: Retry the same step (selector not found, timeout, etc.)"""
    category = "RECOVERABLE"
    default_action = "retry"


class RateLimitError(RegistrationError):
    """E2xx: Backoff and rotate IP (too many attempts, 429, etc.)"""
    category = "RATE_LIMITED"
    default_action = "backoff"

    def __init__(self, code: str, message: str, cooldown_sec: int = 60, **kwargs):
        super().__init__(code, message, **kwargs)
        self.cooldown_sec = cooldown_sec


class BannedIPError(RegistrationError):
    """E3xx: Mark IP as burned, get new proxy (suspicious activity, block page)"""
    category = "BANNED_IP"
    default_action = "skip_ip"


class CaptchaFailError(RegistrationError):
    """E4xx: Retry CAPTCHA solver chain (solver timeout, wrong answer)"""
    category = "CAPTCHA_FAIL"
    default_action = "retry_captcha"


class FatalError(RegistrationError):
    """E5xx: Abort thread, log detailed report (provider changed flow, unknown page)"""
    category = "FATAL"
    default_action = "abort"


@dataclass
class RegContext:
    """Registration context passed through all steps of a provider flow."""
    provider: str           # "yahoo", "aol", "outlook", "protonmail", "gmail"
    username: str = ""
    password: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    proxy_ip: str = ""      # IP:port of proxy (for rate_limiter)
    proxy_geo: str = ""     # ISO2 country code from proxy (e.g. "US")
    proxy_type: str = ""    # "residential", "mobile", "datacenter", "isp"
    language: str = "en"    # Expected page language based on GEO
    thread_id: int = 0
    attempt: int = 0        # Current attempt number (0-based)
    max_retries: int = 3
    _log: object = None     # Logging function
    _err: object = None     # Error logging function
    _arkose_blob: str = ""  # FunCaptcha blob captured from Arkose Labs API
    # ── State machine tracking (Part 5) ──
    current_step: str = ""          # Name of the current step being executed
    step_times: dict = field(default_factory=dict)  # step_name -> elapsed seconds

# ── Safe Screenshot (never throws) ──────────────────────────────────────────────────


async def _safe_screenshot(page, name: str, log_fn=None):
    """Take debug screenshot — guaranteed to never throw.
    Use this before raising exceptions to capture page state."""
    try:
        await debug_screenshot(page, name, log_fn)
    except Exception:
        try:
            logger.debug(f"Screenshot failed for {name}")
        except Exception:
            pass


# ── State Machine Dispatcher ───────────────────────────────────────────────────


async def run_flow_machine(page, ctx: RegContext, steps: list,
                           cancel_event=None):
    """
    Execute a list of registration steps with:
    - Auto-screenshot on ANY error (before re-raising)
    - Step timing logged to ctx.step_times
    - Cancel event checking between steps
    - Consistent error logging

    Args:
        page: Playwright page object
        ctx: RegContext with _log/_err functions
        steps: list of (step_name, async_fn, args_tuple)
               e.g. [("warmup", step_0_warmup, (ctx,)), ...]
        cancel_event: threading.Event — if set, abort early

    Returns: True if all steps completed, None if cancelled.
    Raises: RegistrationError subclasses (with auto-screenshot).
    """
    for step_name, step_fn, step_args in steps:
        # Check cancel
        if cancel_event and cancel_event.is_set():
            if ctx._log:
                ctx._log(f"[CANCEL] Aborted before {step_name}")
            return None

        ctx.current_step = step_name
        start_time = time.time()

        try:
            await step_fn(page, *step_args)
            elapsed = time.time() - start_time
            ctx.step_times[step_name] = round(elapsed, 1)
            if ctx._log:
                ctx._log(f"[STEP] {step_name} OK ({elapsed:.1f}s)")

        except RegistrationError:
            # Known error — screenshot and re-raise
            elapsed = time.time() - start_time
            ctx.step_times[step_name] = round(elapsed, 1)
            await _safe_screenshot(page, f"{ctx.provider}_{step_name}_error", ctx._log)
            raise

        except asyncio.CancelledError:
            # Task cancelled — screenshot but don't wrap
            await _safe_screenshot(page, f"{ctx.provider}_{step_name}_cancelled", ctx._log)
            raise

        except Exception as e:
            # Unknown error — screenshot + wrap in FatalError
            elapsed = time.time() - start_time
            ctx.step_times[step_name] = round(elapsed, 1)
            await _safe_screenshot(page, f"{ctx.provider}_{step_name}_crash", ctx._log)
            if ctx._err:
                ctx._err(f"[CRASH] {step_name}: {str(e)[:300]}")
            raise FatalError("E599", f"{step_name}: {str(e)[:200]}")

    return True


# ── Defensive Coding Template Helpers ────────────────────────────────────────


async def verify_page_state(page, url_pattern: str = None, selector: str = None,
                            timeout: int = 3000) -> bool:
    """
    Pre-check: verify we're on the expected page before acting.

    Args:
        page: Playwright page object
        url_pattern: substring that must be in page.url (e.g. "signup")
        selector: CSS selector that must be visible on page
        timeout: max ms to wait for selector

    Returns: True if page state is valid, False otherwise.
    """
    if url_pattern:
        current = (page.url or "").lower()
        if url_pattern.lower() not in current:
            return False
    if selector:
        try:
            el = page.locator(selector).first
            await el.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False
    return True


async def block_check(page, provider: str, ctx: RegContext = None,
                      step_name: str = ""):
    """
    Scan for block signals and raise appropriate error if detected.
    Call this BEFORE each registration step.

    Raises: BannedIPError or RateLimitError if block detected.
    """
    lang = ctx.language if ctx else "en"
    result = await scan_for_block_signals(page, provider, lang)
    if result["detected"]:
        log_fn = ctx._err if ctx and ctx._err else logger.warning
        log_fn(f"[BLOCK@{step_name}] {result['reason']}")
        await debug_screenshot(page, f"{provider}_{step_name}_blocked")
        if result["action"] == "skip_ip":
            raise BannedIPError("E302", f"{step_name}: {result['reason']}")
        elif result["action"] == "backoff":
            raise RateLimitError("E201", f"{step_name}: {result['reason']}")
        else:
            # Low severity — log but don't crash
            if ctx and ctx._log:
                ctx._log(f"[WARN@{step_name}] {result['reason']}")


async def run_step(page, ctx: RegContext, step_name: str,
                   action_fn, *,
                   url_pattern: str = None,
                   expected_selector: str = None,
                   error_selector: str = None,
                   screenshot: bool = False):
    """
    Universal step wrapper implementing the Defensive Coding Template.

    Pattern:
        1. Pre-check: verify page state
        2. Block scan: detect rate limits / IP bans
        3. Action: execute the step (human_fill, human_click, etc.)
        4. Post-check: look for error messages
        5. Screenshot: capture success state

    Args:
        page: Playwright page
        ctx: Registration context
        step_name: e.g. "fill_email", "enter_password"
        action_fn: async callable that performs the step action
        url_pattern: expected URL substring (for pre-check)
        expected_selector: expected selector on page (for pre-check)
        error_selector: CSS selector for error message element (for post-check)
        screenshot: whether to take success screenshot

    Raises:
        FatalError: if page state is wrong
        BannedIPError/RateLimitError: if block detected
        RecoverableError: if error message shown after action
    """
    log = ctx._log or logger.info
    err = ctx._err or logger.error

    # 1. Pre-check
    if url_pattern or expected_selector:
        valid = await verify_page_state(page, url_pattern, expected_selector)
        if not valid:
            await debug_screenshot(page, f"{ctx.provider}_{step_name}_wrong_page")
            raise FatalError("E501", f"Wrong page state at {step_name} (url={page.url})")

    # 2. Block scan
    await block_check(page, ctx.provider, ctx, step_name)

    # 3. Action
    ctx.attempt += 1
    log(f"[Step:{step_name}] attempt={ctx.attempt}")
    result = await action_fn()

    # 4. Post-check
    if error_selector:
        try:
            err_el = page.locator(error_selector).first
            if await err_el.is_visible(timeout=2000):
                err_text = (await err_el.text_content() or "").strip()
                if err_text:
                    await debug_screenshot(page, f"{ctx.provider}_{step_name}_error")
                    raise RecoverableError("E102", f"{step_name}: {err_text}")
        except RecoverableError:
            raise
        except Exception:
            pass  # No error element = good

    # 5. Screenshot success
    if screenshot:
        await debug_screenshot(page, f"{ctx.provider}_{step_name}_ok")

    return result


# ── Step 6: Block Signal Scanner + GEO Mapper ──────────────


# Error phrases per provider + language
_BLOCK_SIGNALS = {
    "universal": {
        "en": [
            "something went wrong", "try again later", "suspicious activity",
            "temporarily unavailable", "too many attempts", "access denied",
            "unable to process", "service unavailable", "blocked",
            "unusual activity", "verify your identity", "account locked",
            "we couldn't complete", "request couldn't be processed",
        ],
        "es": [
            "algo salió mal", "inténtalo más tarde", "actividad sospechosa",
            "temporalmente no disponible", "demasiados intentos", "acceso denegado",
            "no se pudo procesar", "bloqueado", "actividad inusual",
        ],
        "pt": [
            "algo deu errado", "tente novamente mais tarde", "atividade suspeita",
            "temporariamente indisponível", "muitas tentativas", "acesso negado",
            "bloqueado", "atividade incomum",
        ],
        "de": [
            "etwas schief gelaufen", "versuchen sie es später", "verdächtige aktivität",
            "zu viele versuche", "zugriff verweigert", "blockiert",
        ],
        "ru": [
            "что-то пошло не так", "попробуйте позже", "подозрительная активность",
            "слишком много попыток", "доступ запрещён", "заблокировано",
        ],
    },
    "yahoo": {
        "en": [
            "not available in your region", "we are unable",
            "error 500", "challenge/fail",
        ],
    },
    "outlook": {
        "en": [
            "we need to verify", "prove you're not a robot",
            "your account has been locked", "help us protect your account",
        ],
    },
    "gmail": {
        "en": [
            "this phone number cannot be used for verification",
            "couldn't create your account", "this account is not eligible",
            "phone number has been used too many times",
        ],
    },
    "protonmail": {
        "en": [
            "human verification required", "too many account creation attempts",
            "please try again later",
        ],
    },
}

# URL patterns that indicate a block/error
_BLOCK_URL_PATTERNS = {
    "universal": ["/error", "/blocked", "/sorry", "/challenge/fail"],
    "yahoo": ["guce.yahoo", "consent.yahoo"],
    "outlook": ["account.live.com/recover", "account.live.com/identity"],
    "gmail": ["accounts.google.com/speedbump", "accounts.google.com/challenge"],
    "protonmail": [],
    "webde": [],
}


async def scan_for_block_signals(page, provider: str, language: str = "en"):
    """
    Universal block/error detector. Checks page text + URL for block signals.

    Returns dict: {detected: bool, reason: str, action: str, severity: str}
    Actions: "retry", "backoff", "skip_ip", "abort"
    """
    result = {"detected": False, "reason": "", "action": "continue", "severity": "none"}

    url = (page.url or "").lower()

    # 1. Check URL patterns
    url_patterns = _BLOCK_URL_PATTERNS.get("universal", []) + _BLOCK_URL_PATTERNS.get(provider, [])
    for pattern in url_patterns:
        if pattern in url:
            result["detected"] = True
            result["reason"] = f"Block URL: {pattern}"
            result["action"] = "skip_ip"
            result["severity"] = "high"
            return result

    # 2. Check page text
    try:
        body_text = await page.evaluate("""() => {
            return (document.body?.innerText?.substring(0, 3000) || '').toLowerCase();
        }""")
    except Exception:
        return result

    # Check universal + provider-specific + language-specific phrases
    all_phrases = []
    for lang in [language, "en"]:  # Check requested language + English fallback
        all_phrases.extend(_BLOCK_SIGNALS.get("universal", {}).get(lang, []))
        all_phrases.extend(_BLOCK_SIGNALS.get(provider, {}).get(lang, []))
    # Deduplicate
    all_phrases = list(set(all_phrases))

    for phrase in all_phrases:
        if phrase in body_text:
            result["detected"] = True
            result["reason"] = f"Block text: '{phrase}'"
            # Determine severity by phrase
            if any(w in phrase for w in ["too many", "rate", "demasiados", "muitas", "слишком"]):
                result["action"] = "backoff"
                result["severity"] = "medium"
            elif any(w in phrase for w in ["suspicious", "blocked", "banned", "locked",
                                            "sospechosa", "bloqueado", "заблокировано"]):
                result["action"] = "skip_ip"
                result["severity"] = "high"
            else:
                result["action"] = "retry"
                result["severity"] = "low"
            return result

    return result


# ── Step 6b: GEO-Language Mapper ──


_GEO_TO_LANGUAGE = {
    "US": "en", "GB": "en", "CA": "en", "AU": "en", "NZ": "en", "IE": "en",
    "ES": "es", "MX": "es", "AR": "es", "CO": "es", "CL": "es", "PE": "es",
    "BR": "pt", "PT": "pt",
    "DE": "de", "AT": "de", "CH": "de",
    "FR": "fr", "BE": "fr",
    "RU": "ru", "UA": "ru", "KZ": "ru", "BY": "ru",
    "IT": "it", "NL": "nl", "PL": "pl", "TR": "tr", "JP": "ja",
    "CN": "zh", "KR": "ko", "TH": "th", "VN": "vi", "ID": "id",
}


def get_expected_language(proxy_geo: str) -> str:
    """Map proxy country (ISO2) to expected page language."""
    if not proxy_geo:
        return "en"
    return _GEO_TO_LANGUAGE.get(proxy_geo.upper(), "en")


def get_error_keywords(provider: str, language: str = "en") -> list:
    """Get all error keywords for a provider + language combo."""
    keywords = []
    keywords.extend(_BLOCK_SIGNALS.get("universal", {}).get(language, []))
    keywords.extend(_BLOCK_SIGNALS.get("universal", {}).get("en", []))  # Always include EN
    keywords.extend(_BLOCK_SIGNALS.get(provider, {}).get(language, []))
    keywords.extend(_BLOCK_SIGNALS.get(provider, {}).get("en", []))
    return list(set(keywords))


# ── Step 7: Rate Limiter ──────────────────────────────────


class RateLimitTracker:
    """
    Per-provider, per-IP rate limit tracking with exponential backoff.
    Thread-safe via simple dict operations (GIL protects).

    Usage:
        tracker = RateLimitTracker()
        if not tracker.can_proceed("yahoo", "1.2.3.4"):
            wait_time = tracker.get_wait_time("yahoo", "1.2.3.4")
            # skip this IP or wait
        tracker.record_attempt("yahoo", "1.2.3.4", success=True)
        tracker.record_block("yahoo", "1.2.3.4", cooldown_sec=120)
    """

    # Backoff stages: 30s → 2min → 10min → burned
    BACKOFF_STAGES = [30, 120, 600]
    MAX_FAILS_BEFORE_BURN = 3

    def __init__(self):
        # {(provider, ip): {"fails": int, "last_block": float, "burned": bool, "stage": int}}
        self._state = {}

    def _key(self, provider: str, ip: str) -> tuple:
        return (provider, ip or "unknown")

    def can_proceed(self, provider: str, ip: str) -> tuple:
        """Check if we can make a registration attempt. Returns (can_go: bool, wait_seconds: float)."""
        key = self._key(provider, ip)
        state = self._state.get(key)
        if not state:
            return (True, 0)
        if state.get("burned"):
            return (False, -1)
        last_block = state.get("last_block", 0)
        stage = state.get("stage", 0)
        if stage >= len(self.BACKOFF_STAGES):
            return (False, -1)  # Exhausted all stages
        cooldown = self.BACKOFF_STAGES[min(stage, len(self.BACKOFF_STAGES) - 1)]
        elapsed = time.time() - last_block
        if elapsed >= cooldown:
            return (True, 0)
        return (False, cooldown - elapsed)

    def get_wait_time(self, provider: str, ip: str) -> int:
        """Get seconds to wait before next attempt. Returns 0 if can proceed."""
        key = self._key(provider, ip)
        state = self._state.get(key)
        if not state:
            return 0
        if state.get("burned"):
            return -1  # -1 = permanently burned
        last_block = state.get("last_block", 0)
        stage = state.get("stage", 0)
        if stage >= len(self.BACKOFF_STAGES):
            return -1
        cooldown = self.BACKOFF_STAGES[min(stage, len(self.BACKOFF_STAGES) - 1)]
        remaining = cooldown - (time.time() - last_block)
        return max(0, int(remaining))

    def record_attempt(self, provider: str, ip: str, success: bool):
        """Record a registration attempt result."""
        key = self._key(provider, ip)
        if success:
            # Reset on success
            self._state.pop(key, None)

    def record_success(self, provider: str, ip: str):
        """Alias: record successful attempt, resets backoff state."""
        self.record_attempt(provider, ip, success=True)

    def record_block(self, provider: str, ip: str, cooldown_sec: int = 0):
        """Record that this IP was blocked/rate-limited by provider."""
        key = self._key(provider, ip)
        state = self._state.get(key, {"fails": 0, "last_block": 0, "burned": False, "stage": 0})
        state["fails"] = state.get("fails", 0) + 1
        state["last_block"] = time.time()
        state["stage"] = state.get("stage", 0) + 1
        if state["fails"] >= self.MAX_FAILS_BEFORE_BURN:
            state["burned"] = True
            logger.warning(f"[RateLimit] IP burned: {provider}/{ip} after {state['fails']} blocks")
        self._state[key] = state

    def is_burned(self, provider: str, ip: str) -> bool:
        """Check if IP is permanently burned for this provider."""
        key = self._key(provider, ip)
        return self._state.get(key, {}).get("burned", False)

    def reset(self, provider: str = None, ip: str = None):
        """Reset rate limit state. If both None, resets everything."""
        if provider and ip:
            self._state.pop(self._key(provider, ip), None)
        elif provider:
            self._state = {k: v for k, v in self._state.items() if k[0] != provider}
        else:
            self._state.clear()


# Global singleton — shared across all threads
rate_limiter = RateLimitTracker()


# ── Step 7b: Session Sanitizer ──


async def clean_session(context):
    """
    Clear cookies, localStorage, sessionStorage between registration attempts.
    Prevents cross-attempt fingerprint leakage.
    """
    try:
        await context.clear_cookies()
    except Exception:
        pass
    try:
        # Clear localStorage and sessionStorage via JS on all pages
        for page in context.pages:
            try:
                await page.evaluate("""() => {
                    try { localStorage.clear(); } catch(e) {}
                    try { sessionStorage.clear(); } catch(e) {}
                }""")
            except Exception:
                pass
    except Exception:
        pass
