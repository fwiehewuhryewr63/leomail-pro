"""
Gmail AVD — Chrome-based registration with US mobile proxies
Based on gmail_avd_prod.py (the script that achieved lifecycle/phone-input)
Key: Chrome -> accounts.google.com/signup -> lifecycle page -> phone input
"""
import sys, os, time, subprocess, random, string, uuid, glob
import uiautomator2 as u2

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(__file__))

ADB = r"C:\Android\platform-tools\adb.exe"
EMU = r"C:\Android\emulator\emulator.exe"
AVD_MGR = r"C:\Android\cmdline-tools\latest\bin\avdmanager.bat"
MITMDUMP = r"C:\Users\admin\AppData\Roaming\Python\Python314\Scripts\mitmdump.exe"
SYS_IMG = "system-images;android-34;google_apis;x86_64"

from backend.modules.birth._helpers import get_sms_provider

# ─── New US Mobile Proxies (15 total) ────────────────────────
PROXIES = [
    # Format A: user:pass@host:port (residential/datacenter)
    {"host": "194.31.73.212",  "port": 29390, "user": "CDlwmTcAr9", "pass": "R2hXifz0Nr", "geo": "US"},
    {"host": "45.147.31.225",  "port": 53747, "user": "gXofvHuBi5", "pass": "KIc4g86zk8", "geo": "US"},
    {"host": "45.147.31.161",  "port": 28836, "user": "41xsFumr32", "pass": "RkRHbqEwTY", "geo": "US"},
    {"host": "194.31.73.168",  "port": 42656, "user": "6WefdPnxtg", "pass": "B8VLp7n9hX", "geo": "US"},
    {"host": "194.31.73.163",  "port": 35118, "user": "tFmS0UhCSM", "pass": "Qdir3HJ6Tf", "geo": "US"},
    # Format B: mobile proxies with US country
    {"host": "212.8.249.134",  "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c0522f", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "93.190.141.105", "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c0a241", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "190.2.137.56",   "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c0d03f", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "185.132.133.7",  "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c107fb", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "190.2.142.241",  "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c12f22", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "109.236.82.42",  "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c1545a", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "175.110.115.169","port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c178df", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "175.110.115.169","port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c19578", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "190.2.137.56",   "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c1bd6b", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
    {"host": "190.2.155.93",   "port": 443, "user": "sswop4i5mp-mobile-country-US-hold-session-session-699dfa5c1ee39", "pass": "yup4GAqgxBhYgNQh", "geo": "US"},
]

FIRST_NAMES = ["James","Michael","Robert","David","William","Daniel","Thomas","Joseph","Christopher","Matthew"]
LAST_NAMES  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Anderson","Taylor"]

# ─── Core Helpers ────────────────────────────────────────────

def human_delay(a=0.8, b=2.5):
    time.sleep(random.uniform(a, b))

def adb(*args):
    return subprocess.run([ADB] + list(args), capture_output=True, text=True, timeout=30)

def tap(x, y):
    adb("shell", "input", "tap", str(x), str(y))

def get_page(d):
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
    """Poll until old text disappears AND new text appears."""
    for i in range(timeout // 3):
        time.sleep(3)
        page = get_page(d)
        old_still = any(frag in page for frag in must_disappear)
        new_found = any(kw in page for kw in must_appear_any)
        if not old_still and new_found:
            return page
        if not old_still and not new_found:
            return page
    d.screenshot(f"TIMEOUT_{step_name}.png")
    return None

def click_next_via_scroll(d, max_tries=3):
    for attempt in range(max_tries):
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


def cleanup_all_avds():
    """Delete ALL old AVDs to avoid device fingerprint correlation."""
    print("[CLEANUP] Deleting ALL old AVDs...")
    r = subprocess.run([AVD_MGR, "list", "avd", "-c"], capture_output=True, text=True, timeout=30)
    avds = [line.strip() for line in r.stdout.strip().split("\n") if line.strip()]
    for avd in avds:
        subprocess.run([AVD_MGR, "delete", "avd", "-n", avd], capture_output=True, timeout=15)
    if avds:
        print(f"    Deleted {len(avds)} old AVDs: {', '.join(avds[:5])}{'...' if len(avds) > 5 else ''}")
    else:
        print("    No old AVDs found")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    # Auto-increment: use proxy 0 on first run, 1 on second, etc.
    # Store index in a temp file
    idx_file = os.path.join(os.path.dirname(__file__), ".gmail_proxy_idx")
    if os.path.exists(idx_file):
        with open(idx_file) as f:
            PROXY_INDEX = int(f.read().strip())
    else:
        PROXY_INDEX = 0
    
    if PROXY_INDEX >= len(PROXIES):
        print(f"❌ All {len(PROXIES)} proxies used! No more available.")
        return
    
    proxy = PROXIES[PROXY_INDEX]
    AVD_NAME = f"gmail_us_{PROXY_INDEX + 1}"
    
    # Save next index
    with open(idx_file, "w") as f:
        f.write(str(PROXY_INDEX + 1))
    
    sms = get_sms_provider("grizzly")
    bal = sms.get_balance()
    print(f"GrizzlySMS: {bal} RUB")
    
    # ── 1. Kill everything + cleanup ──────────────────────────
    print("\n[SETUP] Cleaning...")
    subprocess.run([ADB, "emu", "kill"], capture_output=True, timeout=10)
    subprocess.run(["taskkill", "/f", "/im", "mitmdump.exe"], capture_output=True)
    subprocess.run(["taskkill", "/f", "/im", "emulator.exe"], capture_output=True)
    subprocess.run(["taskkill", "/f", "/im", "qemu-system-x86_64.exe"], capture_output=True)
    time.sleep(5)
    
    # Delete ALL old AVDs
    cleanup_all_avds()
    
    # ── 2. Create fresh AVD ──────────────────────────────────
    print(f"[SETUP] Creating AVD '{AVD_NAME}' (Pixel 7)...")
    subprocess.run(
        [AVD_MGR, "create", "avd", "-n", AVD_NAME, "-k", SYS_IMG,
         "-d", "pixel_7", "--force"],
        capture_output=True, timeout=60
    )
    time.sleep(2)
    
    # ── 3. Boot — MINIMAL flags (match successful attempt) ────
    # Key: NO -no-window, NO -gpu swiftshader, NO -phone-number
    print("[SETUP] Booting (minimal flags)...")
    emu_proc = subprocess.Popen(
        [EMU, "-avd", AVD_NAME, "-no-audio", "-no-boot-anim"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    
    for i in range(60):
        time.sleep(3)
        r = adb("shell", "getprop", "sys.boot_completed")
        if r.stdout.strip() == "1":
            print(f"[SETUP] Booted ({(i+1)*3}s)")
            break
    else:
        print("  ❌ Boot timeout")
        sys.exit(1)
    
    # ── 4. Init uiautomator2 ────────────────────────────────
    print("[SETUP] Init uiautomator2...")
    subprocess.run([sys.executable, "-m", "uiautomator2", "init"],
                   capture_output=True, text=True, timeout=60)
    
    # ── 5. Start proxy ──────────────────────────────────────
    print(f"[SETUP] Proxy #{PROXY_INDEX}: {proxy['geo']} ({proxy['host']})...")
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
    
    # ── Generate persona (US English matching proxy) ─────────
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
    print(f"  Proxy #{PROXY_INDEX} / AVD: {AVD_NAME}")
    print(f"  {fname} {lname}")
    print(f"  {uname}@gmail.com / {pwd}")
    print(f"  Born: {month} {day}, {year}")
    print(f"  Proxy: {proxy['geo']} ({proxy['host']})")
    print(f"{'='*60}")
    
    try:
        # ═══════════════════════════════════════════════════════
        # STEP 0: Open Chrome + Navigate to Signup
        # ═══════════════════════════════════════════════════════
        print("\n[0] Opening Chrome → accounts.google.com/signup ...")
        adb("shell", "pm", "clear", "com.android.chrome")
        time.sleep(2)
        adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
            "-d", "https://accounts.google.com/signup")
        
        print("    Waiting 20s for page...")
        time.sleep(20)
        
        # Dismiss Chrome first-run dialogs
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
        
        fields = find_input_field(d)
        if not fields or len(fields) < 1:
            d.screenshot("s1_FAIL.png")
            print("    ❌ No input fields")
            return
        
        type_into_field(d, fields[0], fname)
        print(f"    First: {fname}")
        if len(fields) >= 2:
            type_into_field(d, fields[1], lname)
            print(f"    Last: {lname}")
        
        human_delay(2, 3)
        d.screenshot("s1.png")
        print("    Waiting 8s for page ready...")
        time.sleep(8)
        
        click_next_via_scroll(d)
        
        page = wait_page_change(
            d,
            must_disappear=["enter your name"],
            must_appear_any=["birthday", "basic information", "how", "sign in"],
            timeout=20,
            step_name="name_to_birthday"
        )
        d.screenshot("s1_after.png")
        
        if page is None:
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
        # STEP 2: Birthday + Gender (DYNAMIC — finds elements via hierarchy)
        # ═══════════════════════════════════════════════════════
        if "birthday" not in page and "basic information" not in page:
            d.screenshot("s2_UNEXPECTED.png")
            print(f"    ❌ NOT on birthday page! Got: {page[:100]}")
            return
        
        print(f"\n[2] Birthday: {month} {day}, {year} — Gender: Male")
        human_delay(3, 5)
        
        # Dump hierarchy to find actual element positions
        import xml.etree.ElementTree as ET
        
        def get_naf_elements(d):
            """Find all NAF (Not Accessibility Friendly) elements = Chrome dropdowns."""
            xml_str = d.dump_hierarchy()
            root = ET.fromstring(xml_str)
            nafs = []
            for el in root.iter():
                if el.get("NAF") == "true":
                    bounds = el.get("bounds", "")
                    if bounds:
                        # Parse [x1,y1][x2,y2]
                        parts = bounds.replace("][", ",").replace("[", "").replace("]", "").split(",")
                        if len(parts) == 4:
                            x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                            nafs.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                                        "cx": cx, "cy": cy, "class": el.get("class", ""),
                                        "text": el.get("text", ""), "bounds": bounds})
            return nafs
        
        def get_edit_texts(d):
            """Find all EditText elements with their bounds."""
            xml_str = d.dump_hierarchy()
            root = ET.fromstring(xml_str)
            edits = []
            for el in root.iter():
                if el.get("class") == "android.widget.EditText":
                    bounds = el.get("bounds", "")
                    if bounds:
                        parts = bounds.replace("][", ",").replace("[", "").replace("]", "").split(",")
                        if len(parts) == 4:
                            x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                            # Skip URL bar (top < 300)
                            if y1 > 300:
                                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                                edits.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                                             "cx": cx, "cy": cy,
                                             "text": el.get("text", ""),
                                             "resource-id": el.get("resource-id", "")})
            return edits
        
        # ---- MONTH (Spinner/dropdown — NAF element in Chrome) ----
        month_ok = False
        month_idx = month_names.index(month)
        
        for month_try in range(3):
            # Find NAF elements (Chrome renders <select> as NAF)
            nafs = get_naf_elements(d)
            edits = get_edit_texts(d)
            
            print(f"    NAF elements: {len(nafs)}, EditTexts: {len(edits)}")
            for i, naf in enumerate(nafs):
                print(f"      NAF[{i}]: class={naf['class']}, bounds={naf['bounds']}")
            for i, ed in enumerate(edits):
                print(f"      Edit[{i}]: text='{ed['text']}', rid='{ed['resource-id']}', bounds=[{ed['x1']},{ed['y1']}][{ed['x2']},{ed['y2']}]")
            
            # Month is the FIRST NAF element (or Spinner) on the birthday page
            if nafs:
                month_el = nafs[0]  # First NAF = Month dropdown
                tap(month_el["cx"], month_el["cy"])
                print(f"    Tapped Month NAF at ({month_el['cx']}, {month_el['cy']})")
            elif d(text="Month").exists(timeout=2):
                d(text="Month").click()
                print("    Tapped Month text")
            else:
                # Fallback: tap center-left of page
                tap(145, 560)
                print("    Tapped Month fallback (145, 560)")
            
            time.sleep(3)
            d.screenshot(f"s2_month_open{month_try}.png")
            
            # Try to find month text in the dropdown
            if d(text=month).exists(timeout=5):
                d(text=month).click()
                month_ok = True
                print(f"    Month: {month} ✅")
                break
            
            # Try CheckedTextView
            if d(className="android.widget.CheckedTextView", text=month).exists(timeout=2):
                d(className="android.widget.CheckedTextView", text=month).click()
                month_ok = True
                print(f"    Month: {month} ✅ (CheckedTextView)")
                break
            
            # ADB TAP FALLBACK — Chrome dropdown items invisible to uiautomator2
            # From screenshot: dropdown items at Y=635+idx*65 (Jan=0=Y635, Feb=1=Y700...)
            # Oct(idx=9) at Y=1220 is last visible. Nov/Dec need scroll.
            if month_idx <= 9:
                # Visible without scrolling
                tap_y = 635 + month_idx * 65
                tap(140, tap_y)
                time.sleep(1)
                month_ok = True
                print(f"    Month: {month} ✅ (ADB tap Y={tap_y})")
                break
            else:
                # November(10) or December(11): scroll dropdown down first
                d.swipe(140, 1200, 140, 800, duration=0.3)
                time.sleep(0.5)
                # After scroll, remaining items appear at top of visible area
                # Nov would be at ~Y=700, Dec at ~Y=765 (approximately)
                tap_y = 700 + (month_idx - 10) * 65
                tap(140, tap_y)
                time.sleep(1)
                month_ok = True
                print(f"    Month: {month} ✅ (ADB tap Y={tap_y} after scroll)")
                break
        
        if not month_ok:
            d.screenshot("s2_month_FAIL.png")
            print(f"    ❌ Month selection failed after 3 tries")
            return
        
        time.sleep(1)
        
        # ---- DAY & YEAR (EditText fields) ----
        edits = get_edit_texts(d)
        edits_sorted = sorted(edits, key=lambda e: e["x1"])  # Sort left-to-right
        
        # Filter to only fields near the birthday row (skip Month which is a dropdown)
        if len(edits_sorted) >= 2:
            type_into_field(d, d(className="android.widget.EditText").child_by_instance(0, className="android.widget.EditText") if False else None, day)
            # Use the actual elements found
            day_el = edits_sorted[0]
            year_el = edits_sorted[1]
            
            tap(day_el["cx"], day_el["cy"])
            human_delay(0.3, 0.5)
            try: d.clear_text()
            except: pass
            d.send_keys(day)
            print(f"    Day: {day} ✅ (at {day_el['cx']},{day_el['cy']})")
            
            human_delay(0.5, 1)
            
            tap(year_el["cx"], year_el["cy"])
            human_delay(0.3, 0.5)
            try: d.clear_text()
            except: pass
            d.send_keys(year)
            print(f"    Year: {year} ✅ (at {year_el['cx']},{year_el['cy']})")
        else:
            # Use resourceId fallback
            day_field = d(resourceId="day")
            if day_field.exists(timeout=3):
                type_into_field(d, day_field, day)
                print(f"    Day: {day} ✅ (resourceId)")
            
            year_field = d(resourceId="year")
            if year_field.exists(timeout=3):
                type_into_field(d, year_field, year)
                print(f"    Year: {year} ✅ (resourceId)")
        
        human_delay(1, 2)
        
        # ---- GENDER (second NAF/dropdown element) ----
        nafs = get_naf_elements(d)
        gender_el = None
        if len(nafs) >= 2:
            gender_el = nafs[1]  # Second NAF = Gender
        elif len(nafs) == 1:
            # After month selection, the first NAF might now be Gender
            gender_el = nafs[0]
        
        if gender_el:
            tap(gender_el["cx"], gender_el["cy"])
            print(f"    Tapped Gender at ({gender_el['cx']}, {gender_el['cy']})")
        elif d(text="Gender").exists(timeout=2):
            d(text="Gender").click()
            print("    Tapped Gender text")
        else:
            # Guess: Gender is below birthday row
            tap(360, 700)
            print("    Tapped Gender fallback")
        
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
        
        # Next on birthday page
        btn = d(text="Next")
        if btn.exists(timeout=5):
            btn.click()
            print("    → Birthday Next clicked")
        else:
            tap(600, 950)
            print("    → Birthday Next tapped (fallback)")
        
        page = wait_page_change(
            d,
            must_disappear=["enter your birthday", "basic information"],
            must_appear_any=["username", "how", "sign in", "gmail", "choose"],
            timeout=30,
            step_name="birthday_to_username"
        )
        d.screenshot("s2_after.png")
        
        if page is None:
            page = get_page(d)
            if any(x in page for x in ["fill in", "valid date", "complete birthday"]):
                print(f"    ❌ Birthday validation error: {page[:100]}")
                return
            # Retry
            btn = d(text="Next")
            if btn.exists(timeout=3):
                btn.click()
            else:
                tap(600, 950)
            time.sleep(8)
            page = get_page(d)
            if "birthday" in page or "basic information" in page:
                print(f"    ❌ Stuck on birthday")
                return
        
        print(f"    After: {page[:60]}")
        print("    ✅ Birthday accepted")
        
        # ═══════════════════════════════════════════════════════
        # STEP 3: Username
        # ═══════════════════════════════════════════════════════
        print(f"\n[3] Username: {uname}")
        
        if any(x in page for x in ["birthday", "basic information"]):
            print(f"    ❌ Still on birthday!")
            return
        
        human_delay(3, 5)
        
        # Handle radio buttons
        radio = d(className="android.widget.RadioButton")
        if radio.exists(timeout=3) and radio.count > 1:
            radio[1].click()
            human_delay(1, 2)
        
        fields = find_input_field(d)
        if fields:
            type_into_field(d, fields[0], uname)
            print(f"    Typed: {uname}")
        else:
            d.screenshot("s3_NO_FIELD.png")
            print("    ❌ No username field!")
            return
        
        human_delay(2, 4)
        d.screenshot("s3.png")
        click_next_via_scroll(d)
        
        page = wait_page_change(
            d,
            must_disappear=["how you", "sign in", "username"],
            must_appear_any=["password", "strong"],
            timeout=20,
            step_name="username_to_password"
        )
        d.screenshot("s3_after.png")
        
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
            print(f"    ❌ Not on password page: {(page or '')[:80]}")
            return
        
        print(f"    After: {page[:60]}")
        print("    ✅ Username accepted")
        
        # ═══════════════════════════════════════════════════════
        # STEP 4: Password
        # ═══════════════════════════════════════════════════════
        print(f"\n[4] Password: {pwd}")
        human_delay(3, 5)
        
        fields = find_input_field(d)
        if fields and len(fields) >= 2:
            type_into_field(d, fields[0], pwd)
            print("    Password typed")
            human_delay(0.8, 1.5)
            type_into_field(d, fields[1], pwd)
            print("    Confirm typed")
        elif fields and len(fields) == 1:
            type_into_field(d, fields[0], pwd)
            print("    Password typed (1 field)")
        else:
            # ADB tap fallback
            print(f"    No EditText — ADB tap fallback")
            tap(360, 715)
            human_delay(0.5, 0.8)
            try: d.clear_text()
            except: pass
            for ch in pwd:
                d.send_keys(ch)
                time.sleep(random.uniform(0.04, 0.15))
            print("    Password typed (tap)")
            human_delay(1, 2)
            tap(360, 855)
            human_delay(0.5, 0.8)
            try: d.clear_text()
            except: pass
            for ch in pwd:
                d.send_keys(ch)
                time.sleep(random.uniform(0.04, 0.15))
            print("    Confirm typed (tap)")
        
        print("    Waiting 12s for page ready...")
        time.sleep(12)
        d.screenshot("s4.png")
        click_next_via_scroll(d)
        
        print("    Waiting for verification page (30s)...")
        page = wait_page_change(
            d,
            must_disappear=["create a strong", "strong password"],
            must_appear_any=["phone", "robot", "verify", "number", "security", "add", "skip", "review"],
            timeout=30,
            step_name="password_to_phone"
        )
        d.screenshot("s4_after.png")
        
        if page is None:
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
        # STEP 5: Verification — analyze what page Google shows
        # ═══════════════════════════════════════════════════════
        print(f"\n[5] Checking verification type...")
        
        # Wait for FULL page load
        print("    Waiting 20s for verification page to load...")
        time.sleep(20)
        
        page = get_page(d)
        d.screenshot("s5.png")
        print(f"    Page: {page[:120]}")
        
        if not page.strip():
            print("    Page still empty, waiting more...")
            for i in range(10):
                time.sleep(5)
                page = get_page(d)
                if page.strip():
                    break
            d.screenshot("s5_loaded.png")
            print(f"    After wait: {page[:120]}")
        
        # ===== CLASSIFICATION: What did Google show? =====
        
        # BEST CASE: Skip/Not now available
        for skip_text in ["Skip", "Not now"]:
            if d(text=skip_text).exists(timeout=2):
                d(text=skip_text).click()
                print(f"    🎉 SKIPPED with '{skip_text}'!")
                time.sleep(5)
                page = get_page(d)
                d.screenshot("s5_skipped.png")
                # Jump to post-verification
                break
        
        # Check for phone input field (the GOOD outcome — lifecycle page)
        fields = find_input_field(d)
        phone_field = None
        
        if fields:
            phone_field = fields[0]
            print("    ✅ PHONE INPUT FOUND! (lifecycle page)")
        else:
            # BAD: Check what type of bad page
            if "send sms" in page or "your phone will open" in page:
                print("    ❌ DEVICE SMS (deviceph) — emulator detected via Chrome")
                d.screenshot("s5_deviceph.png")
                return
            
            if "verify your phone" in page and "verify" in page:
                print("    ❌ Auto-verify page — no phone input")
                d.screenshot("s5_autoverify.png")
                
                # Try: click Verify, maybe it transitions to code input
                if d(text="Verify").exists(timeout=3):
                    d(text="Verify").click()
                    print("    → Clicked Verify, waiting 15s...")
                    time.sleep(15)
                    page = get_page(d)
                    d.screenshot("s5_after_verify.png")
                    fields = find_input_field(d)
                    if fields:
                        phone_field = fields[0]
                        print("    ✅ Phone input appeared after Verify!")
                    else:
                        print(f"    ❌ Still stuck: {page[:80]}")
                        return
                else:
                    return
            
            # Try clicking any available button
            if not phone_field:
                for btn_text in ["Send SMS", "Send", "Continue", "Next", "Get code"]:
                    if d(text=btn_text).exists(timeout=2):
                        d(text=btn_text).click()
                        print(f"    → Clicked: {btn_text}")
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
                print(f"  Proxy:    #{PROXY_INDEX} {proxy['host']}")
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
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        subprocess.run(["taskkill", "/f", "/im", "mitmdump.exe"], capture_output=True)
        subprocess.run(["taskkill", "/f", "/im", "emulator.exe"], capture_output=True)
        subprocess.run(["taskkill", "/f", "/im", "qemu-system-x86_64.exe"], capture_output=True)


if __name__ == "__main__":
    main()
