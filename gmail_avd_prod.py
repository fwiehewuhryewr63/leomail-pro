"""
Gmail AVD — SINGLE careful attempt
v3: ALL page transitions verified with wait_page_change()
ALL NAF elements use ADB tap from XML hierarchy coordinates
"""
import sys, os, time, subprocess, random, string, uuid
import uiautomator2 as u2

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(__file__))

ADB = r"C:\Android\platform-tools\adb.exe"
EMU = r"C:\Android\emulator\emulator.exe"
AVD_MGR = r"C:\Android\cmdline-tools\latest\bin\avdmanager.bat"
MITMDUMP = r"C:\Users\admin\AppData\Roaming\Python\Python314\Scripts\mitmdump.exe"
SYS_IMG = "system-images;android-34;google_apis;x86_64"

from backend.modules.birth._helpers import get_sms_provider

# ─── Proxies ────────────────────────────────────────────────
PROXIES = [
    {"host": "190.2.137.56",   "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5df151f", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "93.190.141.105", "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e005f9", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "190.2.142.241",  "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e02039", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "62.112.8.229",   "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e038ed", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "89.38.99.96",    "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e0526f", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "89.38.99.96",    "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e06af1", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "109.236.82.42",  "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e08471", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "109.236.82.42",  "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e09cf8", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "212.8.249.134",  "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e0b510", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
    {"host": "62.112.8.229",   "port": 443, "user": "sswop4i5mp-mobile-country-BR-hold-session-session-699dae5e0cc4a", "pass": "yup4GAqgxBhYgNQh", "geo": "BR"},
]

FIRST_NAMES = ["James","Michael","Robert","David","William","Daniel","Thomas","Joseph","Christopher","Matthew"]
LAST_NAMES  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Anderson","Taylor"]

# ─── Core Helpers ────────────────────────────────────────────

def human_delay(a=0.8, b=2.5):
    time.sleep(random.uniform(a, b))

def adb(*args):
    return subprocess.run([ADB] + list(args), capture_output=True, text=True, timeout=30)

def tap(x, y):
    """ADB tap at exact pixel coordinates."""
    adb("shell", "input", "tap", str(x), str(y))

def get_page(d):
    """Get all visible text on screen (lowercase)."""
    texts = []
    for el in d(className="android.widget.TextView"):
        try:
            t = el.get_text()
            if t and t.strip() and len(t) > 1:
                texts.append(t.strip())
        except:
            break
    return " ".join(texts).lower()


def wait_page_change(d, must_disappear, must_appear_any, timeout=30, step_name=""):
    """
    THE CRITICAL FUNCTION — polls until:
    1) ALL strings in must_disappear are GONE from page text
    2) ANY string in must_appear_any is FOUND in page text
    
    Returns page text on success, None on timeout.
    
    This prevents the bug where old page text persists during
    server round-trip and the script proceeds too early.
    """
    for i in range(timeout // 3):
        time.sleep(3)
        page = get_page(d)
        
        # Check: ALL old text fragments must be gone
        old_still_present = any(frag in page for frag in must_disappear)
        
        # Check: ANY new text must be present
        new_found = any(kw in page for kw in must_appear_any)
        
        if not old_still_present and new_found:
            return page
        
        if not old_still_present and not new_found:
            # Old page gone but new page not recognized — return what we have
            # (Google might show a page we didn't expect)
            return page
    
    # Timeout
    d.screenshot(f"TIMEOUT_{step_name}.png")
    return None


def click_next_via_scroll(d, max_tries=3):
    """
    Click 'Next' button. Scrolls page to make it visible above keyboard.
    Used on Name, Username, Password pages (NOT birthday — birthday uses ADB tap).
    NO fallback ADB tap — that would hit birthday-specific coordinates.
    """
    for attempt in range(max_tries):
        # Scroll down a bit to reveal Next
        d.swipe(540, 1800, 540, 1200, duration=0.3)
        time.sleep(1.5)
        
        btn = d(text="Next")
        if btn.exists(timeout=3):
            btn.click()
            print(f"    → Next clicked (try {attempt+1})")
            return True
        time.sleep(2)
    
    print("    ⚠ Next button not found")
    return False


def find_input_field(d, skip_url_bar=True):
    """
    Find first EditText that's NOT the Chrome URL bar.
    URL bar has top ~144..275. Form fields have top > 400.
    Returns the element or None.
    """
    inp = d(className="android.widget.EditText")
    if not inp.exists(timeout=5):
        return None
    
    results = []
    for i in range(inp.count):
        try:
            b = inp[i].info.get("bounds", {})
            top = b.get("top", 0)
            if not skip_url_bar or top > 400:
                results.append(inp[i])
        except:
            break
    return results


def type_into_field(d, field_element, text):
    """Click field, clear it, type text character by character."""
    field_element.click()
    human_delay(0.3, 0.5)
    try:
        d.clear_text()
    except:
        pass
    human_delay(0.2, 0.4)
    for ch in text:
        d.send_keys(ch)
        time.sleep(random.uniform(0.04, 0.18))
    human_delay(0.3, 0.6)


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    # ┌─────────────────────────────────────────────────────┐
    # │  CHANGE THESE for each attempt:                     │
    # │  PROXY_INDEX  = 0..9                                │
    # │  AVD_NAME     = unique per attempt                  │
    # └─────────────────────────────────────────────────────┘
    PROXY_INDEX = 0
    AVD_NAME = "gmail_single_13"
    
    proxy = PROXIES[PROXY_INDEX]
    
    sms = get_sms_provider("grizzly")
    bal = sms.get_balance()
    print(f"GrizzlySMS: {bal} RUB")
    
    # ── 1. Kill everything ──────────────────────────────────
    print("\n[SETUP] Cleaning...")
    subprocess.run([ADB, "emu", "kill"], capture_output=True, timeout=10)
    subprocess.run(["taskkill", "/f", "/im", "mitmdump.exe"], capture_output=True)
    subprocess.run(["taskkill", "/f", "/im", "emulator.exe"], capture_output=True)
    time.sleep(5)
    
    # ── 2. Create fresh AVD ─────────────────────────────────
    print(f"[SETUP] Creating AVD '{AVD_NAME}'...")
    subprocess.run([AVD_MGR, "create", "avd", "-n", AVD_NAME, "-k", SYS_IMG,
                    "-d", "pixel_7", "--force"],
                   capture_output=True, timeout=60)
    
    # ── 3. Boot ─────────────────────────────────────────────
    print("[SETUP] Booting...")
    subprocess.Popen([EMU, "-avd", AVD_NAME, "-no-audio", "-no-boot-anim"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(60):
        time.sleep(3)
        r = adb("shell", "getprop", "sys.boot_completed")
        if r.stdout.strip() == "1":
            print(f"[SETUP] Booted ({(i+1)*3}s)")
            break
    else:
        print("BOOT TIMEOUT")
        return
    
    # ── 4. Init uiautomator2 ────────────────────────────────
    print("[SETUP] Init uiautomator2...")
    subprocess.run([sys.executable, "-m", "uiautomator2", "init"],
                   capture_output=True, text=True, timeout=60)
    
    # ── 5. Start proxy ──────────────────────────────────────
    print(f"[SETUP] Proxy: {proxy['geo']} ({proxy['host']})...")
    subprocess.Popen(
        [MITMDUMP, "--mode", f"upstream:http://{proxy['host']}:{proxy['port']}",
         "--listen-port", "8888",
         "--set", f"upstream_auth={proxy['user']}:{proxy['pass']}",
         "--ignore-hosts", "."],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    adb("shell", "settings", "put", "global", "http_proxy", "10.0.2.2:8888")
    
    # ── 6. Connect ──────────────────────────────────────────
    d = u2.connect("emulator-5554")
    w, h = d.window_size()
    print(f"[SETUP] Screen: ({w}, {h})")
    
    # ── Generate persona ────────────────────────────────────
    fname = random.choice(FIRST_NAMES)
    lname = random.choice(LAST_NAMES)
    uname = f"{fname.lower()}.{lname.lower()}.{random.randint(10000,99999)}"
    pwd   = f"{fname[0]}{lname[0]}{random.randint(100,999)}!{random.choice(['xK','mP','qR','tW','zN'])}{random.randint(10,99)}"
    year  = str(random.randint(1990, 2000))
    day   = str(random.randint(1, 28))
    month_names = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    month = random.choice(month_names)
    
    print(f"\n{'='*60}")
    print(f"  {fname} {lname}")
    print(f"  {uname}@gmail.com / {pwd}")
    print(f"  Born: {month} {day}, {year}")
    print(f"  Proxy: {proxy['geo']} ({proxy['host']})")
    print(f"{'='*60}")
    
    # ═══════════════════════════════════════════════════════
    # STEP 0: Open Chrome + Navigate to Signup
    # ═══════════════════════════════════════════════════════
    print("\n[0] Opening Chrome...")
    adb("shell", "pm", "clear", "com.android.chrome")
    time.sleep(2)
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
        "-d", "https://accounts.google.com/signup")
    
    print("    Waiting 20s for page...")
    time.sleep(20)
    
    # Dismiss Chrome first-run dialogs (loop multiple times)
    for _ in range(5):
        for txt in ["Accept & continue", "No thanks", "No, thanks",
                    "Use without an account", "Got it"]:
            if d(text=txt).exists(timeout=2):
                d(text=txt).click()
                print(f"    Dismissed: {txt}")
                human_delay(0.5, 1)
    
    human_delay(3, 5)
    d.screenshot("s0.png")
    page = get_page(d)
    print(f"    Page: {page[:80]}")
    
    if "create" not in page and "name" not in page:
        if d(text="Create account").exists(timeout=3):
            d(text="Create account").click()
            human_delay(2, 3)
            if d(textContains="personal").exists(timeout=3):
                d(textContains="personal").click()
                human_delay(3, 5)
            page = get_page(d)
        if "create" not in page and "name" not in page:
            d.screenshot("s0_FAIL.png")
            print(f"    ❌ Not on signup. Check s0_FAIL.png")
            return
    
    print("    ✅ Signup loaded")
    
    # ═══════════════════════════════════════════════════════
    # STEP 1: Name
    # ═══════════════════════════════════════════════════════
    print(f"\n[1] Entering name: {fname} {lname}")
    human_delay(2, 4)
    
    # Find form fields (skip URL bar at top=144)
    fields = find_input_field(d)
    if not fields or len(fields) < 1:
        d.screenshot("s1_FAIL.png")
        print("    ❌ No input fields found. Check s1_FAIL.png")
        return
    
    # Type first name
    type_into_field(d, fields[0], fname)
    print(f"    First: {fname}")
    
    # Type last name (if second field exists)
    if len(fields) >= 2:
        type_into_field(d, fields[1], lname)
        print(f"    Last: {lname}")
    
    human_delay(2, 3)
    d.screenshot("s1.png")
    
    # Wait for page to fully load (loading bar must complete)
    # s1_after.png from attempt 9 showed Next was greyed = page loading
    print("    Waiting 8s for page ready...")
    time.sleep(8)
    
    # Click Next
    click_next_via_scroll(d)
    
    # WAIT for page to change: "enter your name" must disappear
    page = wait_page_change(
        d,
        must_disappear=["enter your name"],
        must_appear_any=["birthday", "basic information", "how", "sign in"],
        timeout=20,
        step_name="name_to_birthday"
    )
    d.screenshot("s1_after.png")
    
    if page is None:
        # Timeout — try clicking Next again
        print("    Timeout. Retrying Next...")
        click_next_via_scroll(d)
        page = wait_page_change(
            d,
            must_disappear=["enter your name"],
            must_appear_any=["birthday", "basic information"],
            timeout=15,
            step_name="name_retry"
        )
        if page is None:
            print("    ❌ Stuck on name page")
            return
    
    print(f"    After: {page[:60]}")
    print("    ✅ Name accepted")
    
    # ═══════════════════════════════════════════════════════
    # STEP 2: Birthday + Gender
    #   XML coordinates (avd_step5_hierarchy.xml):
    #   Month: NAF Spinner [63,850][370,997]  → tap(216, 923)
    #   Day:   EditText    [391,852][690,994] → resourceId="day"
    #   Year:  EditText    [716,852][1015,994]→ resourceId="year"
    #   Gender:NAF Spinner [63,1088][1021,1241]→ tap(542, 1164)
    #   Next:  View        [811,1501][1021,1642]→ tap(916, 1571)
    # ═══════════════════════════════════════════════════════
    
    # Verify we're ACTUALLY on birthday page before interacting
    if "birthday" not in page and "basic information" not in page:
        d.screenshot("s2_UNEXPECTED.png")
        print(f"    ❌ NOT on birthday page! Got: {page[:100]}")
        print("    Check s2_UNEXPECTED.png")
        return
    
    print(f"\n[2] Birthday: {month} {day}, {year} — Gender: Male")
    human_delay(3, 5)
    
    # -------- Month (ADB tap → native picker) --------
    tap(216, 923)
    print("    Tapped month field")
    human_delay(2, 3)
    
    # Select month from Chrome's native picker popup
    month_ok = False
    if d(text=month).exists(timeout=5):
        d(text=month).click()
        month_ok = True
        print(f"    Month: {month} ✅")
    else:
        # Scroll picker to find month
        d.swipe(350, 1400, 350, 800)
        time.sleep(0.5)
        if d(text=month).exists(timeout=3):
            d(text=month).click()
            month_ok = True
            print(f"    Month: {month} (scroll) ✅")
        else:
            for m in month_names:
                if d(text=m).exists(timeout=0.3):
                    d(text=m).click()
                    month = m
                    month_ok = True
                    print(f"    Month: {m} (fallback) ✅")
                    break
    
    if not month_ok:
        d.screenshot("s2_month_FAIL.png")
        print("    ❌ Month picker empty!")
        return
    
    human_delay(1.5, 3)
    
    # -------- Day (EditText by resourceId) --------
    day_field = d(resourceId="day")
    if day_field.exists(timeout=3):
        type_into_field(d, day_field, day)
    else:
        tap(540, 923)
        human_delay(0.5, 0.8)
        try: d.clear_text()
        except: pass
        d.send_keys(day)
    print(f"    Day: {day} ✅")
    human_delay(0.8, 1.5)
    
    # -------- Year (EditText by resourceId) --------
    year_field = d(resourceId="year")
    if year_field.exists(timeout=3):
        type_into_field(d, year_field, year)
    else:
        tap(865, 923)
        human_delay(0.5, 0.8)
        try: d.clear_text()
        except: pass
        d.send_keys(year)
    print(f"    Year: {year} ✅")
    human_delay(1, 2)
    
    # -------- Gender (ADB tap → native picker) --------
    tap(542, 1164)
    print("    Tapped gender field")
    human_delay(2, 3)
    if d(text="Male").exists(timeout=5):
        d(text="Male").click()
        print("    Gender: Male ✅")
    else:
        d.screenshot("s2_gender_FAIL.png")
        print("    ❌ Gender picker problem!")
        return
    
    human_delay(2, 4)
    d.screenshot("s2.png")
    print("    📸 s2.png saved — verify fields visually")
    
    # -------- Next on birthday page --------
    # DON'T use ADB tap — XML coordinates were from error state page!
    # Use text-based click which works regardless of button position.
    btn = d(text="Next")
    if btn.exists(timeout=5):
        btn.click()
        print("    → Birthday Next clicked")
    else:
        # Fallback: try ADB tap at the position from screenshot analysis
        tap(600, 950)
        print("    → Birthday Next tapped (fallback)")
    
    # CRITICAL: Wait until birthday page ACTUALLY disappears
    page = wait_page_change(
        d,
        must_disappear=["enter your birthday", "basic information"],
        must_appear_any=["username", "how", "sign in", "gmail", "choose"],
        timeout=30,
        step_name="birthday_to_username"
    )
    d.screenshot("s2_after.png")
    
    if page is None:
        # Check if validation error
        page = get_page(d)
        if any(x in page for x in ["fill in", "valid date", "please enter a valid", "complete birthday"]):
            print(f"    ❌ Birthday validation error: {page[:100]}")
        else:
            # Retap Next
            print("    Retapping birthday Next...")
            btn = d(text="Next")
            if btn.exists(timeout=3):
                btn.click()
            else:
                tap(600, 950)
            time.sleep(8)
            page = get_page(d)
            if "birthday" in page or "basic information" in page:
                d.screenshot("s2_stuck.png")
                print(f"    ❌ Stuck on birthday after retry: {page[:100]}")
                return
        if page and not any(x in page for x in ["username","how","sign in","gmail","choose"]):
            return
    
    print(f"    After: {page[:60]}")
    print("    ✅ Birthday accepted — page changed")
    
    # ═══════════════════════════════════════════════════════
    # STEP 3: Username
    # ═══════════════════════════════════════════════════════
    print(f"\n[3] Username: {uname}")
    
    # VERIFY we're on username page (not still on birthday!)
    if any(x in page for x in ["birthday", "basic information", "enter your birthday"]):
        d.screenshot("s3_WRONG_PAGE.png")
        print(f"    ❌ Still on birthday page! Check s3_WRONG_PAGE.png")
        return
    
    human_delay(3, 5)
    
    # Handle radio buttons (create own vs suggested Gmail address)
    radio = d(className="android.widget.RadioButton")
    if radio.exists(timeout=3) and radio.count > 1:
        radio[1].click()  # Second option = "Create your own"
        human_delay(1, 2)
    
    # Find form input for username
    fields = find_input_field(d)
    if fields:
        type_into_field(d, fields[0], uname)
        print(f"    Typed: {uname}")
    else:
        d.screenshot("s3_NO_FIELD.png")
        print("    ❌ No username input field! Check s3_NO_FIELD.png")
        return
    
    human_delay(2, 4)
    d.screenshot("s3.png")
    click_next_via_scroll(d)
    
    # Wait for password page ("strong password" or "create a strong")
    page = wait_page_change(
        d,
        must_disappear=["how you", "sign in", "username"],
        must_appear_any=["password", "strong"],
        timeout=20,
        step_name="username_to_password"
    )
    d.screenshot("s3_after.png")
    
    # Handle "username taken"
    if page and ("taken" in page or "already" in page):
        uname = f"{fname.lower()}.{lname.lower()}.{random.randint(10000,99999)}"
        print(f"    Username taken! Retrying: {uname}")
        fields = find_input_field(d)
        if fields:
            type_into_field(d, fields[0], uname)
        click_next_via_scroll(d)
        page = wait_page_change(
            d,
            must_disappear=["taken", "already"],
            must_appear_any=["password", "strong"],
            timeout=20,
            step_name="username_retry"
        )
    
    if page is None or ("password" not in page and "strong" not in page):
        print(f"    ❌ Not on password page. Page: {(page or '')[:80]}")
        return
    
    print(f"    After: {page[:60]}")
    print("    ✅ Username accepted")
    
    # ═══════════════════════════════════════════════════════
    # STEP 4: Password
    # ═══════════════════════════════════════════════════════
    print(f"\n[4] Password: {pwd}")
    human_delay(3, 5)
    
    # Try multiple strategies to find password fields
    fields = find_input_field(d)
    
    if fields and len(fields) >= 2:
        # Strategy 1: EditText found — use them directly
        type_into_field(d, fields[0], pwd)
        print("    Password typed (EditText)")
        human_delay(0.8, 1.5)
        type_into_field(d, fields[1], pwd)
        print("    Confirm typed (EditText)")
    else:
        # Strategy 2: Fields not found as EditText (common in WebView password inputs)
        # From s4_FAIL.png screenshot: Password field ~center (360,715), Confirm ~(360,855)
        # Keyboard is already open with Password field focused
        print(f"    EditText found: {len(fields) if fields else 0} — using ADB tap fallback")
        
        # Tap Password field + type
        tap(360, 715)
        human_delay(0.5, 0.8)
        try: d.clear_text()
        except: pass
        human_delay(0.3, 0.5)
        for ch in pwd:
            d.send_keys(ch)
            time.sleep(random.uniform(0.04, 0.15))
        print("    Password typed (tap)")
        human_delay(1, 2)
        
        # Tap Confirm field + type
        tap(360, 855)
        human_delay(0.5, 0.8)
        try: d.clear_text()
        except: pass
        human_delay(0.3, 0.5)
        for ch in pwd:
            d.send_keys(ch)
            time.sleep(random.uniform(0.04, 0.15))
        print("    Confirm typed (tap)")
    
    
    
    # CRITICAL: Wait for page to finish loading
    # (loading bar at top takes ~8-12s after typing, Next is greyed until done)
    print("    Waiting 12s for page ready...")
    time.sleep(12)
    
    d.screenshot("s4.png")
    print("    📸 s4.png saved")
    click_next_via_scroll(d)
    
    # Wait for the verification page
    print("    Waiting for verification page (30s)...")
    page = wait_page_change(
        d,
        must_disappear=["create a strong", "strong password"],
        must_appear_any=["phone", "robot", "verify", "number", "security", "add", "skip"],
        timeout=30,
        step_name="password_to_phone"
    )
    d.screenshot("s4_after.png")
    
    if page is None:
        # Retry
        print("    Retrying password Next...")
        time.sleep(8)
        click_next_via_scroll(d)
        time.sleep(10)
        page = get_page(d)
        d.screenshot("s4_retry.png")
        if "strong" in page or "password" in page:
            print("    ❌ Stuck on password page")
            return
    
    print(f"    After: {page[:80]}")
    print("    ✅ Password accepted")
    
    # ═══════════════════════════════════════════════════════
    # STEP 5: Verification — handle ANY page Google shows
    # ═══════════════════════════════════════════════════════
    print(f"\n[5] Checking verification type...")
    
    # CRITICAL: Wait for page to FULLY LOAD
    # Last attempt showed deviceph URL with blank page + loading bar
    print("    Waiting 20s for verification page to load...")
    time.sleep(20)
    
    page = get_page(d)
    d.screenshot("s5.png")
    print(f"    Page: {page[:120]}")
    
    # If page is still empty, poll more
    if not page.strip():
        print("    Page still empty, waiting more...")
        for i in range(10):
            time.sleep(5)
            page = get_page(d)
            if page.strip():
                break
            print(f"    Still empty ({(i+1)*5}s)...")
        d.screenshot("s5_loaded.png")
        print(f"    After wait: {page[:120]}")
    
    # Try to find phone input field FIRST (works for all page types)
    fields = find_input_field(d)
    phone_field = None
    
    if fields:
        phone_field = fields[0]
        print("    ✅ PHONE INPUT FOUND!")
    else:
        # No input field yet — maybe device SMS page with Send button
        print(f"    No phone input. Checking for buttons...")
        d.screenshot("s5_no_input.png")
        
        # Try clicking Send SMS / Send / Continue / Next
        for btn_text in ["Send SMS", "Send", "Continue", "Next", "Verify", "Get code"]:
            if d(text=btn_text).exists(timeout=2):
                d(text=btn_text).click()
                print(f"    → Clicked: {btn_text}")
                time.sleep(15)
                page = get_page(d)
                d.screenshot("s5_after_click.png")
                print(f"    After click: {page[:100]}")
                
                # Check if phone input appeared
                fields = find_input_field(d)
                if fields:
                    phone_field = fields[0]
                    print("    ✅ Phone input appeared!")
                break
        
        if not phone_field:
            # Last resort: try textContains
            for btn_text in ["send", "sms", "continue", "verify", "code"]:
                if d(textContains=btn_text).exists(timeout=1):
                    d(textContains=btn_text).click()
                    print(f"    → Clicked (contains): {btn_text}")
                    time.sleep(15)
                    fields = find_input_field(d)
                    if fields:
                        phone_field = fields[0]
                        print("    ✅ Phone input appeared!")
                    break
    
    if not phone_field:
        d.screenshot("s5_FINAL.png")
        print(f"    ❌ Could not find phone input")
        print(f"    Final page: {page[:150]}")
        return
    
    print("    → Proceeding with phone verification")
    
    # ═══════════════════════════════════════════════════════
    # STEP 6: Enter phone number (GrizzlySMS)
    # ═══════════════════════════════════════════════════════
    print(f"\n[6] Ordering phone number...")
    order = sms.order_number("gmail", "auto")
    if "error" in order:
        print(f"    ❌ GrizzlySMS error: {order['error']}")
        return
    
    order_id = order["id"]
    phone = order["number"]
    print(f"    Number: +{phone}")
    
    human_delay(2, 4)
    type_into_field(d, phone_field, f"+{phone}")
    
    sms.set_status(order_id, 1)
    human_delay(2, 3)
    d.screenshot("s6.png")
    click_next_via_scroll(d)
    
    print("    Waiting for Google response (15s)...")
    time.sleep(15)
    d.screenshot("s6_after.png")
    page = get_page(d)
    print(f"    Page: {page[:80]}")
    
    if "can't" in page or "cannot" in page or "isn't" in page:
        print("    ❌ Number rejected by Google")
        sms.cancel_number(order_id)
        return
    
    # ═══════════════════════════════════════════════════════
    # STEP 7: Wait for SMS code
    # ═══════════════════════════════════════════════════════
    print(f"\n[7] Waiting for SMS code (5 min max)...")
    code = sms.get_sms_code(order_id, 300)
    
    if not code or isinstance(code, dict):
        print("    ❌ No SMS code received")
        sms.cancel_number(order_id)
        return
    
    code = str(code)
    print(f"    ✅ CODE: {code}")
    
    human_delay(2, 4)
    fields = find_input_field(d)
    if fields:
        type_into_field(d, fields[0], code)
    
    human_delay(2, 3)
    d.screenshot("s7.png")
    
    for btn in ["Next", "Verify"]:
        if d(text=btn).click_exists(timeout=2):
            print(f"    → {btn}")
            break
    
    time.sleep(8)
    sms.complete_activation(order_id)
    
    # ═══════════════════════════════════════════════════════
    # STEP 8: Post-verification (skip all optional screens)
    # ═══════════════════════════════════════════════════════
    print(f"\n[8] Post-verification...")
    for step in range(15):
        pg = get_page(d)
        d.screenshot(f"s8_{step}.png")
        
        if any(x in pg for x in ["welcome", "inbox", "myaccount"]):
            print(f"\n{'='*60}")
            print(f"  ✅✅✅ GMAIL CREATED! ✅✅✅")
            print(f"  Email:    {uname}@gmail.com")
            print(f"  Password: {pwd}")
            print(f"  Phone:    +{phone}")
            print(f"{'='*60}")
            return
        
        for btn in ["Skip", "Not now", "I agree", "Accept", "Confirm", "Next", "Done"]:
            if d(text=btn).click_exists(timeout=1):
                print(f"    → {btn}")
                human_delay(2, 4)
                break
            if d(textContains=btn).click_exists(timeout=0.5):
                print(f"    → {btn}")
                human_delay(2, 4)
                break
        human_delay(2, 3)
    
    d.screenshot("s8_FINAL.png")
    print(f"\n  Possibly OK: {uname}@gmail.com / {pwd}")


if __name__ == "__main__":
    main()
