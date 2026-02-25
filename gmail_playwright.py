"""
Gmail Registration via Playwright + Mobile Proxies + GrizzlySMS
- Desktop browser = no emulator detection
- Playwright has native proxy auth support (no mitmdump needed!)
- Human-like behavior (typing delays, random pauses)
- GrizzlySMS real-SIM verification
- Rotates through mobile proxies with fresh fingerprint per attempt
"""
import sys, os, time, random, string, asyncio
from playwright.async_api import async_playwright

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(__file__))
from backend.modules.birth._helpers import get_sms_provider

# ─── Proxies ───
MOBILE_PROXIES = [
    {"host": "185.132.133.7",  "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699cc8e852d51", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "190.2.137.56",   "port": 443, "user": "sswop4i5mp-mobile-country-MX-hold-session-session-699cc8f51d9c5", "pass": "yup4GAqgxBhYgNQh", "geo": "MX"},
    {"host": "89.38.99.96",    "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699cc901e34fc", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "62.112.8.229",   "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699cc92ae19de", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "93.190.141.105", "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699b5efe45ce8", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "190.2.155.93",   "port": 443, "user": "sswop4i5mp-mobile-country-MX-hold-session-session-699b5f1a4ba52", "pass": "yup4GAqgxBhYgNQh", "geo": "MX"},
    {"host": "93.190.141.57",  "port": 443, "user": "sswop4i5mp-mobile-country-BR-state-3455077-hold-session-session-699b5ec7bf4ed", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
]


async def human_delay(a=0.8, b=2.5):
    await asyncio.sleep(random.uniform(a, b))


async def human_type(page, selector, text, clear=True):
    """Type text character by character with human delays."""
    el = page.locator(selector)
    await el.click()
    await human_delay(0.3, 0.6)
    if clear:
        await el.fill("")
        await human_delay(0.2, 0.4)
    for ch in text:
        await page.keyboard.type(ch, delay=random.randint(50, 180))
    await human_delay(0.3, 0.7)


async def human_type_el(el, text, page):
    """Type into an element handle."""
    await el.click()
    await human_delay(0.3, 0.6)
    await el.fill("")
    await human_delay(0.2, 0.4)
    for ch in text:
        await page.keyboard.type(ch, delay=random.randint(50, 180))
    await human_delay(0.3, 0.7)


async def do_attempt(proxy, attempt_num, sms):
    """One registration attempt with given proxy."""
    print(f"\n{'='*60}")
    print(f"  ATTEMPT {attempt_num} | Proxy: {proxy['geo']} ({proxy['host']})")
    
    # Generate persona
    fnames = ["James","Michael","Robert","David","William","Carlos","Daniel",
              "Thomas","Joseph","Christopher","Matthew","Andrew","Ryan","Brandon"]
    lnames = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller",
              "Davis","Rodriguez","Martinez","Anderson","Taylor","Thomas","Jackson"]
    fname = random.choice(fnames)
    lname = random.choice(lnames)
    suffix = random.randint(1000, 99999)
    uname = f"{fname.lower()}.{lname.lower()}.{suffix}"
    pwd = f"{fname[0]}{lname[0]}_{random.randint(1000,9999)}!{random.choice(['xK','mP','qR','tW','zN'])}"
    
    year = str(random.randint(1990, 2002))
    day = str(random.randint(1, 28))
    month_idx = random.randint(0, 11)
    months_en = ["January","February","March","April","May","June",
                 "July","August","September","October","November","December"]
    month = months_en[month_idx]
    
    print(f"  {fname} {lname} | {uname}@gmail.com")
    print(f"{'='*60}")
    
    async with async_playwright() as p:
        # Launch browser with proxy (Playwright handles auth natively!)
        browser = await p.chromium.launch(
            headless=False,
            proxy={
                "server": f"http://{proxy['host']}:{proxy['port']}",
                "username": proxy["user"],
                "password": proxy["pass"],
            },
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-infobars",
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )
        context.set_default_timeout(60000)
        context.set_default_navigation_timeout(60000)
        
        # Remove webdriver flag
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => false});
        """)
        
        page = await context.new_page()
        result = None
        
        try:
            # ── STEP 0: Navigate to signup ──
            print("\n[0] Opening signup...")
            await page.goto("https://accounts.google.com/signup", wait_until="domcontentloaded", timeout=60000)
            await human_delay(3, 6)
            try:
                await page.screenshot(path=f"pw_a{attempt_num}_s0.png", timeout=10000)
            except: pass
            
            title = await page.title()
            content = await page.content()
            print(f"  Title: {title[:50]}")
            
            # Check if we're on signup page
            if "Create" not in content and "name" not in content.lower():
                # Maybe redirected to sign-in
                create_btn = page.locator("text=Create account")
                if await create_btn.count() > 0:
                    await create_btn.first.click()
                    await human_delay(2, 3)
                    personal = page.locator("text=For my personal use")
                    if await personal.count() > 0:
                        await personal.click()
                        await human_delay(2, 4)
                        await page.wait_for_load_state("domcontentloaded")
            
            # ── STEP 1: Name ──
            print("\n[1] Name...")
            await human_delay(1.5, 3)
            
            first_input = page.locator('input[name="firstName"]')
            last_input = page.locator('input[name="lastName"]')
            
            if await first_input.count() > 0:
                await human_type_el(first_input, fname, page)
                await human_delay(0.5, 1.5)
                await human_type_el(last_input, lname, page)
                print(f"  {fname} {lname}")
            else:
                # Try generic inputs
                inputs = page.locator("input[type='text']")
                if await inputs.count() >= 2:
                    await human_type_el(inputs.nth(0), fname, page)
                    await human_delay(0.5, 1.5)
                    await human_type_el(inputs.nth(1), lname, page)
                    print(f"  {fname} {lname}")
            
            await human_delay(1, 2)
            await page.locator("button:has-text('Next')").click()
            await human_delay(3, 5)
            await page.wait_for_load_state("domcontentloaded")
            await page.screenshot(path=f"pw_a{attempt_num}_s1.png")
            
            # ── STEP 2: Birthday + Gender ──
            print("\n[2] Birthday...")
            await human_delay(1.5, 3)
            
            # Month select
            month_select = page.locator("select#month")
            if await month_select.count() > 0:
                await month_select.select_option(value=str(month_idx + 1))
                print(f"  Month={month}")
            
            # Day
            day_input = page.locator("input#day")
            if await day_input.count() > 0:
                await human_type_el(day_input, day, page)
            
            # Year
            year_input = page.locator("input#year")
            if await year_input.count() > 0:
                await human_type_el(year_input, year, page)
            print(f"  Day={day}, Year={year}")
            
            # Gender
            gender_select = page.locator("select#gender")
            if await gender_select.count() > 0:
                await gender_select.select_option(value="1")  # 1=Male
                print("  Gender=Male")
            
            await human_delay(1, 3)
            await page.locator("button:has-text('Next')").click()
            await human_delay(3, 5)
            await page.wait_for_load_state("domcontentloaded")
            await page.screenshot(path=f"pw_a{attempt_num}_s2.png")
            
            # Check stuck on birthday
            body = (await page.content()).lower()
            if "fill in a complete" in body or "enter a valid" in body:
                print("  ❌ Birthday validation error")
                result = "birthday_fail"
                return result
            
            # ── STEP 3: Username ──
            print("\n[3] Username...")
            await human_delay(2, 4)
            
            # Check for "Create your own" radio
            create_own = page.locator("text=Create your own Gmail address")
            if await create_own.count() > 0:
                await create_own.click()
                await human_delay(1, 2)
            
            username_input = page.locator("input[name='Username']")
            if await username_input.count() == 0:
                username_input = page.locator("input[type='text']").first
            
            await human_type_el(username_input, uname, page)
            print(f"  {uname}")
            
            await human_delay(1, 3)
            await page.locator("button:has-text('Next')").click()
            await human_delay(3, 5)
            await page.wait_for_load_state("domcontentloaded")
            await page.screenshot(path=f"pw_a{attempt_num}_s3.png")
            
            # Username taken?
            body = (await page.content()).lower()
            if "already" in body or "taken" in body:
                uname = f"{fname.lower()}.{lname.lower()}.{random.randint(10000,99999)}"
                print(f"  Taken! Trying: {uname}")
                await username_input.fill("")
                await human_type_el(username_input, uname, page)
                await page.locator("button:has-text('Next')").click()
                await human_delay(3, 5)
                await page.wait_for_load_state("domcontentloaded")
            
            # ── STEP 4: Password ──
            print("\n[4] Password...")
            await human_delay(2, 4)
            
            pwd_input = page.locator("input[name='Passwd']")
            confirm_input = page.locator("input[name='PasswdAgain']")
            
            if await pwd_input.count() > 0:
                await human_type_el(pwd_input, pwd, page)
                await human_delay(0.5, 1.5)
                if await confirm_input.count() > 0:
                    await human_type_el(confirm_input, pwd, page)
                print(f"  Password: {'*' * len(pwd)}")
            
            await human_delay(1, 3)
            await page.locator("button:has-text('Next')").click()
            
            # Wait for phone page
            print("  Waiting for verification page...")
            await human_delay(5, 8)
            await page.wait_for_load_state("domcontentloaded")
            await page.screenshot(path=f"pw_a{attempt_num}_s4.png")
            
            body = (await page.content()).lower()
            url = page.url
            print(f"  URL: {url[:60]}")
            
            # ── KEY CHECK ──
            if "deviceph" in url or "send sms" in body:
                print("  ❌ Device SMS verification")
                result = "device_sms"
                return result
            
            # Look for phone input
            phone_input = page.locator("input[type='tel']")
            if await phone_input.count() == 0:
                phone_input = page.locator("input#phoneNumberId")
            
            if await phone_input.count() == 0:
                # Try any text input on this page
                inputs = page.locator("input")
                found = False
                for i in range(await inputs.count()):
                    inp_type = await inputs.nth(i).get_attribute("type") or ""
                    if inp_type in ["tel", "text", "number"]:
                        phone_input = inputs.nth(i)
                        found = True
                        break
                if not found:
                    print(f"  ❌ No phone input found")
                    result = "no_phone_input"
                    return result
            
            print("  ✅ PHONE INPUT FOUND!")
            
            # ── STEP 5: Phone verification ──
            print("\n[5] Phone verification...")
            order = sms.order_number("gmail", "auto")
            if "error" in order:
                print(f"  GrizzlySMS error: {order['error']}")
                result = "sms_error"
                return result
            
            order_id = order["id"]
            phone = order["number"]
            country = order.get("country", "?")
            print(f"  Number: +{phone} ({country})")
            
            await human_delay(2, 4)
            await human_type_el(phone_input, f"+{phone}", page)
            
            sms.set_status(order_id, 1)
            await human_delay(1, 2)
            
            next_btn = page.locator("button:has-text('Next')")
            if await next_btn.count() > 0:
                await next_btn.click()
            await human_delay(5, 8)
            await page.wait_for_load_state("domcontentloaded")
            await page.screenshot(path=f"pw_a{attempt_num}_s5.png")
            
            body = (await page.content()).lower()
            if "cannot" in body or "can't be used" in body:
                print("  Number rejected!")
                sms.cancel_number(order_id)
                result = "number_rejected"
                return result
            
            # ── STEP 6: Wait SMS ──
            print(f"\n[6] Waiting for SMS (5 min)...")
            code_result = sms.get_sms_code(order_id, 300)
            
            if not code_result or isinstance(code_result, dict):
                print(f"  SMS FAILED")
                sms.cancel_number(order_id)
                result = "sms_timeout"
                return result
            
            code = str(code_result)
            print(f"  CODE: {code}")
            
            await human_delay(2, 4)
            code_input = page.locator("input[type='tel']")
            if await code_input.count() == 0:
                code_input = page.locator("input").first
            await human_type_el(code_input, code, page)
            
            await human_delay(1, 2)
            next_btn = page.locator("button:has-text('Next')")
            verify_btn = page.locator("button:has-text('Verify')")
            if await next_btn.count() > 0:
                await next_btn.click()
            elif await verify_btn.count() > 0:
                await verify_btn.click()
            
            await human_delay(5, 8)
            await page.wait_for_load_state("domcontentloaded")
            sms.complete_activation(order_id)
            print("  Activation OK!")
            
            # ── Post-verification ──
            for step in range(10):
                body = (await page.content()).lower()
                if any(x in body for x in ["welcome", "myaccount", "mail.google"]):
                    await page.screenshot(path=f"pw_a{attempt_num}_SUCCESS.png")
                    print(f"\n  ✅ GMAIL CREATED: {uname}@gmail.com / {pwd}")
                    result = {"email": f"{uname}@gmail.com", "password": pwd, "phone": phone}
                    return result
                
                await human_delay(1, 3)
                for btn_text in ["Skip", "Not now", "I agree", "Accept", "Confirm", "Next", "Done"]:
                    btn = page.locator(f"button:has-text('{btn_text}')")
                    if await btn.count() > 0:
                        await btn.first.click()
                        print(f"    -> {btn_text}")
                        await human_delay(2, 4)
                        break
                    link = page.locator(f"text='{btn_text}'")
                    if await link.count() > 0:
                        await link.first.click()
                        print(f"    -> {btn_text}")
                        await human_delay(2, 4)
                        break
            
            await page.screenshot(path=f"pw_a{attempt_num}_FINAL.png")
            result = {"email": f"{uname}@gmail.com", "password": pwd, "phone": phone, "note": "check screenshot"}
            return result
            
        except Exception as e:
            print(f"  ERROR: {e}")
            try:
                await page.screenshot(path=f"pw_a{attempt_num}_ERROR.png", timeout=5000)
            except: pass
            result = f"error: {e}"
            return result
        finally:
            await browser.close()


async def main():
    sms = get_sms_provider("grizzly")
    bal = sms.get_balance()
    print(f"GrizzlySMS: {bal} RUB")
    
    proxies = MOBILE_PROXIES.copy()
    random.shuffle(proxies)
    
    for i, proxy in enumerate(proxies):
        result = await do_attempt(proxy, i + 1, sms)
        
        if isinstance(result, dict):
            print(f"\n\n{'='*60}")
            print(f"  SUCCESS: {result}")
            print(f"{'='*60}")
            break
        elif result == "device_sms":
            print(f"  Device SMS — next proxy...")
            await asyncio.sleep(3)
        else:
            print(f"  Failed: {result} — next...")
            await asyncio.sleep(3)
    
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
