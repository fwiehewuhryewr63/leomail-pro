"""
Leomail v4 - Outlook/Hotmail Registration Engine (Defensive Coding Template)
Registers outlook.com / hotmail.com accounts via signup.live.com.
Flow: signup -> email/username -> password -> birthday (country+month+day+year) -> name -> FunCaptcha -> prompts -> done
"""
import asyncio
import json as _json
import random
import threading
import urllib.parse as _urlparse
from loguru import logger
from sqlalchemy.orm import Session

from ...models import Proxy, ProxyStatus, Account, ThreadLog
from ...services.captcha_provider import CaptchaProvider, get_captcha_chain
from ...utils import generate_birthday, generate_password, generate_username
from ..browser_manager import BrowserManager
from ..human_behavior import (
    random_mouse_move, random_scroll, between_steps,
    pre_registration_warmup, human_click as hb_human_click, warmup_browsing,
)
from ._helpers import (
    human_delay as _human_delay,
    human_fill as _human_fill,
    human_type as _human_type,
    human_click as _human_click,
    check_error_on_page as _check_error_on_page,
    fluent_combobox_select as _fluent_combobox_select,
    MONTH_ALIASES, COUNTRY_ALIASES,
    wait_for_any as _wait_for_any,
    step_screenshot as _step_screenshot,
    wait_and_find as _wait_and_find,
    detect_and_solve_recaptcha as _detect_and_solve_recaptcha,
    detect_and_solve_funcaptcha as _detect_and_solve_funcaptcha,
    debug_screenshot as _debug_screenshot,
    _safe_screenshot,
    scan_for_block_signals as _scan_for_block_signals,
    clean_session as _clean_session,
    rate_limiter as _rate_limiter,
    RateLimitError, BannedIPError, FatalError, RecoverableError, CaptchaFailError,
    RegContext, verify_page_state, block_check, run_step,
    export_account_to_file, get_expected_language,
    run_flow_machine,
)


# Shared selectors
_NEXT_SELECTORS = ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]']


# ── Step Functions ───────────────────────────────────────────────────────────────


async def step_0_warmup(page, ctx: RegContext):
    """Step 0: Full pre-registration warmup — builds natural browsing history.
    
    Visits Google, performs search, browses 3-6 sites with real scrolling and
    mouse movement. Takes 15-30 seconds. This is CRITICAL for anti-fraud:
    a session that goes directly to signup.live.com = obvious bot.
    """
    ctx._log("Pre-registration warmup (15-30s browsing)...")
    try:
        geo = getattr(ctx, 'proxy_geo', None)
        await pre_registration_warmup(page, geo=geo)
    except Exception as warmup_e:
        logger.debug(f"Warmup error (proxy may be dead): {warmup_e}")

    warmup_url = page.url or ""
    if "chrome-error" in warmup_url or "about:blank" == warmup_url:
        ctx._log("[WARN] Proxy not working, warmup failed")


async def step_1_navigate(page, ctx: RegContext, proxy, db):
    """Step 1: Cookie warmup → referrer chain → signup.live.com.
    
    Cookie warmup: visit bing.com + microsoft.com to build natural MUID/ANON cookies.
    Referrer chain: go to outlook.com → click 'Create free account' → signup.live.com.
    This simulates a real user who was browsing Microsoft services before signing up.
    """
    # ── Cookie warmup: bing → microsoft (shared Microsoft cookie ecosystem) ──
    ctx._log("Cookie warmup: building natural browsing history...")
    warmup_sites = [
        ("https://www.bing.com", 3, 7),
        ("https://www.microsoft.com", 2, 5),
    ]
    for url, delay_min, delay_max in warmup_sites:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await random_scroll(page, "down")
            await _human_delay(delay_min, delay_max)
        except Exception as warmup_e:
            logger.debug(f"[Outlook] Cookie warmup skipped for {url}: {warmup_e}")
    
    # ── Referrer chain: outlook.com → 'Create account' → signup ──
    ctx._log("Navigating via outlook.com referrer chain...")
    signup_reached = False
    try:
        await page.goto("https://outlook.com", wait_until="domcontentloaded", timeout=30000)
        await _human_delay(2, 4)
        await random_mouse_move(page, steps=3)
        
        # Find 'Create free account' link (multi-locale)
        signup_link_selectors = [
            'a:has-text("Create free account")',
            'a:has-text("Sign up")',
            'a:has-text("Create account")',
            'a:has-text("Создайте бесплатную учетную запись")',
            'a:has-text("Crear cuenta gratuita")',
            'a:has-text("Crie uma conta gratuita")',
            'a:has-text("Kostenloses Konto erstellen")',
            'a:has-text("Créer un compte gratuit")',
            'a[href*="signup"]',
        ]
        signup_link = await _wait_for_any(page, signup_link_selectors, timeout=8000)
        if signup_link:
            ctx._log("Found 'Create account' link — clicking...")
            await _human_click(page, signup_link)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            signup_reached = True
        else:
            ctx._log("Create account link not found — direct navigation")
    except Exception as ref_e:
        logger.debug(f"[Outlook] Referrer chain skipped: {ref_e}")
    
    # ── Fallback: direct navigation to signup ──
    if not signup_reached or "signup.live.com" not in (page.url or ""):
        ctx._log("Opening registration page directly...")
        try:
            await page.goto(
                "https://signup.live.com/signup",
                wait_until="domcontentloaded",
                timeout=60000,
            )
        except Exception as nav_e:
            logger.warning(f"[Outlook] Navigation error: {nav_e}")

    # Reading pause: real humans read the page before typing (3-6 seconds)
    await _human_delay(3, 6)
    await random_scroll(page, "down")
    await _human_delay(1, 2)
    await random_scroll(page, "up")

    # Pre-check: proxy alive?
    current_url = page.url or ""
    if "chrome-error" in current_url or "about:blank" == current_url:
        if proxy:
            try:
                proxy.fail_count = (proxy.fail_count or 0) + 1
                if proxy.fail_count >= 3:
                    proxy.status = ProxyStatus.DEAD
                    logger.warning(f"Proxy marked DEAD after {proxy.fail_count} consecutive failures: {proxy.host}:{proxy.port}")
                else:
                    logger.info(f"Proxy temp fail #{proxy.fail_count}/3: {proxy.host}:{proxy.port} (will retry with different proxy)")
                db.commit()
            except Exception:
                pass
        ctx._err(f"[ERR] Proxy navigation failed (URL: {current_url})")
        raise RecoverableError("E501", f"Proxy navigation failed: {current_url}")

    # Check for error/block pages
    if "error" in current_url.split("?")[0].lower() or "blocked" in current_url.lower():
        ctx._err(f"[ERR] MS returned error page (URL: {current_url})")
        raise BannedIPError("E301", f"MS error page: {current_url}")

    # Block scan
    await block_check(page, ctx.provider, ctx, "navigate")

    await random_mouse_move(page, steps=3)
    ctx._log(f"Page: {page.url}")


async def step_2_email_mode(page, ctx: RegContext):
    """Step 2: Handle 'Get a new email address' link and detect domain dropdown."""
    new_email_link = page.locator(
        'a#liveSwitch, a[id*="Switch"], a:has-text("new email"), '
        'a:has-text("новый"), a:has-text("Get a new")'
    )
    ctx._got_new_email_mode = False
    try:
        if await new_email_link.count() > 0:
            ctx._log("Clicking 'Get a new email'...")
            await new_email_link.first.click()
            await _human_delay(1.5, 3)
            ctx._got_new_email_mode = True
    except Exception:
        pass

    if ctx._got_new_email_mode:
        domain_dropdown = await _wait_for_any(page, [
            'select#LiveDomainBoxList', '#LiveDomainBoxList',
            'select[name="DomainList"]',
        ], timeout=3000)
        if domain_dropdown:
            ctx._log("Username-only mode (domain dropdown visible)")
        else:
            ctx._got_new_email_mode = False
            ctx._log("Domain dropdown not visible, using full email")


async def step_3_enter_email(page, ctx: RegContext, domain: str):
    """Step 3: Enter email/username with retry on taken username (up to 3 times)."""
    await block_check(page, ctx.provider, ctx, "enter_email")

    email_selectors = [
        'input[name="MemberName"]', '#MemberName', '#iMemberName',
        'input[name="Email"]',
        'input[type="email"]', 'input[type="text"][name="MemberName"]',
        'input[aria-label*="email"]', 'input[aria-label*="Email"]',
        'input[placeholder*="email"]', 'input[placeholder*="Email"]',
        'input[id*="floatingLabel"]',
    ]
    ctx._log(f"Entering email: {ctx.email}")
    found = await _wait_and_find(page, email_selectors, "email", ctx.username, ctx._log, ctx._err, timeout=20000)
    if not found:
        raise RecoverableError("E101", "Email field not found")

    got_new_email_mode = getattr(ctx, '_got_new_email_mode', False)
    text_to_enter = ctx.username if got_new_email_mode else ctx.email
    ctx._log(f"Entering: {text_to_enter}")

    await _human_fill(page, found, text_to_enter)
    await _human_delay(1.5, 3.5)

    # Select domain if needed
    if got_new_email_mode and domain != "outlook.com":
        domain_sel = await _wait_for_any(page, [
            'select#LiveDomainBoxList', '#LiveDomainBoxList',
            'select[name="DomainList"]', 'select[aria-label*="domain"]',
        ], timeout=5000)
        if domain_sel:
            ctx._log(f"Selecting domain: @{domain}")
            await page.locator(domain_sel).first.select_option(domain)
            await _human_delay(0.5, 1)

    # Click Next
    next_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=5000)
    if next_btn:
        await _human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(3, 6)

    # Email-taken retry (up to 3)
    for email_retry in range(3):
        # Check if page advanced past email step (password field visible = success!)
        pwd_check = await _wait_for_any(page, [
            'input[name="Password"]', '#PasswordInput', 'input[type="password"]',
        ], timeout=2000)
        if pwd_check:
            ctx._log(f"Email accepted: {ctx.email}")
            break

        # Still on email page — check for error
        err_text = await _check_error_on_page(page)
        if err_text:
            old_username = ctx.username
            ctx.username = generate_username(ctx.first_name, ctx.last_name)
            ctx.email = f"{ctx.username}@{domain}"
            ctx._log(f"[WARN] Email '{old_username}@{domain}' taken: {err_text}. Trying: {ctx.email}")
            text_to_enter = ctx.username if got_new_email_mode else ctx.email
            found2 = await _wait_for_any(page, email_selectors, timeout=5000)
            if found2:
                await page.locator(found2).first.fill("")
                await _human_fill(page, found2, text_to_enter)
            await _human_delay(0.5, 1)
            next_retry = await _wait_for_any(page, _NEXT_SELECTORS, timeout=3000)
            if next_retry:
                await _human_click(page, next_retry)
            else:
                await page.keyboard.press("Enter")
            await _human_delay(3, 5)
        else:
            break
    else:
        raise RecoverableError("E102", "MS rejected 3 emails in a row")


async def step_4_password(page, ctx: RegContext):
    """Step 4: Enter password and click Next."""
    await block_check(page, ctx.provider, ctx, "password")

    ctx._log("Entering password...")
    pwd_selectors = [
        'input[name="Password"]', '#PasswordInput', 'input[type="password"]',
        '#iPasswordInput', 'input[name="passwd"]', '#Password',
        'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
        'input[data-purpose*="assword"]', 'input[placeholder*="assword"]',
        'input[placeholder*="арол"]',
    ]
    found = await _wait_and_find(page, pwd_selectors, "password", ctx.username, ctx._log, ctx._err, timeout=25000)
    if not found:
        raise RecoverableError("E103", "Password field not found")

    await _human_fill(page, found, ctx.password)
    await _human_delay(0.5, 1.2)

    next_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=3000)
    if next_btn:
        await _human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(2, 4)


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


async def step_5_birthday(page, ctx: RegContext, birthday, proxy):
    """Step 5: Enter birthday (country + month + day + year) using Fluent UI comboboxes."""
    ctx._log("Entering date of birth...")
    await _human_delay(1, 2)
    await _step_screenshot(page, "before_birthday", ctx.username)

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    month_name = month_names[birthday.month] if 1 <= birthday.month <= 12 else str(birthday.month)

    # Country selection
    from ...services.geo_resolver import build_geo_profile, resolve_proxy_geo
    proxy_geo = resolve_proxy_geo(proxy) if proxy else None
    geo_profile = build_geo_profile(proxy_geo) if proxy_geo else None

    _MS_COUNTRY_NAMES = {
        "US": "United States", "GB": "United Kingdom", "CA": "Canada",
        "AU": "Australia", "DE": "Germany", "FR": "France",
        "NL": "Netherlands", "SE": "Sweden", "IE": "Ireland",
        "NZ": "New Zealand", "AT": "Austria", "BR": "Brazil",
        "MX": "Mexico", "ES": "Spain", "PL": "Poland",
        "CZ": "Czechia", "RO": "Romania", "TR": "Turkey",
        "IT": "Italy", "PT": "Portugal", "AR": "Argentina",
        "CO": "Colombia", "CL": "Chile", "PE": "Peru",
        "IN": "India", "JP": "Japan", "KR": "South Korea",
        "RU": "Russia", "UA": "Ukraine", "IL": "Israel",
        "ZA": "South Africa", "EG": "Egypt", "NG": "Nigeria",
        "KE": "Kenya", "PH": "Philippines", "ID": "Indonesia",
        "TH": "Thailand", "VN": "Vietnam", "MY": "Malaysia",
        "SG": "Singapore", "HK": "Hong Kong", "FI": "Finland",
        "DK": "Denmark", "NO": "Norway", "HU": "Hungary",
        "GR": "Greece", "CN": "China", "TW": "Taiwan",
    }
    geo_code = geo_profile["country"] if geo_profile else None
    if geo_code and geo_code in _MS_COUNTRY_NAMES:
        chosen_country = _MS_COUNTRY_NAMES[geo_code]
    else:
        country_pool = [
            "United States", "United Kingdom", "Canada", "Australia",
            "Germany", "France", "Netherlands", "Sweden",
        ]
        chosen_country = random.choice(country_pool)
    # Get locale-aware aliases for this country
    country_aliases = COUNTRY_ALIASES.get(geo_code, [chosen_country]) if geo_code else [chosen_country]
    ctx._log(f"Selecting country: {chosen_country} (GEO: {proxy_geo or 'auto'})")

    _COUNTRY_SELECTORS = [
        '#countryDropdownId',
        'button[name="countryDropdownName"]',
        'button[aria-label*="ountry"]',
        'button[aria-label*="тран"]',
        'button[aria-label*="aís"]',
        'button[aria-label*="and"]',
        'button[role="combobox"]:first-of-type',
    ]
    country_ok = await _fluent_combobox_select(page, _COUNTRY_SELECTORS,
        chosen_country, "Country", ctx._log, timeout=5000, aliases=country_aliases)
    if not country_ok:
        # Fallback 1: native <select> element
        old_country = await _wait_for_any(page, [
            'select[id*="Country"]', 'select[name*="Country"]',
        ], timeout=2000)
        if old_country:
            try:
                await page.locator(old_country).first.select_option("US")
                ctx._log("Country: selected via native select")
                country_ok = True
            except Exception:
                pass
        # Fallback 2: try "United States" (most universal option)
        if not country_ok and chosen_country != "United States":
            ctx._log(f"[WARN] Country '{chosen_country}' failed — trying 'United States' fallback")
            country_ok = await _fluent_combobox_select(page, _COUNTRY_SELECTORS,
                "United States", "Country", ctx._log, timeout=5000,
                aliases=COUNTRY_ALIASES.get("US", ["United States", "USA"]))
    await _human_delay(0.5, 1.0)

    # Month — use locale-aware aliases
    month_aliases = MONTH_ALIASES.get(birthday.month, [month_name])
    _MONTH_SELECTORS = [
        '#BirthMonthDropdown',
        'button[name="BirthMonth"]',
        'button[aria-label*="irth month"]',
        'button[aria-label*="есяц"]',
        'button[aria-label*="es de"]',
        'button[aria-label*="onat"]',
    ]
    month_ok = await _fluent_combobox_select(page, _MONTH_SELECTORS,
        month_name, "Month", ctx._log, timeout=10000, aliases=month_aliases)
    if not month_ok:
        # Fallback 1: native <select> element
        old_month = await _wait_for_any(page, [
            '#BirthMonth', 'select[name="BirthMonth"]',
        ], timeout=2000)
        if old_month:
            try:
                await page.locator(old_month).first.select_option(str(birthday.month))
                ctx._log(f"Month: native select ({birthday.month})")
                month_ok = True
            except Exception:
                pass
    if not month_ok:
        # Last resort: dismiss any stuck dropdown, wait, retry month once more
        ctx._log("[WARN] Month selection failed — recovery attempt (dismiss + retry)")
        try:
            await page.keyboard.press("Escape")
            await _human_delay(1, 2)
            await page.mouse.click(400, 300)
            await _human_delay(1, 2)
        except Exception:
            pass
        month_ok = await _fluent_combobox_select(page, _MONTH_SELECTORS,
            month_name, "Month", ctx._log, timeout=10000, aliases=month_aliases)
    if not month_ok:
        ctx._err(f"Failed to select month. URL: {page.url}")
        await _debug_screenshot(page, "outlook_birthday_error", ctx._log)
        raise RecoverableError("E104", f"Month field not found at {page.url}")
    await _human_delay(0.3, 0.8)

    # Day
    day_ok = await _fluent_combobox_select(page, [
        '#BirthDayDropdown',
        'button[name="BirthDay"]',
        'button[aria-label*="irth day"]',
        'button[aria-label*="ень рожд"]',
    ], str(birthday.day), "Day", ctx._log, timeout=5000)
    if not day_ok:
        old_day = await _wait_for_any(page, [
            '#BirthDay', 'select[name="BirthDay"]',
        ], timeout=2000)
        if old_day:
            try:
                await page.locator(old_day).first.select_option(str(birthday.day))
                ctx._log(f"Day: native select ({birthday.day})")
            except Exception:
                pass
    await _human_delay(0.3, 0.8)

    # Year
    year_sel = await _wait_for_any(page, [
        'input[name="BirthYear"]', '#BirthYear',
        'input[aria-label*="irth year"]', 'input[aria-label*="од рожд"]',
        'input[type="number"]',
    ], timeout=5000)
    if year_sel:
        await _human_fill(page, year_sel, str(birthday.year))
        ctx._log(f"Year: {birthday.year}")
    else:
        ctx._log("[WARN] Year field not found")
    await _human_delay(0.5, 1)

    # Scroll + submit
    await page.mouse.wheel(0, random.randint(50, 150))
    await _human_delay(0.8, 1.5)

    next_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=3000)
    if next_btn:
        await _human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(2, 4)


async def step_6_name(page, ctx: RegContext):
    """Step 6: Enter first + last name. May not appear on all MS flows."""
    ctx._log(f"Entering name: {ctx.first_name} {ctx.last_name}")
    fn_selectors = [
        '#firstNameInput',
        'input[name="FirstName"]', '#FirstName', '#iFirstName',
        'input[name="DisplayName"]', '#DisplayName',
        'input[placeholder*="имя"]', 'input[placeholder*="irst"]',
        'input[aria-label*="irst name"]', 'input[aria-label*="имя"]',
    ]
    name_found = await _wait_for_any(page, fn_selectors, timeout=8000)
    if name_found:
        ctx._log("Detected name page")
        await _human_fill(page, name_found, ctx.first_name)
        await _human_delay(0.8, 1.5)

        ln_selectors = [
            '#lastNameInput',
            'input[name="LastName"]', '#LastName', '#iLastName',
            'input[placeholder*="фамил"]', 'input[placeholder*="ast"]',
            'input[aria-label*="ast name"]', 'input[aria-label*="фам"]',
        ]
        found_ln = await _wait_for_any(page, ln_selectors, timeout=5000)
        if found_ln:
            await _human_fill(page, found_ln, ctx.last_name)
        await _human_delay(0.5, 1)

        await random_mouse_move(page, steps=2)
        await _human_delay(1.0, 2.0)

        next_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=3000)
        if next_btn:
            await _human_click(page, next_btn)
        else:
            await page.keyboard.press("Enter")
        await _human_delay(3, 6)
    else:
        ctx._log("[WARN] Name page not found - possibly already on CAPTCHA")


async def step_7_captcha(page, ctx: RegContext, captcha_provider):
    """Step 7: Handle PerimeterX HUMAN challenge ('Press and hold') or FunCaptcha fallback.
    MS Outlook uses hsprotect.net (PerimeterX/HUMAN Security) enforcement.
    The challenge is usually 'press and hold the button', NOT classic FunCaptcha puzzles.

    RE-CHALLENGE LOOP: Microsoft sometimes shows a SECOND captcha after the first one passes.
    We loop up to MAX_CAPTCHA_ROUNDS to handle re-challenges.
    """
    MAX_CAPTCHA_ROUNDS = 3  # max re-challenges before giving up
    ctx._log("Checking CAPTCHA...")
    await _human_delay(2, 4)
    any_round_passed = False  # track if ANY round solved successfully

    for captcha_round in range(1, MAX_CAPTCHA_ROUNDS + 1):
        if captcha_round > 1:
            ctx._log(f"[CAPTCHA] Re-challenge check — round {captcha_round}/{MAX_CAPTCHA_ROUNDS}")
            # Wait for re-challenge iframe to appear (it re-loads asynchronously)
            # Poll up to 8 seconds — MS takes 3-6s to inject the re-challenge iframe
            iframe_appeared = False
            for wait_i in range(8):
                await asyncio.sleep(1.0)
                rc_count = await page.locator(
                    'iframe[src*="hsprotect"], iframe[title*="captcha"], '
                    'iframe[title*="Human"], #enforcementFrame'
                ).count()
                if rc_count > 0:
                    iframe_appeared = True
                    ctx._log(f"[CAPTCHA] Re-challenge iframe appeared after {wait_i + 1}s")
                    break
            if not iframe_appeared:
                # No re-challenge after 8s — previous solve was accepted!
                ctx._log(f"[OK] No re-challenge after 8s — captcha fully passed!")
                await block_check(page, ctx.provider, ctx, "post_captcha")
                return

        # Detect enforcement iframe (hsprotect.net or legacy funcaptcha/arkose)
        captcha_frame = page.locator(
            'iframe[src*="hsprotect"], iframe[title*="captcha"], iframe[title*="Verification"], '
            'iframe[title*="Human"], iframe[src*="funcaptcha"], #enforcementFrame'
        )

        if await captcha_frame.count() == 0:
            if captcha_round == 1:
                # No enforcement on first check — try reCAPTCHA fallback
                ctx._log("No enforcement iframe — checking reCAPTCHA fallback...")
                recaptcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
                if recaptcha_solved:
                    ctx._log("[OK] reCAPTCHA solved (MS fallback)")
                    await _human_delay(3, 6)
                    post_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=5000)
                    if post_btn:
                        await _human_click(page, post_btn)
                        await _human_delay(3, 6)
                else:
                    ctx._log("No CAPTCHA detected - continuing")
            else:
                # No enforcement on subsequent round — previous solve was accepted!
                ctx._log(f"[OK] No re-challenge on round {captcha_round} — captcha fully passed!")
            await block_check(page, ctx.provider, ctx, "post_captcha")
            return

        # ── Enforcement iframe detected ──
        await _debug_screenshot(page, f"{ctx.username}_captcha_round{captcha_round}", ctx._log)

        # Check main page text for challenge type
        page_text = ""
        try:
            page_text = await page.inner_text("body")
        except Exception:
            pass
        page_lower = page_text.lower()

        # Check for BLOCK signals (not a challenge, just a ban)
        block_keywords = [
            "can't create", "cannot create", "unable to create",
            "something went wrong", "try again later",
            "we couldn't create", "account cannot be created",
        ]
        for kw in block_keywords:
            if kw in page_lower:
                ctx._err(f"[BLOCK] Microsoft BLOCKED: '{kw}'")
                raise BannedIPError("E302", f"MS blocked: {kw}")

        # ── Try PerimeterX "Press and hold" challenge ──
        # Multi-locale detection: the challenge text can be in any language
        _PX_CHALLENGE_KEYWORDS = [
            "press and hold", "prove you're human",         # English
            "pressione e segure", "provar que você",        # Portuguese
            "mantén presionado", "mantener presionado", "demuestra que eres", # Spanish
            "gedrückt halten", "halten sie", "beweisen",    # German
            "appuyez et maintenez", "prouvez que vous",     # French
            "tieni premuto", "dimostra che sei",            # Italian
            "houd ingedrukt", "bewijs dat je",              # Dutch
            "naciśnij i przytrzymaj", "udowodnij",          # Polish
            "basılı tutun", "insan olduğunuzu",             # Turkish
            "apăsați și mențineți",                         # Romanian
            "tryck och håll",                               # Swedish
            "人間であることを証明",                            # Japanese
        ]
        is_press_hold = any(kw in page_lower for kw in _PX_CHALLENGE_KEYWORDS)

        # FALLBACK: if enforcement iframe from hsprotect.net exists, it's ALWAYS press-and-hold
        # This handles ANY language we haven't mapped
        has_hsprotect = await page.locator('iframe[src*="hsprotect"]').count() > 0
        if not is_press_hold and has_hsprotect:
            ctx._log(f"[CAPTCHA] hsprotect iframe detected — treating as press-and-hold (text did not match known patterns)")
            is_press_hold = True

        if is_press_hold:
            ctx._log(f"[CAPTCHA] PerimeterX 'Press and hold' challenge (round {captcha_round})")
            solved = await _solve_perimeterx_hold(page, ctx)
            if solved:
                ctx._log(f"[OK] PerimeterX challenge passed (round {captcha_round})!")
                any_round_passed = True
                await _human_delay(3, 6)
                # DON'T return yet — loop back to check for re-challenge
                continue
            else:
                if any_round_passed:
                    # A previous round DID pass — MS re-challenged and we failed the re-challenge
                    # but the first solve may have been accepted. Check if page advanced.
                    ctx._log(f"[CAPTCHA] Re-challenge failed on round {captcha_round}, but round 1 passed — checking if accepted...")
                    await _human_delay(3, 5)
                    # Check if enforcement iframe disappeared (challenge was actually accepted)
                    remaining = await page.locator('iframe[src*="hsprotect"], #enforcementFrame').count()
                    if remaining == 0:
                        ctx._log(f"[OK] Enforcement iframe gone after re-challenge fail — treating as success!")
                        await block_check(page, ctx.provider, ctx, "post_captcha")
                        return
                    # Check if URL changed (page moved past captcha)
                    if "signup.live.com" not in page.url:
                        ctx._log(f"[OK] URL changed to {page.url[:60]} — registration continued!")
                        await block_check(page, ctx.provider, ctx, "post_captcha")
                        return
                    ctx._log(f"[CAPTCHA] Re-challenge still active — continuing to next round")
                    continue  # try next round instead of crash
                # PX failed — try FunCaptcha API solver as fallback
                ctx._log(f"[CAPTCHA] PX press-and-hold failed — trying FunCaptcha API fallback...")
                fc_solved = await _detect_and_solve_funcaptcha(page, captcha_provider, ctx._log)
                if fc_solved:
                    ctx._log("[OK] FunCaptcha API solved the challenge after PX fail!")
                    await _human_delay(3, 5)
                    any_round_passed = True
                    continue  # re-check for challenge
                ctx._err(f"[CAPTCHA] Both PX hold AND FunCaptcha API failed on round {captcha_round}")
                raise CaptchaFailError("E410", f"PX hold + FunCaptcha API both failed (round {captcha_round})")
        else:
            # Unknown enforcement type — try FunCaptcha API solver
            ctx._log(f"[CAPTCHA] Unknown enforcement: {page_lower[:120]}")
            ctx._log("[CAPTCHA] Trying FunCaptcha API solver for unknown enforcement...")
            fc_solved = await _detect_and_solve_funcaptcha(page, captcha_provider, ctx._log)
            if fc_solved:
                ctx._log("[OK] FunCaptcha API solved unknown enforcement!")
                await _human_delay(3, 5)
                any_round_passed = True
                continue  # re-check for challenge
            ctx._err("[CAPTCHA] Unknown enforcement type — FunCaptcha API also failed")
            raise CaptchaFailError("E411", "Unknown enforcement + FunCaptcha API failed")

    # Exhausted all rounds
    ctx._err(f"[CAPTCHA] Failed after {MAX_CAPTCHA_ROUNDS} re-challenge rounds")
    raise CaptchaFailError("E412", f"Captcha re-challenged {MAX_CAPTCHA_ROUNDS} times — giving up")

    await block_check(page, ctx.provider, ctx, "post_captcha")


async def _solve_perimeterx_hold(page, ctx: RegContext, max_retries: int = 4) -> bool:
    """Solve PerimeterX 'Press and hold the button' challenge.
    The button loads inside an hsprotect.net iframe. Strategy:
    1. Try to find #px-captcha in main page (PerimeterX sometimes injects it directly)
    2. Try Playwright frame_locator() to find elements INSIDE the cross-origin iframe
    3. Fall back to pressing center of the iframe element itself
    Hold duration: 10-16 seconds (PerimeterX requires long holds).
    Returns True if challenge was passed, False otherwise.
    """
    pre_url = page.url  # remember URL before challenge

    for attempt in range(1, max_retries + 1):
        ctx._log(f"[PX] Attempt {attempt}/{max_retries}: looking for hold button...")

        hold_target = None  # the locator to get bounding_box from
        found_via = "none"

        # ── Strategy 1: #px-captcha in main page ──
        main_page_selectors = [
            '#px-captcha',
            'div[id="px-captcha"]',
            '[data-testid*="captcha"]',
            'button[id*="captcha"]',
        ]
        for sel in main_page_selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    hold_target = loc.first
                    found_via = f"main_page:{sel}"
                    break
            except Exception:
                continue

        # ── Strategy 2: frame_locator() to find elements INSIDE the iframe ──
        if not hold_target:
            iframe_selectors = [
                'iframe[src*="hsprotect"]',
                'iframe[title*="Human"]',
                'iframe[title*="captcha"]',
                'iframe[title*="Verification"]',
                '#enforcementFrame',
            ]
            for iframe_sel in iframe_selectors:
                try:
                    iframe_loc = page.locator(iframe_sel)
                    iframe_count = await iframe_loc.count()
                    if iframe_count == 0:
                        continue
                    # Use .first when multiple iframes match (strict mode fix)
                    if iframe_count > 1:
                        frame = page.frame_locator(f"{iframe_sel} >> nth=0")
                    else:
                        frame = page.frame_locator(iframe_sel)
                    # Look for the press-and-hold button inside the iframe
                    inner_selectors = [
                        '#px-captcha',
                        '#px-captcha-wrapper',
                        'div[id="px-captcha"]',
                        'button',
                        '[role="button"]',
                        '.btn',
                        '#hold_button',
                    ]
                    for inner_sel in inner_selectors:
                        try:
                            inner_loc = frame.locator(inner_sel)
                            if await inner_loc.count() > 0:
                                hold_target = inner_loc.first
                                found_via = f"frame:{iframe_sel} > {inner_sel}"
                                break
                        except Exception:
                            continue
                    if hold_target:
                        break
                except Exception:
                    continue

        # ── Strategy 3: Fall back to the iframe element itself ──
        if not hold_target:
            for iframe_sel in ['iframe[src*="hsprotect"]', 'iframe[title*="Human"]', '#enforcementFrame']:
                try:
                    loc = page.locator(iframe_sel)
                    if await loc.count() > 0:
                        hold_target = loc.first
                        found_via = f"iframe_element:{iframe_sel}"
                        break
                except Exception:
                    continue

        if not hold_target:
            ctx._log(f"[PX] No button found on attempt {attempt}")
            await _human_delay(2, 4)
            continue

        # ── Simulate human press-and-hold ──
        try:
            # Get bounding box — wait for button to render (height > 0)
            bbox = None
            for wait_i in range(6):  # poll up to 6 times (0, 1, 2, 3, 4, 5s)
                bbox = await hold_target.bounding_box()
                if bbox and bbox.get('height', 0) > 5 and bbox.get('width', 0) > 5:
                    break  # button rendered with real dimensions
                if wait_i < 5:
                    if wait_i == 0:
                        ctx._log(f"[PX] {found_via} — waiting for button to render...")
                    await asyncio.sleep(1.0)
                    bbox = None  # reset for next check
            
            if not bbox or bbox.get('height', 0) <= 5 or bbox.get('width', 0) <= 5 or bbox.get('x', 0) < -100:
                ctx._log(f"[PX] {found_via} — button has zero/tiny/offscreen dimensions after 5s wait (bbox={bbox})")
                # Scroll element into view and retry
                try:
                    await hold_target.scroll_into_view_if_needed(timeout=3000)
                    await asyncio.sleep(2.0)
                    bbox = await hold_target.bounding_box()
                    if bbox and bbox.get('height', 0) > 5 and bbox.get('width', 0) > 5 and bbox.get('x', 0) > -100:
                        ctx._log(f"[PX] Scroll fixed it! New bbox: {bbox['width']:.0f}x{bbox['height']:.0f} at ({bbox['x']:.0f},{bbox['y']:.0f})")
                    else:
                        # Try clicking the page body to trigger re-render, then re-check
                        try:
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await asyncio.sleep(1.5)
                            await page.evaluate("window.scrollTo(0, 0)")
                            await asyncio.sleep(1.5)
                            bbox = await hold_target.bounding_box()
                        except Exception:
                            pass
                        if not bbox or bbox.get('height', 0) <= 5 or bbox.get('width', 0) <= 5 or bbox.get('x', 0) < -100:
                            ctx._log(f"[PX] Still zero/offscreen after scroll — skipping attempt {attempt}")
                            await _human_delay(2, 4)
                            continue
                        ctx._log(f"[PX] Page scroll fixed it! New bbox: {bbox['width']:.0f}x{bbox['height']:.0f} at ({bbox['x']:.0f},{bbox['y']:.0f})")
                except Exception as scroll_err:
                    ctx._log(f"[PX] Scroll failed: {scroll_err}")
                    await _human_delay(2, 4)
                    continue

            ctx._log(f"[PX] Found via {found_via} — bbox: {bbox['width']:.0f}x{bbox['height']:.0f} at ({bbox['x']:.0f},{bbox['y']:.0f})")

            # Move mouse naturally first — pre-PX warm movements
            await random_mouse_move(page, steps=random.randint(3, 5))
            await _human_delay(0.5, 1.5)

            # Click position: center of the target with small random offset
            cx = bbox['x'] + bbox['width'] * random.uniform(0.35, 0.65)
            cy = bbox['y'] + bbox['height'] * random.uniform(0.35, 0.65)

            ctx._log(f"[PX] Pressing and holding at ({cx:.0f}, {cy:.0f})...")

            # Move to target smoothly
            await page.mouse.move(cx, cy, steps=random.randint(8, 16))
            await _human_delay(0.3, 0.6)

            # Mouse down (start press)
            await page.mouse.down()

            # Hold with ADAPTIVE duration (different per attempt for broader coverage)
            # PX minimum threshold is ~10s — vary to find what works
            _HOLD_RANGES = {
                1: (10.0, 14.0),   # Attempt 1: shorter — many PX accept 10-12s
                2: (14.0, 18.0),   # Attempt 2: medium
                3: (18.0, 25.0),   # Attempt 3: longer — some PX need 20s+
                4: (11.0, 16.0),   # Attempt 4: mid-range retry
            }
            hold_min, hold_max = _HOLD_RANGES.get(attempt, (13.0, 21.0))
            hold_duration = random.uniform(hold_min, hold_max)
            ctx._log(f"[PX] Holding for {hold_duration:.1f}s (attempt {attempt} range: {hold_min:.0f}-{hold_max:.0f}s)...")
            elapsed = 0.0
            while elapsed < hold_duration:
                # Micro-jitter: ±3px every 200-500ms (realistic hand tremor)
                jitter_x = cx + random.randint(-3, 3)
                jitter_y = cy + random.randint(-3, 3)
                await page.mouse.move(jitter_x, jitter_y)
                step = random.uniform(0.2, 0.5)
                await asyncio.sleep(step)
                elapsed += step

            # Mouse up (release)
            await page.mouse.up()
            ctx._log("[PX] Released button")

            # Post-PX pause: don't rush after solving (3-6s natural pause)
            await _human_delay(3, 6)

            # ── Progressive success check: poll every 2s for up to 12s ──
            # MS can take 8-10s to process the PX hold and redirect.
            # A single 3-6s wait caused FALSE NEGATIVES — page redirected AFTER we gave up.
            for check_i in range(6):  # 6 checks × 2s = 12s max
                await asyncio.sleep(2.0)
                current_url = page.url
                current_text = ""
                try:
                    current_text = await page.inner_text("body")
                except Exception:
                    pass

                # 1. URL changed (page advanced past challenge)
                if current_url != pre_url:
                    ctx._log(f"[PX] URL changed after {(check_i+1)*2}s: {current_url[:80]} — SOLVED!")
                    await _debug_screenshot(page, f"{ctx.username}_px_solved", ctx._log)
                    return True

                # 2. Challenge text gone (multi-language check)
                lower_text = current_text.lower()
                _PX_STILL_SHOWING = [
                    "press and hold", "prove you're human",
                    "pressione e segure", "provar que você",
                    "mantén presionado", "demuestra que eres",
                    "gedrückt halten", "appuyez et maintenez",
                    "tieni premuto", "houd ingedrukt",
                    "basılı tutun", "naciśnij i przytrzymaj",
                ]
                challenge_still_showing = any(kw in lower_text for kw in _PX_STILL_SHOWING)
                if not challenge_still_showing:
                    ctx._log(f"[PX] Challenge text gone after {(check_i+1)*2}s — appears solved!")
                    await _debug_screenshot(page, f"{ctx.username}_px_solved", ctx._log)
                    return True

                # 3. Enforcement iframe gone
                iframe_count = await page.locator('iframe[src*="hsprotect"]').count()
                if iframe_count == 0:
                    ctx._log(f"[PX] Enforcement iframe gone after {(check_i+1)*2}s — challenge passed!")
                    await _debug_screenshot(page, f"{ctx.username}_px_solved", ctx._log)
                    return True

            # Still on challenge page after 12s — screenshot and retry
            ctx._log(f"[PX] Still on challenge page after attempt {attempt} (12s wait)")
            await _debug_screenshot(page, f"{ctx.username}_px_retry{attempt}", ctx._log)
            await _human_delay(1, 2)

        except Exception as e:
            ctx._log(f"[PX] Error on attempt {attempt}: {str(e)[:100]}")
            await _human_delay(2, 4)

    return False


async def step_8_post_prompts(page, ctx: RegContext):
    """Step 8: Handle post-captcha prompts (Stay signed in?, privacy notice, promo pages)."""
    await _human_delay(2, 4)

    # ── Microsoft Privacy Notice page ──
    # After successful registration, MS redirects to:
    #   https://privacynotice.account.microsoft.com/notice?ru=...
    # This page has Accept/Continue buttons that MUST be clicked or the flow hangs.
    if "privacynotice" in page.url.lower() or "privacy" in page.url.lower():
        ctx._log("[OK] Privacy notice page detected — accepting...")
        privacy_btn = await _wait_for_any(page, [
            'button[id*="accept"]', 'button[id*="Accept"]',
            'input[type="submit"]', 'button[type="submit"]',
            'button:has-text("Accept")', 'button:has-text("Continue")',
            'button:has-text("Принять")', 'button:has-text("Aceptar")',
            'button:has-text("Akzeptieren")', 'button:has-text("Accepter")',
            'button:has-text("Accetta")', 'button:has-text("Aceitar")',
            'a:has-text("Accept")', 'a:has-text("Continue")',
            '#id__0',  # common MS button ID
        ], timeout=10000)
        if privacy_btn:
            await _human_click(page, privacy_btn)
            ctx._log("[OK] Privacy notice accepted")
            await _human_delay(3, 6)
        else:
            # Try pressing Enter as fallback
            ctx._log("[WARN] No privacy button found — pressing Enter")
            await page.keyboard.press("Enter")
            await _human_delay(3, 5)

    # ── "Stay signed in?" prompt ──
    stay_signed_in = await _wait_for_any(page, [
        '#KmsiBanner', '#acceptButton', 'button:has-text("Yes")',
        'input[value="Yes"]', '#idSIButton9',
    ], timeout=5000)
    if stay_signed_in:
        ctx._log("Clicking 'Yes' on 'Stay signed in?'")
        await _human_click(page, stay_signed_in)
        await _human_delay(3, 5)

    # ── Second privacy check (can appear AFTER stay-signed-in) ──
    if "privacynotice" in page.url.lower() or "privacy" in page.url.lower():
        ctx._log("[OK] Privacy notice page (round 2) — accepting...")
        privacy_btn2 = await _wait_for_any(page, [
            'button[id*="accept"]', 'button[id*="Accept"]',
            'input[type="submit"]', 'button[type="submit"]',
            'button:has-text("Accept")', 'button:has-text("Continue")',
            'a:has-text("Accept")', 'a:has-text("Continue")',
            '#id__0',
        ], timeout=8000)
        if privacy_btn2:
            await _human_click(page, privacy_btn2)
            ctx._log("[OK] Privacy notice accepted (round 2)")
            await _human_delay(3, 6)
        else:
            await page.keyboard.press("Enter")
            await _human_delay(3, 5)

    # ── Promo/skip pages ──
    skip_promo = await _wait_for_any(page, [
        'button:has-text("Skip")', 'a:has-text("Skip")',
        'button:has-text("Пропустить")', 'a:has-text("Пропустить")',
        'button:has-text("No thanks")', 'a:has-text("No thanks")',
        'button:has-text("Maybe later")', '#declineButton',
    ], timeout=3000)
    if skip_promo:
        ctx._log("Skipping promo page...")
        await _human_click(page, skip_promo)
        await _human_delay(2, 4)


async def step_9_verify_success(page, ctx: RegContext) -> bool:
    """Step 9: Verify registration succeeded."""
    ctx._log("Checking result...")
    await _human_delay(2, 4)
    final_url = page.url.lower()
    ctx._log(f"Final URL: {final_url}")

    registration_success = False
    try:
        success_indicators = [
            "outlook.live.com", "signup.live.com/signup?sru",
            "/MailSetup", "account.microsoft.com",
            "privacynotice.account.microsoft.com",
            "outlook.office.com", "outlook.office365.com",
            "login.live.com",  # post-registration redirect
        ]
        if any(ind in final_url for ind in success_indicators):
            registration_success = True
            ctx._log("[OK] URL confirms successful registration")
        elif "signup.live.com" not in final_url:
            registration_success = True
            ctx._log("[OK] Left registration page")
        else:
            page_text = await page.locator('body').inner_text()
            fail_indicators = ["something went wrong", "couldn't create", "error", "blocked"]
            if any(fi.lower() in page_text.lower() for fi in fail_indicators):
                ctx._err("[FAIL] Page contains error indicators")
                await _debug_screenshot(page, "outlook_error_on_page")
            else:
                ctx._log("[WARN] Still on signup.live.com, but no errors")
                await _debug_screenshot(page, "outlook_still_on_signup")
    except Exception as e:
        ctx._log(f"Success check: error ({e}), counting as success if URL changed")
        if "signup.live.com" not in final_url:
            registration_success = True

    if not registration_success:
        ctx._err(f"[FAIL] Registration NOT confirmed! URL: {final_url}")
        await _debug_screenshot(page, "outlook_not_confirmed")
        raise FatalError("E502", f"Registration not confirmed: {final_url}")

    return True


# ── Outlook Post-Registration Warmup ─────────────────────────────────────────────


async def _outlook_post_reg_warmup(page, ctx: RegContext):
    """Outlook-specific post-registration warmup (30-60s).

    A real user's first-time inbox experience:
    1. Dismiss onboarding prompts (Welcome wizard, "Get app", "Choose look")
    2. Land in inbox, see welcome email
    3. Open and READ the welcome email
    4. Browse settings briefly
    Total: 30-60s — natural first-time user pace

    Every step is error-tolerant — if something fails, we continue.
    Compose step removed to reduce page loads on shared proxy bandwidth.
    """
    duration = random.randint(30, 60)
    start = asyncio.get_event_loop().time()
    ctx._log(f"[POST-REG] Outlook first-time inbox experience ({duration}s)...")

    def _elapsed():
        return asyncio.get_event_loop().time() - start

    # ── Step 1: Navigate to inbox ──
    try:
        await page.goto("https://outlook.live.com/mail/0/inbox",
                        wait_until="domcontentloaded", timeout=25000)
        await _human_delay(3, 6)
        ctx._log("[POST-REG] Inbox page loaded")
        inbox_loaded = True
    except Exception as e:
        ctx._log(f"[POST-REG] Inbox load error: {str(e)[:80]}")
        # Fallback: try base URL
        try:
            await page.goto("https://outlook.live.com/mail/",
                            wait_until="domcontentloaded", timeout=20000)
            await _human_delay(3, 5)
            inbox_loaded = True
        except Exception:
            ctx._log("[POST-REG] Could not reach inbox — skipping warmup")
            return

    # ── Step 2: Dismiss onboarding prompts ──
    # MS shows multiple prompts for new accounts: Welcome, Get app, Theme, etc.
    _ONBOARDING_DISMISS_SELECTORS = [
        # "Get the Outlook app" / "Try the Outlook app"
        'button:has-text("Skip")', 'button:has-text("No thanks")',
        'button:has-text("Maybe later")', 'a:has-text("Skip")',
        'button:has-text("Not now")',
        # "Choose your look" / "Pick a theme"
        'button:has-text("Got it")', 'button:has-text("Done")',
        # "Import contacts" / "Welcome wizard"
        'button:has-text("Skip for now")', 'button:has-text("Close")',
        # Generic dismiss / continue
        'button[aria-label="Close"]', 'button[aria-label="Dismiss"]',
        'button[aria-label="close"]', 'button[aria-label="dismiss"]',
        # Close "X" buttons on dialogs
        'div[role="dialog"] button[aria-label="Close"]',
        'div[role="dialog"] button:has-text("×")',
        # Multi-language variants
        'button:has-text("Пропустить")', 'button:has-text("Omitir")',
        'button:has-text("Überspringen")', 'button:has-text("Ignorer")',
        'button:has-text("Salta")',
    ]

    # Try dismissing up to 5 prompts (MS can chain multiple)
    for prompt_round in range(5):
        if _elapsed() > duration * 0.3:  # Don't spend more than 30% on onboarding
            break
        dismissed = False
        for sel in _ONBOARDING_DISMISS_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await _human_delay(1, 2)
                    await _human_click(page, sel)
                    ctx._log(f"[POST-REG] Dismissed onboarding prompt ({sel[:40]})")
                    await _human_delay(2, 4)
                    dismissed = True
                    break
            except Exception:
                continue
        if not dismissed:
            break  # No more prompts to dismiss
        await _human_delay(1, 2)

    # ── Step 3: Read the welcome email ──
    if _elapsed() < duration * 0.6:
        try:
            # Wait for email list to populate
            await _human_delay(2, 4)

            # Look for the first email in inbox (likely Microsoft welcome)
            email_selectors = [
                'div[role="listbox"] div[role="option"]:first-child',
                'div[data-convid]',
                'div[role="option"][aria-label*="Microsoft"]',
                'div[role="option"][aria-label*="Welcome"]',
                'div[role="option"][aria-label*="Outlook"]',
                'div[role="option"]:first-child',
            ]

            email_clicked = False
            for sel in email_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        await _human_click(page, sel)
                        email_clicked = True
                        ctx._log("[POST-REG] Opened first email (welcome)")
                        break
                except Exception:
                    continue

            if email_clicked:
                # Read the email — scroll and idle
                await _human_delay(3, 6)
                from ..human_behavior import random_mouse_move, random_scroll, idle_behavior
                await random_mouse_move(page, steps=random.randint(2, 4))
                await random_scroll(page, "down")
                await _human_delay(2, 4)

                # Idle "reading" behavior
                await idle_behavior(page, random.uniform(3, 6))
                await random_mouse_move(page, steps=random.randint(1, 3))

                # Go back to inbox (click Back, not full page reload)
                try:
                    back_btn = page.locator('button[aria-label="Back"], button[title="Back"]').first
                    if await back_btn.count() > 0:
                        await _human_click(page, 'button[aria-label="Back"], button[title="Back"]')
                        await _human_delay(2, 4)
                except Exception:
                    pass

                ctx._log("[POST-REG] Welcome email read")
            else:
                ctx._log("[POST-REG] No emails found in inbox yet — browsing inbox")
                from ..human_behavior import random_mouse_move, random_scroll, idle_behavior
                await random_mouse_move(page, steps=random.randint(2, 5))
                await random_scroll(page, "down")
                await _human_delay(2, 4)
                await idle_behavior(page, random.uniform(2, 4))

        except Exception as e:
            ctx._log(f"[POST-REG] Email read error: {str(e)[:80]}")

    # ── Step 4: Visit Settings (skip if time is tight) ──
    if _elapsed() < duration * 0.75:
        try:
            await page.goto("https://outlook.live.com/mail/0/options/general",
                            wait_until="domcontentloaded", timeout=25000)
            await _human_delay(2, 4)
            from ..human_behavior import random_mouse_move, random_scroll
            await random_mouse_move(page, steps=random.randint(2, 4))
            await random_scroll(page, "down")
            await _human_delay(2, 3)
            ctx._log("[POST-REG] Browsed settings")
        except Exception as e:
            ctx._log(f"[POST-REG] Settings visit error: {str(e)[:80]}")

    # ── Step 5 (Compose) REMOVED — reduces proxy bandwidth competition ──

    # ── Step 5: Final idle on current page ──
    remaining = duration - _elapsed()
    if remaining > 3:
        try:
            from ..human_behavior import random_mouse_move, idle_behavior
            await random_mouse_move(page, steps=random.randint(1, 3))
            await idle_behavior(page, min(remaining - 2, random.uniform(3, 8)))
        except Exception:
            pass

    total_time = _elapsed()
    ctx._log(f"[POST-REG] Outlook warmup complete ({total_time:.1f}s)")


# ── Main Orchestrator ────────────────────────────────────────────────────────────


async def register_single_outlook(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    name_pool: list,
    captcha_provider: CaptchaProvider | None,
    db: Session,
    thread_log: ThreadLog | None = None,
    domain: str = "outlook.com",
    ACTIVE_PAGES: dict = None,
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """Register a single Outlook/Hotmail account using the Defensive Coding Template."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
    if not name_pool:
        logger.error("[Outlook] [FAIL] No names! Load a name pack before registration.")
        if thread_log:
            thread_log.status = "error"
            thread_log.error_message = "No names! Load a name pack."
            try: db.commit()
            except: pass
        return None

    first_name, last_name = random.choice(name_pool)
    password = generate_password()
    birthday = generate_birthday()
    username = generate_username(first_name, last_name)
    email = f"{username}@{domain}"
    provider_name = "hotmail" if "hotmail" in domain else "outlook"

    # ── Create RegContext ──
    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Outlook][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try: db.commit()
            except Exception: pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Outlook][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try: db.commit()
            except Exception: pass

    _proxy_geo = (proxy.geo or "").upper() if proxy else ""
    ctx = RegContext(
        provider=provider_name,
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
        proxy_ip=f"{proxy.host}:{proxy.port}" if proxy else "",
        proxy_geo=_proxy_geo,
        proxy_type=getattr(proxy, 'proxy_type', '') or "" if proxy else "",
        language=get_expected_language(_proxy_geo),
        thread_id=thread_log.id if thread_log else 0,
        _log=_log,
        _err=_err,
    )

    # Initialize Vision Engine
    vision = None
    try:
        from ..vision import VisionEngine
        vision = VisionEngine("outlook", debug=True)
        _log("[Vision] Vision Engine active")
    except Exception as ve:
        logger.debug(f"[Outlook] Vision not available: {ve}")

    context = await browser_manager.create_context(proxy=proxy, geo=None)

    try:
        page = await context.new_page()
        ACTIVE_PAGES[ctx.thread_id] = {"page": page, "context": context}

        # ── Intercept Arkose Labs requests to capture blob ──
        async def _intercept_arkose(route):
            """Capture data[blob] from Arkose Labs API POST requests."""
            try:
                req = route.request
                logger.debug(f"[ARKOSE-INTERCEPT] {req.method} {req.url[:120]}")
                if req.method == "POST":
                    body = req.post_data or ""
                    blob = ""
                    # Try JSON body first
                    try:
                        jdata = _json.loads(body)
                        blob = jdata.get("blob", "")
                    except Exception:
                        pass
                    # Try form-encoded body (data[blob]=xxx)
                    if not blob and "blob" in body:
                        try:
                            parsed = _urlparse.parse_qs(body)
                            blob = parsed.get("blob", parsed.get("data[blob]", [""]))[0]
                        except Exception:
                            pass
                    if blob and len(blob) > 10:
                        ctx._arkose_blob = blob
                        ctx._log(f"[ARKOSE] Blob captured: {blob[:60]}...")
            except Exception:
                pass
            await route.continue_()

        # Route on ALL known Arkose Labs domains (context-level = covers iframes)
        arkose_patterns = [
            "**arkoselabs.com**",
            "**funcaptcha.com**",
            "**funcaptcha.co**",
            "**arkoselabs.us**",
            "**/fc/**",  # some configs use /fc/ path
        ]
        for pat in arkose_patterns:
            await context.route(pat, _intercept_arkose)

        # ALSO: Listen for ALL requests to log Arkose URLs (debug)
        def _on_request(request):
            url_lower = request.url.lower()
            if any(k in url_lower for k in ["arkose", "funcaptcha", "enforcement", "hsprotect"]):
                logger.info(f"[ARKOSE-URL] {request.method} {request.url[:200]}")

        page.on("request", _on_request)

        # ── State Machine: all steps via run_flow_machine ──
        all_steps = [
            ("warmup",        step_0_warmup,         (ctx,)),
            ("navigate",      step_1_navigate,       (ctx, proxy, db)),
            ("email_mode",    step_2_email_mode,     (ctx,)),
            ("enter_email",   step_3_enter_email,    (ctx, domain)),
            ("password",      step_4_password,       (ctx,)),
            ("birthday",      step_5_birthday,       (ctx, birthday, proxy)),
            ("name",          step_6_name,           (ctx,)),
            ("captcha",       step_7_captcha,        (ctx, captcha_provider)),
            ("post_prompts",  step_8_post_prompts,   (ctx,)),
            ("verify",        step_9_verify_success, (ctx,)),
        ]
        result = await run_flow_machine(page, ctx, all_steps, BIRTH_CANCEL_EVENT)
        if result is None:
            return None

        # ── Save session, fingerprint, and create account ──
        account = Account(
            email=ctx.email,
            password=ctx.password,
            provider=provider_name,
            first_name=ctx.first_name,
            last_name=ctx.last_name,
            gender="random",
            birthday=birthday,
            geo=proxy.geo if proxy and hasattr(proxy, 'geo') else None,
            language=ctx.language or 'en',
            birth_ip=f"{proxy.host}" if proxy else None,
            status="new",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        # Save session (cookies/localStorage) with real account ID
        try:
            account.browser_profile_path = await browser_manager.save_session(context, account.id)
            db.commit()
        except Exception as se:
            logger.warning(f"[Outlook] Session save warning: {se}")

        # Save fingerprint (GPU, UA, canvas seed) for profile persistence
        try:
            fp_data = getattr(context, '_leomail_fingerprint', None)
            if fp_data:
                browser_manager.save_fingerprint(account.id, fp_data)
                account.user_agent = fp_data.get("user_agent", "")
                db.commit()
                logger.info(f"[Outlook] Fingerprint saved for account {account.id}")
        except Exception as fp_err:
            logger.warning(f"[Outlook] Fingerprint save warning: {fp_err}")

        logger.info(f"[OK] Outlook registered: {ctx.email}")
        export_account_to_file(account)

        # IMAP verification (non-blocking, expected to fail on fresh Outlook accounts)
        # Outlook requires app password or OAuth for IMAP — regular password won't work
        try:
            from ...services.imap_checker import verify_account_imap
            await verify_account_imap(account, db, _log, _log)  # _log for errors too — IMAP fail is expected
        except Exception as imap_e:
            logger.debug(f"[Outlook] IMAP check skipped: {imap_e}")

        # Post-registration warmup — Outlook-specific
        try:
            _log("[OK] Post-reg session warmup...")
            await _outlook_post_reg_warmup(page, ctx)
        except Exception as warmup_e:
            logger.debug(f"[Outlook] Post-reg warmup error: {warmup_e}")

        return account

    except (RateLimitError, BannedIPError, CaptchaFailError, FatalError, RecoverableError):
        raise
    except Exception as e:
        logger.error(f"[FAIL] Outlook registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        raise FatalError("E599", f"Unhandled: {str(e)[:200]}")
    finally:
        ACTIVE_PAGES.pop(ctx.thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
