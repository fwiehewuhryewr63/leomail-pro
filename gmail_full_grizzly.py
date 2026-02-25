"""
Full Gmail registration on AVD: fresh signup + GrizzlySMS verification.
One-shot script — does everything from scratch.
"""
import sys
import os
import time
import subprocess
import random
import uiautomator2 as u2

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(__file__))
ADB = "C:\\Android\\platform-tools\\adb.exe"

from backend.modules.birth._helpers import get_sms_provider


def get_texts(d):
    texts = []
    for el in d(className="android.widget.TextView"):
        try:
            t = el.get_text()
            if t and t.strip() and len(t) > 1:
                texts.append(t.strip())
        except:
            break
    return texts


def main():
    sms = get_sms_provider("grizzly")
    bal = sms.get_balance()
    print(f"GrizzlySMS: {bal} RUB")

    d = u2.connect("emulator-5554")
    print(f"Device: {d.window_size()}")

    # === STEP 0: Fresh Chrome + navigate to signup ===
    print("\n[0] Fresh start...")
    subprocess.run([ADB, "shell", "pm", "clear", "com.android.chrome"], capture_output=True)
    time.sleep(2)
    subprocess.run([ADB, "shell", "am", "start", "-a", "android.intent.action.VIEW",
                   "-d", "https://accounts.google.com/signup"], capture_output=True)
    time.sleep(6)

    # Dismiss Chrome first-run
    for _ in range(5):
        for txt in ["Accept & continue", "No thanks", "No, thanks",
                     "Use without an account", "Got it"]:
            if d(text=txt).exists(timeout=2):
                d(text=txt).click()
                time.sleep(1)
                print(f"  Dismissed: {txt}")
    time.sleep(4)
    d.screenshot("s0.png")

    # === STEP 1: First + Last name ===
    print("\n[1] Name...")
    fname = "Carlos"
    lname = "Rivera"
    inp = d(className="android.widget.EditText")
    if inp.exists(timeout=10):
        inp[0].click(); time.sleep(0.3)
        d.clear_text(); d.send_keys(fname); time.sleep(0.3)
        if inp.count > 1:
            inp[1].click(); time.sleep(0.3)
            d.clear_text(); d.send_keys(lname)
        print(f"  {fname} {lname}")
    d(text="Next").click_exists(timeout=5)
    time.sleep(5)
    d.screenshot("s1.png")

    # === STEP 2: Birthday + Gender ===
    print("\n[2] Birthday...")
    # Day + Year via EditText
    inp = d(className="android.widget.EditText")
    if inp.exists(timeout=5):
        day = str(random.randint(1, 28))
        year = str(random.randint(1990, 2000))
        inp[0].click(); time.sleep(0.2)
        d.clear_text(); d.send_keys(day); time.sleep(0.3)
        if inp.count > 1:
            inp[1].click(); time.sleep(0.2)
            d.clear_text(); d.send_keys(year)
        print(f"  Day={day}, Year={year}")

    # Month: ADB tap at (200, 920) to open native dropdown
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    month = random.choice(months)
    print(f"  Opening Month dropdown...")
    subprocess.run([ADB, "shell", "input", "tap", "200", "920"], capture_output=True)
    time.sleep(2)
    if d(text=month).exists(timeout=3):
        d(text=month).click()
        print(f"  Month={month}")
    else:
        # Scroll and try
        d.swipe(150, 1200, 150, 600)
        time.sleep(0.5)
        if d(text=month).exists(timeout=2):
            d(text=month).click()
            print(f"  Month={month} (scrolled)")
        else:
            d(text="July").click_exists(timeout=2)
            print(f"  Month=July (fallback)")
    time.sleep(1)

    # Gender: ADB tap at (350, 1170)
    print(f"  Opening Gender dropdown...")
    subprocess.run([ADB, "shell", "input", "tap", "350", "1170"], capture_output=True)
    time.sleep(2)
    if d(text="Male").exists(timeout=3):
        d(text="Male").click()
        print(f"  Gender=Male")
    time.sleep(1)
    d.screenshot("s2.png")

    d(text="Next").click_exists(timeout=5)
    time.sleep(5)
    page = " ".join(get_texts(d)).lower()
    print(f"  Page: {page[:60]}")

    if "birthday" in page:
        print("  Still on birthday!")
        d.screenshot("s2_stuck.png")
        return

    # === STEP 3: Username ===
    print("\n[3] Username...")
    uname = f"carlos.rivera.{random.randint(1000, 9999)}"
    radio = d(className="android.widget.RadioButton")
    if radio.exists(timeout=3) and radio.count > 0:
        # Use "create your own" option if available
        if radio.count > 1:
            radio[1].click()  # Usually second option is custom
            time.sleep(1)
            inp = d(className="android.widget.EditText")
            if inp.exists(timeout=3):
                for i in range(inp.count):
                    try:
                        b = inp[i].info.get("bounds", {})
                        if b.get("top", 0) > 400:
                            inp[i].click(); time.sleep(0.2)
                            d.clear_text(); d.send_keys(uname)
                            break
                    except:
                        pass
            print(f"  Custom: {uname}")
        else:
            radio[0].click()
            print("  Selected suggested")
    else:
        inp = d(className="android.widget.EditText")
        if inp.exists(timeout=3):
            for i in range(inp.count):
                try:
                    b = inp[i].info.get("bounds", {})
                    if b.get("top", 0) > 400:
                        inp[i].click(); time.sleep(0.2)
                        d.clear_text(); d.send_keys(uname)
                        print(f"  Typed: {uname}")
                        break
                except:
                    pass

    d(text="Next").click_exists(timeout=5)
    time.sleep(5)
    d.screenshot("s3.png")
    page = " ".join(get_texts(d)).lower()
    print(f"  Page: {page[:60]}")

    # Check if username already taken
    if "taken" in page or "already" in page:
        uname2 = f"carlos.rivera.{random.randint(10000, 99999)}"
        inp = d(className="android.widget.EditText")
        if inp.exists(timeout=3):
            for i in range(inp.count):
                try:
                    b = inp[i].info.get("bounds", {})
                    if b.get("top", 0) > 400:
                        inp[i].click(); time.sleep(0.2)
                        d.clear_text(); d.send_keys(uname2)
                        uname = uname2
                        break
                except:
                    pass
        d(text="Next").click_exists(timeout=3)
        time.sleep(5)
        page = " ".join(get_texts(d)).lower()

    # === STEP 4: Password ===
    print("\n[4] Password...")
    pwd = f"Cr!v3r4_{random.randint(1000, 9999)}!"
    inp = d(className="android.widget.EditText")
    if inp.exists(timeout=5):
        pwd_inputs = []
        for i in range(inp.count):
            try:
                b = inp[i].info.get("bounds", {})
                if b.get("top", 0) > 400:
                    pwd_inputs.append(i)
            except:
                break
        for idx in pwd_inputs:
            inp[idx].click(); time.sleep(0.2)
            d.clear_text(); d.send_keys(pwd); time.sleep(0.3)
        print(f"  Password set ({len(pwd_inputs)} fields)")
    
    d(text="Next").click_exists(timeout=5)
    
    # Wait for phone verification page to load (can take 10-15s)
    print("  Waiting for phone page...")
    page = ""
    for wait in range(8):
        time.sleep(4)
        page = " ".join(get_texts(d)).lower()
        if "phone" in page or "robot" in page or "verify" in page:
            break
        if page.strip():
            print(f"    ({wait}) {page[:50]}")
    
    d.screenshot("s4.png")
    print(f"  Page: {page[:60]}")

    # === STEP 5: Phone verification with GrizzlySMS ===
    print("\n[5] Phone verification...")
    if "phone" not in page and "robot" not in page and "verify" not in page:
        print(f"  Not on phone page! Text: {page[:80]}")
        d.screenshot("s5_wrong.png")
        return

    # Try up to 4 numbers from GrizzlySMS
    for attempt in range(4):
        print(f"\n  Attempt {attempt + 1}...")
        order = sms.order_number("gmail", "auto")
        
        if "error" in order:
            print(f"  Order error: {order['error']}")
            continue
        
        order_id = order["id"]
        phone = order["number"]
        country = order.get("country", "?")
        print(f"  {country}: +{phone}")
        
        # Enter phone
        inp = d(className="android.widget.EditText")
        if inp.exists(timeout=3):
            for i in range(inp.count):
                try:
                    b = inp[i].info.get("bounds", {})
                    if b.get("top", 0) > 400:
                        inp[i].click(); time.sleep(0.3)
                        d.clear_text()
                        d.send_keys(f"+{phone}")
                        break
                except:
                    pass
        
        sms.set_status(order_id, 1)
        time.sleep(0.5)
        d(text="Next").click_exists(timeout=3)
        time.sleep(6)
        
        d.screenshot(f"s5_attempt{attempt}.png")
        page = " ".join(get_texts(d)).lower()
        
        if "cannot be used" in page or "can't be used" in page:
            print(f"  REJECTED by Google")
            sms.cancel_number(order_id)
            continue
        elif "not recognized" in page:
            print(f"  Format error")
            sms.cancel_number(order_id)
            continue
        elif "code" in page or "enter" in page or "sent" in page or "verify" in page:
            print(f"  ACCEPTED! Waiting for SMS (5 min)...")
            code_result = sms.get_sms_code(order_id, 300)
            
            if code_result and not isinstance(code_result, dict):
                code = str(code_result)
                print(f"  CODE: {code}")
                
                inp = d(className="android.widget.EditText")
                if inp.exists(timeout=5):
                    for i in range(inp.count):
                        try:
                            b = inp[i].info.get("bounds", {})
                            if b.get("top", 0) > 400:
                                inp[i].click(); time.sleep(0.2)
                                d.clear_text(); d.send_keys(code)
                                break
                        except:
                            pass
                
                d(text="Next").click_exists(timeout=3)
                if not d(text="Next").exists(timeout=1):
                    d(text="Verify").click_exists(timeout=2)
                time.sleep(5)
                sms.complete_activation(order_id)
                
                # Handle post-verification
                for step in range(10):
                    d.screenshot(f"post_{step}.png")
                    pg = " ".join(get_texts(d)).lower()
                    print(f"  Post {step}: {pg[:50]}")
                    
                    if any(x in pg for x in ["welcome", "inbox", "myaccount", "manage your"]):
                        print(f"\n{'='*60}")
                        print(f"  GMAIL ACCOUNT CREATED!")
                        print(f"  Email: {uname}@gmail.com")
                        print(f"  Password: {pwd}")
                        print(f"  Phone: +{phone} ({country})")
                        print(f"{'='*60}")
                        d.screenshot("SUCCESS.png")
                        return
                    
                    for btn in ["Skip", "Not now", "I agree", "Accept", "Confirm", "Next", "Done"]:
                        if d(text=btn).exists(timeout=1):
                            d(text=btn).click()
                            print(f"    -> {btn}")
                            break
                        if d(textContains=btn).exists(timeout=0.5):
                            d(textContains=btn).click()
                            print(f"    -> {btn} (partial)")
                            break
                    time.sleep(3)
                
                d.screenshot("RESULT.png")
                print(f"\nRegistration flow completed. Check RESULT.png")
                print(f"  Email: {uname}@gmail.com")
                print(f"  Password: {pwd}")
                return
            else:
                error = code_result.get("error", "?") if isinstance(code_result, dict) else "?"
                print(f"  SMS timeout: {error}")
                sms.cancel_number(order_id)
                continue
        else:
            print(f"  Unknown: {page[:60]}")
            sms.cancel_number(order_id)
            continue
    
    print("\nAll attempts exhausted.")
    bal = sms.get_balance()
    print(f"GrizzlySMS remaining: {bal} RUB")


if __name__ == "__main__":
    main()
