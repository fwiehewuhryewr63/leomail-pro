"""
Leomail v3 - Birth Helpers
Shared utility functions for all provider registration engines.
"""
import asyncio
import random
from datetime import datetime
from pathlib import Path
from loguru import logger

from ...config import load_config, get_api_key
from ...services.captcha_provider import CaptchaProvider
from ...services.sms_provider import GrizzlySMS
from ...services.simsms_provider import SimSmsProvider
from ...services.fivesim_provider import FiveSimProvider


DEBUG_SCREENSHOT_DIR = str(Path(__file__).resolve().parent.parent.parent / "user_data" / "debug_screenshots")

# ── Auto-export file for market-format accounts ──
ACCOUNTS_EXPORT_FILE = Path(__file__).resolve().parent.parent.parent / "user_data" / "accounts_export.txt"


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


# SMS provider priority for fallback chain
SMS_FALLBACK_ORDER = ["simsms", "grizzly", "5sim"]


def get_sms_chain(primary: str) -> list:
    """Return ordered list of SMS providers: primary first, then fallbacks.
    Only includes providers that have an API key configured."""
    chain = []
    # Primary first
    p = get_sms_provider(primary)
    if p:
        chain.append((primary, p))
    # Then fallbacks in order
    for name in SMS_FALLBACK_ORDER:
        if name == primary:
            continue
        fb = get_sms_provider(name)
        if fb:
            chain.append((name, fb))
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

# Priority order when no specific country detected
COUNTRY_FALLBACK_PRIORITY = [
    "us", "uk", "de", "nl", "se", "pl", "br", "ca", "fr",
    "es", "ru", "it", "at", "cz", "ee", "ro", "ie", "ua", "il",
]


async def scrape_phone_dropdown(page, _log=None) -> list[str]:
    """
    Scrape Yahoo/AOL phone country dropdown to get available phone prefixes.
    Returns list of phone prefixes (e.g. ["1", "44", "55"]).
    """
    try:
        prefixes = await page.evaluate("""() => {
            const prefixes = [];
            // Method 1: <select> options with country codes
            const selects = document.querySelectorAll('select');
            for (const sel of selects) {
                for (const opt of sel.options) {
                    const m = opt.text.match(/\\+(\\d{1,4})/);
                    if (m) prefixes.push(m[1]);
                    const vm = (opt.value || '').match(/^(\\d{1,4})$/);
                    if (vm) prefixes.push(vm[1]);
                }
            }
            // Method 2: data attributes or list items
            if (prefixes.length === 0) {
                const items = document.querySelectorAll('[data-code], [data-country-code], li[role="option"]');
                for (const el of items) {
                    const code = el.getAttribute('data-code') || el.getAttribute('data-country-code') || '';
                    if (code) prefixes.push(code);
                    const m = el.textContent.match(/\\+(\\d{1,4})/);
                    if (m) prefixes.push(m[1]);
                }
            }
            return [...new Set(prefixes)];
        }""")
        if prefixes and _log:
            _log(f"Dropdown: {len(prefixes)} countries (examples: +{', +'.join(prefixes[:5])})")
        return prefixes or []
    except Exception as e:
        if _log:
            _log(f"Dropdown scraping failed: {e}")
        return []


# ── SMS Exponential Backoff Tracker ──
# Prevents hammering SMS providers when they're down
_sms_backoff = {}  # {service: {"fails": int, "last_fail": float}}
_SMS_BACKOFF_BASE = 10    # seconds
_SMS_BACKOFF_MAX = 120    # max seconds


def _get_sms_backoff_delay(service: str) -> float:
    """Get current backoff delay for a service. Returns 0 if no backoff needed."""
    import time
    info = _sms_backoff.get(service)
    if not info or info["fails"] == 0:
        return 0
    delay = min(_SMS_BACKOFF_BASE * (2 ** (info["fails"] - 1)), _SMS_BACKOFF_MAX)
    # Check if enough time passed since last fail
    elapsed = time.time() - info.get("last_fail", 0)
    remaining = delay - elapsed
    return max(0, remaining)


def _record_sms_fail(service: str):
    """Record an SMS ordering failure for backoff calculation."""
    import time
    if service not in _sms_backoff:
        _sms_backoff[service] = {"fails": 0, "last_fail": 0}
    _sms_backoff[service]["fails"] += 1
    _sms_backoff[service]["last_fail"] = time.time()
    logger.debug(f"SMS backoff [{service}]: fails={_sms_backoff[service]['fails']}")


def _reset_sms_backoff(service: str):
    """Reset backoff after successful SMS order."""
    _sms_backoff[service] = {"fails": 0, "last_fail": 0}
    logger.debug(f"SMS backoff [{service}]: reset")


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
    Universal SMS ordering with auto-intelligence:
    1. Auto-detect country from proxy geo / page dropdown / fallback priority
    2. Try all configured SMS providers in chain order
    3. Zero user input required

    Args:
        service: "yahoo", "aol", "gmail", "outlook"
        sms_provider: primary SMS provider instance
        proxy_geo: ISO2 country code from proxy (e.g. "BR", "US")
        page: Playwright page for dropdown scraping (Yahoo/AOL only)
        scrape_dropdown: whether to scrape phone country dropdown (False for Gmail)
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

    if not sms_provider:
        _err(f"{service.upper()} requires SMS but no SMS provider configured")
        return None, None, []

    # Exponential backoff - wait if previous attempts failed
    backoff_delay = _get_sms_backoff_delay(service)
    if backoff_delay > 0:
        _log(f"[WAIT] SMS backoff: waiting {backoff_delay:.0f}с before ordering ({_sms_backoff.get(service, {}).get('fails', 0)} consecutive fails)")
        await asyncio.sleep(backoff_delay)

    # ── Step 1: Build ordered country list ──
    detected_country = None  # from page dropdown
    expanded_countries = []

    # Priority 1: proxy GEO (MUST match for Gmail, should match for Yahoo/AOL)
    if proxy_geo:
        proxy_sms = ISO2_TO_SMS_COUNTRY.get(proxy_geo.upper())
        if proxy_sms:
            expanded_countries.append(proxy_sms)
            _log(f"Proxy geo {proxy_geo} -> SMS country: {proxy_sms}")

    # Priority 2: dropdown scraping (Yahoo/AOL - detect page's displayed country)
    dropdown_countries = []
    if scrape_dropdown and page:
        prefixes = await scrape_phone_dropdown(page, _log)
        if prefixes:
            # Find which prefix the page currently shows (first in dropdown = current)
            for prefix in prefixes[:3]:
                cc = PREFIX_TO_SMS_COUNTRY.get(prefix)
                if cc:
                    if not detected_country:
                        detected_country = cc
                    if cc not in dropdown_countries:
                        dropdown_countries.append(cc)
            # Add all dropdown countries
            for prefix in prefixes:
                cc = PREFIX_TO_SMS_COUNTRY.get(prefix)
                if cc and cc not in dropdown_countries:
                    dropdown_countries.append(cc)
            _log(f"Dropdown countries: {dropdown_countries[:10]}...")

    # Merge: detected first (if matches proxy), then proxy, then dropdown, then fallback
    if detected_country and detected_country not in expanded_countries:
        expanded_countries.insert(0, detected_country)

    for c in dropdown_countries:
        if c not in expanded_countries:
            expanded_countries.append(c)

    # Priority 3: fallback countries (if we have < 3 options)
    if len(expanded_countries) < 3:
        for c in COUNTRY_FALLBACK_PRIORITY:
            if c not in expanded_countries:
                expanded_countries.append(c)

    _log(f"SMS countries (priority): {expanded_countries[:8]}...")

    # ── Step 2: Build provider chain ──
    _cls = type(sms_provider).__name__.lower()
    if 'grizzly' in _cls:
        _primary = 'grizzly'
    elif 'fivesim' in _cls or '5sim' in _cls:
        _primary = '5sim'
    else:
        _primary = 'simsms'

    sms_chain = get_sms_chain(_primary)
    if not sms_chain:
        sms_chain = [("primary", sms_provider)]

    # ── Step 3: Try each provider with expanded country list ──
    for provider_name, provider in sms_chain:
        _log(f"[SMS] Trying SMS: {provider_name}")

        # Method 1: order_number_from_countries (tries all countries internally)
        if hasattr(provider, 'order_number_from_countries'):
            try:
                order = await asyncio.to_thread(
                    provider.order_number_from_countries, service, expanded_countries
                )
                if order and "error" not in order:
                    _log(f"[OK] {provider_name}: number from {order.get('country', '?')} - {order.get('number', '')}")
                    _reset_sms_backoff(service)
                    return order, provider, expanded_countries
                _log(f"{provider_name} from_countries: {order.get('error', '') if order else 'empty'}")
            except Exception as e:
                _log(f"{provider_name} from_countries error: {e}")

        # Method 2: try countries one by one
        for country in expanded_countries[:5]:
            try:
                order = await asyncio.to_thread(provider.order_number, service, country)
                if order and "error" not in order:
                    _log(f"[OK] {provider_name}: number from {order.get('country', '?')} - {order.get('number', '')}")
                    _reset_sms_backoff(service)
                    return order, provider, expanded_countries
            except Exception as e:
                _log(f"{provider_name}/{country}: {e}")

        _log(f"[FAIL] {provider_name}: all countries exhausted")

    _record_sms_fail(service)
    _err(f"Failed to order SMS from any provider for {service} (next attempt in {_get_sms_backoff_delay(service):.0f}с)")
    return None, None, expanded_countries


async def order_sms_retry(
    service: str,
    active_provider,
    expanded_countries: list,
    used_numbers: set = None,
    _log=None,
) -> dict | None:
    """
    Retry SMS order after rejection (wrong code, number rejected by provider).
    Uses the same provider and expanded country list, skipping already-used numbers.

    Returns order_dict or None.
    """
    if not _log:
        _log = lambda msg: logger.info(msg)

    if not active_provider:
        _log("Retry: no active SMS provider")
        return None

    if not used_numbers:
        used_numbers = set()

    _log(f"[RETRY] Retry SMS order for {service}...")

    # Try from expanded countries
    for country in expanded_countries[:8]:
        try:
            order = await asyncio.to_thread(active_provider.order_number, service, country)
            if order and "error" not in order:
                number = order.get("number", "")
                if number in used_numbers:
                    _log(f"Number {number} already used, skipping")
                    continue
                _log(f"[OK] Retry: number from {country} - {number}")
                return order
        except Exception as e:
            _log(f"Retry {country}: {e}")

    _log("[FAIL] Retry: all countries exhausted")
    return None


def get_captcha_provider():
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
    """Move mouse to element center with random offset, simulating real user."""
    try:
        el = page.locator(selector).first
        box = await el.bounding_box()
        if box:
            x = box['x'] + box['width'] * random.uniform(0.25, 0.75)
            y = box['y'] + box['height'] * random.uniform(0.25, 0.75)
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            await human_delay(0.1, 0.3)
    except Exception:
        pass


async def human_click(page, selector):
    """Move mouse to element, then click with human-like timing."""
    await human_mouse_to(page, selector)
    try:
        await page.locator(selector).first.click()
    except Exception:
        pass
    await human_delay(0.2, 0.5)


async def human_fill(page, selector, text):
    """Clear field, then type text character-by-character with realistic speed.
    Includes micro-pauses, speed variations, and occasional corrections."""
    try:
        el = page.locator(selector).first
        await human_mouse_to(page, selector)
        await el.click()
        await human_delay(0.2, 0.5)
        await el.fill("")
        await human_delay(0.1, 0.3)
        for i, char in enumerate(text):
            delay_ms = random.randint(50, 170)
            if random.random() < 0.08:
                delay_ms = random.randint(200, 500)
            await page.keyboard.type(char, delay=delay_ms)
            if i > 0 and i % random.randint(3, 7) == 0 and random.random() < 0.3:
                await human_delay(0.15, 0.4)
    except Exception:
        try:
            await page.locator(selector).first.fill(text)
        except Exception:
            pass


async def human_type(page, selector, text, thread_log=None, db=None):
    """Type text with human-like delays and occasional pauses."""
    el = page.locator(selector)
    await el.click()
    await human_delay(0.3, 0.8)
    for char in text:
        await el.type(char, delay=random.randint(45, 120))
        if random.random() < 0.15:
            await human_delay(0.2, 0.6)


async def check_error_on_page(page) -> str | None:
    """Check if Microsoft shows an error message."""
    error_selectors = [
        '#MemberNameError', '#PasswordError', '#FirstNameError',
        '#LastNameError', '#BirthDateError', '.alert-error',
        '#error', '#ServerError',
    ]
    for sel in error_selectors:
        el = page.locator(sel)
        if await el.count() > 0:
            text = await el.text_content()
            if text and text.strip():
                return text.strip()
    return None


async def fluent_combobox_select(page, button_selectors: list[str], value: str, label: str, _log, timeout=5000):
    """Select a value from a Fluent UI combobox (button[role=combobox] + div[role=listbox]).
    
    MS signup uses Fluent UI - dropdowns are buttons that open a listbox of div[role=option] items.
    """
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
    
    try:
        # Use force=True because Fluent UI labels often overlay the button
        await page.locator(btn).first.click(force=True)
        await human_delay(0.3, 0.6)
    except Exception as e:
        # Fallback: try clicking via JavaScript
        try:
            await page.locator(btn).first.evaluate("el => el.click()")
            await human_delay(0.3, 0.6)
        except Exception:
            _log(f"[WARN] Failed to click combobox '{label}': {e}")
            return False
    
    try:
        await page.wait_for_selector('[role="listbox"]', timeout=3000)
    except Exception:
        _log(f"[WARN] Listbox for '{label}' did not appear")
        return False
    
    options = page.locator('[role="listbox"] [role="option"]')
    count = await options.count()
    
    for i in range(count):
        try:
            text = (await options.nth(i).inner_text()).strip()
            if text == value or text.startswith(value):
                await options.nth(i).click()
                _log(f"[OK] {label}: selected '{text}'")
                await human_delay(0.2, 0.4)
                return True
        except Exception:
            continue
    
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
    
    _log(f"[WARN] Failed to select '{value}' in combobox '{label}' (found {count} options)")
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
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
    Universal reCAPTCHA detector + solver.
    Checks if a reCAPTCHA iframe is present, extracts sitekey, solves via CapGuru.
    Returns True if captcha was solved, False if no captcha found.
    """
    if not captcha_provider or not captcha_provider.api_key:
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
        token = await asyncio.to_thread(
            captcha_provider.solve_captcha, page_url, sitekey
        )

        if not token:
            _log("[FAIL] Failed to solve CAPTCHA")
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
