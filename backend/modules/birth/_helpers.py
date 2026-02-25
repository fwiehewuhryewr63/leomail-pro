"""
Leomail v3 — Birth Helpers
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

        logger.info(f"📋 Account exported: {email} → {ACCOUNTS_EXPORT_FILE}")
    except Exception as e:
        logger.warning(f"📋 Export failed for {getattr(account, 'email', '?')}: {e}")


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
            _log(f"📸 Скриншот: {fname}")
        return path
    except Exception as e:
        if _log:
            _log(f"📸 Скриншот не удался: {e}")
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
    
    MS signup uses Fluent UI — dropdowns are buttons that open a listbox of div[role=option] items.
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
        _log(f"⚠️ Fluent combobox '{label}' не найден")
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
            _log(f"⚠️ Не удалось кликнуть combobox '{label}': {e}")
            return False
    
    try:
        await page.wait_for_selector('[role="listbox"]', timeout=3000)
    except Exception:
        _log(f"⚠️ Listbox для '{label}' не появился")
        return False
    
    options = page.locator('[role="listbox"] [role="option"]')
    count = await options.count()
    
    for i in range(count):
        try:
            text = (await options.nth(i).inner_text()).strip()
            if text == value or text.startswith(value):
                await options.nth(i).click()
                _log(f"✅ {label}: выбрано '{text}'")
                await human_delay(0.2, 0.4)
                return True
        except Exception:
            continue
    
    try:
        idx = int(value) - 1
        if 0 <= idx < count:
            text = (await options.nth(idx).inner_text()).strip()
            await options.nth(idx).click()
            _log(f"✅ {label}: выбрано по индексу '{text}'")
            await human_delay(0.2, 0.4)
            return True
    except (ValueError, Exception):
        pass
    
    _log(f"⚠️ Не удалось выбрать '{value}' в combobox '{label}' (найдено {count} опций)")
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
        msg = f"Не найдено поле '{step_name}'. URL: {page.url}"
        if ss and _log_fn:
            _log_fn(f"📸 Скриншот: {ss}")
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

        _log("🔐 reCAPTCHA обнаружена! Решаем...")

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
            _log("Sitekey не найден")
            return False

        _log(f"Sitekey: {sitekey[:20]}...")

        page_url = page.url
        token = await asyncio.to_thread(
            captcha_provider.solve_captcha, page_url, sitekey
        )

        if not token:
            _log("❌ Не удалось решить CAPTCHA")
            return False

        _log("✅ CAPTCHA решена! Вставляем токен...")

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
