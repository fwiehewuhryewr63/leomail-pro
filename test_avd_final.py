"""
Gmail AVD - Definitive test with CDP for select dropdowns.
1. Sets Chrome command-line flags for remote debugging
2. Clears Chrome, opens signup
3. Fills name via uiautomator2
4. Fills birthday selects via CDP JavaScript
5. Fills username/password via uiautomator2
6. Reports verification step result
"""
import uiautomator2 as u2
import subprocess
import time
import random
import json
import urllib.request
import websocket

ADB = "C:\\Android\\platform-tools\\adb.exe"


def adb(cmd):
    r = subprocess.run([ADB] + cmd, capture_output=True, text=True, timeout=15)
    return r.stdout.strip()


def cdp_eval(ws_url, js_code):
    """Execute JS via Chrome DevTools Protocol WebSocket."""
    ws = websocket.create_connection(ws_url, timeout=10)
    ws.send(json.dumps({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {"expression": js_code, "returnByValue": True}
    }))
    result = json.loads(ws.recv())
    ws.close()
    val = result.get("result", {}).get("result", {}).get("value", "?")
    return val


def get_cdp_ws():
    """Get WebSocket URL for first accounts.google.com tab."""
    adb(["forward", "tcp:9222", "localabstract:chrome_devtools_remote"])
    time.sleep(0.5)
    with urllib.request.urlopen("http://localhost:9222/json") as resp:
        tabs = json.loads(resp.read().decode())
    for tab in tabs:
        url = tab.get("url", "")
        if "accounts.google.com" in url:
            return tab.get("webSocketDebuggerUrl", "")
    if tabs:
        return tabs[0].get("webSocketDebuggerUrl", "")
    return None


def screenshot_texts(d, filename):
    """Take screenshot and return all text on screen."""
    d.screenshot(filename)
    texts = []
    try:
        for el in d(className="android.widget.TextView"):
            t = el.get_text()
            if t and len(t.strip()) > 1:
                texts.append(t.strip())
    except:
        pass
    return texts


def main():
    print("=" * 60)
    print("Gmail AVD - Full Flow with CDP")
    print("=" * 60)

    d = u2.connect("emulator-5554")
    print(f"Device: {d.window_size()}")

    # 0. Setup Chrome with remote debugging flags
    print("\n[0] Setting Chrome flags...")
    adb(["root"])
    time.sleep(2)
    # Write Chrome command-line flags
    flag = "_ --disable-fre --no-default-browser-check --no-first-run --remote-allow-origins=*"
    adb(["shell", f"echo '{flag}' > /data/local/tmp/chrome-command-line"])
    adb(["shell", f"cp /data/local/tmp/chrome-command-line /data/local/chrome-command-line"])
    adb(["shell", "chmod 644 /data/local/chrome-command-line"])
    print("  Flags written")

    # Clear Chrome and restart
    adb(["shell", "pm", "clear", "com.android.chrome"])
    time.sleep(2)
    adb(["shell", "am", "start", "-a", "android.intent.action.VIEW",
         "-d", "https://accounts.google.com/signup"])
    time.sleep(6)

    # Handle first-run dialogs
    for _ in range(5):
        for txt in ["Accept & continue", "No thanks", "No, thanks",
                     "Use without an account", "Got it"]:
            if d(text=txt).exists(timeout=2):
                d(text=txt).click()
                time.sleep(1)
                print(f"  Dismissed: {txt}")
    time.sleep(4)
    
    texts = screenshot_texts(d, "step0.png")
    print(f"  Page: {' | '.join(texts[:3])}")

    # 1. Name
    print("\n[1] Name...")
    inputs = d(className="android.widget.EditText")
    if inputs.exists(timeout=10):
        inputs[0].click(); time.sleep(0.3)
        d.clear_text(); d.send_keys("Carlos"); time.sleep(0.3)
        if inputs.count > 1:
            inputs[1].click(); time.sleep(0.3)
            d.clear_text(); d.send_keys("Mendez")
    else:
        print("  ERROR: No input fields found!")
        return
    
    d(text="Next").click_exists(timeout=5)
    time.sleep(5)
    texts = screenshot_texts(d, "step1.png")
    print(f"  Page: {' | '.join(texts[:3])}")

    # 2. Birthday & Gender via CDP
    print("\n[2] Birthday & Gender...")
    
    # Fill Day/Year via uiautomator2 first
    inputs = d(className="android.widget.EditText")
    if inputs.exists(timeout=5):
        inputs[0].click(); time.sleep(0.2)
        d.clear_text(); d.send_keys("15"); time.sleep(0.3)
        if inputs.count > 1:
            inputs[1].click(); time.sleep(0.2)
            d.clear_text(); d.send_keys("1995")
        print("  Day=15, Year=1995 filled")

    # Now use CDP for Month and Gender selects
    print("  Connecting CDP...")
    try:
        ws_url = get_cdp_ws()
        if ws_url:
            print(f"  WS: {ws_url[:50]}...")
            
            # Set Month = July (7)
            val = cdp_eval(ws_url, """
                (function() {
                    var sel = document.querySelector('select#month');
                    if (!sel) return 'no #month';
                    sel.value = '7';
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'month=' + sel.value;
                })()
            """)
            print(f"  Month: {val}")

            # Set Gender = Male (1)
            val = cdp_eval(ws_url, """
                (function() {
                    var sel = document.querySelector('select#gender');
                    if (!sel) return 'no #gender';
                    sel.value = '1';
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'gender=' + sel.value;
                })()
            """)
            print(f"  Gender: {val}")
        else:
            print("  ERROR: No CDP tab found!")
    except Exception as e:
        print(f"  CDP error: {e}")

    time.sleep(1)
    texts = screenshot_texts(d, "step2_filled.png")
    
    # Click Next
    d(text="Next").click_exists(timeout=3)
    time.sleep(5)
    texts = screenshot_texts(d, "step2_after.png")
    joined = " ".join(texts).lower()
    print(f"  Page: {' | '.join(texts[:3])}")

    if "birthday" in joined:
        print("  WARNING: Still on birthday page!")
        # Try clicking Next again
        d(text="Next").click_exists(timeout=3)
        time.sleep(5)
        texts = screenshot_texts(d, "step2_retry.png")
        joined = " ".join(texts).lower()

    # 3. Username
    print("\n[3] Username...")
    if "choose" in joined or "username" in joined or "gmail" in joined or "address" in joined:
        radio = d(className="android.widget.RadioButton")
        if radio.exists(timeout=3) and radio.count > 0:
            radio[0].click()
            print("  Selected suggested email")
        else:
            inp = d(className="android.widget.EditText")
            if inp.exists(timeout=3):
                inp.click(); time.sleep(0.2)
                d.clear_text()
                uname = f"carlos.mendez.t{random.randint(1000, 9999)}"
                d.send_keys(uname)
                print(f"  Typed: {uname}")
        
        d(text="Next").click_exists(timeout=3)
        time.sleep(5)
    else:
        print(f"  Not on username page, skipping. Text: {joined[:80]}")
    
    texts = screenshot_texts(d, "step3.png")
    joined = " ".join(texts).lower()
    print(f"  Page: {' | '.join(texts[:3])}")

    # 4. Password
    print("\n[4] Password...")
    if "password" in joined or "create a" in joined:
        inp = d(className="android.widget.EditText")
        if inp.exists(timeout=5):
            n = inp.count
            print(f"  {n} input(s)")
            pwd = "C4rl0s_Gm4!l_2026!"
            inp[0].click(); time.sleep(0.2)
            d.clear_text(); d.send_keys(pwd); time.sleep(0.3)
            if n > 1:
                inp[1].click(); time.sleep(0.2)
                d.clear_text(); d.send_keys(pwd)
            
            d(text="Next").click_exists(timeout=3)
            time.sleep(6)
    else:
        print(f"  Not on password page. Text: {joined[:80]}")

    # 5. VERIFICATION - THE CRITICAL CHECK
    print("\n" + "=" * 60)
    print("[5] VERIFICATION PAGE")
    print("=" * 60)
    time.sleep(3)
    texts = screenshot_texts(d, "step5_CRITICAL.png")
    
    print("  All text on screen:")
    for t in texts:
        print(f"    > {t[:80]}")
    
    joined = " ".join(texts).lower()
    print()
    
    if "qr" in joined or "scan" in joined:
        print(">>> RESULT: QR CODE -- Emulator detected! <<<")
    elif any(x in joined for x in ["phone number", "phone", "sms", "verify your", "add phone", "enter a phone"]):
        # Need to distinguish from home screen "Phone" app
        if "gmail" not in joined or "chrome" not in joined:
            print(">>> RESULT: PHONE VERIFICATION -- AVD WORKS! <<<")
        else:
            print(">>> Home screen detected, not verification <<<")
    elif "review" in joined or "agree" in joined or "privacy" in joined:
        print(">>> RESULT: REVIEW/PRIVACY -- Almost done! <<<")
    elif "welcome" in joined or "account" in joined:
        print(">>> RESULT: ACCOUNT CREATED?! <<<")
    else:
        print(">>> UNKNOWN - check step5_CRITICAL.png <<<")


if __name__ == "__main__":
    main()
