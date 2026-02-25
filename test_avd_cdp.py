"""
Gmail AVD Flow - proper select dropdown handling via CDP
Uses Chrome DevTools Protocol via ADB to inject JavaScript into Chrome
"""
import uiautomator2 as u2
import time
import subprocess
import random
import json

ADB = "C:\\Android\\platform-tools\\adb.exe"


def adb_shell(cmd):
    """Run an ADB shell command and return output."""
    r = subprocess.run([ADB, "shell"] + cmd.split(), capture_output=True, text=True, timeout=10)
    return r.stdout.strip()


def chrome_js(d, js_code):
    """Execute JavaScript in Chrome via address bar (for select/option manipulation).
    Uses a workaround: tap address bar, type javascript:, press enter.
    Chrome blocks 'javascript:' in address bar on Android, so we use CDP instead.
    """
    # Forward Chrome DevTools port
    # Get Chrome's DevTools socket
    pid = adb_shell("pidof com.android.chrome")
    if not pid:
        pid = adb_shell("pidof com.chrome.canary")
    
    # Use adb forward to connect to Chrome DevTools
    subprocess.run([ADB, "forward", "tcp:9222", f"localabstract:chrome_devtools_remote"], 
                  capture_output=True, text=True)
    
    import urllib.request
    try:
        # Get active tab
        with urllib.request.urlopen("http://localhost:9222/json") as resp:
            tabs = json.loads(resp.read().decode())
        
        if not tabs:
            print("  No Chrome tabs found via CDP!")
            return None
        
        ws_url = tabs[0].get("webSocketDebuggerUrl", "")
        page_url = tabs[0].get("url", "")
        print(f"  CDP tab: {page_url[:60]}...")
        
        # Use websocket to execute JS
        import websocket
        ws = websocket.create_connection(ws_url)
        msg = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": js_code, "returnByValue": True}
        })
        ws.send(msg)
        result = json.loads(ws.recv())
        ws.close()
        return result
    except Exception as e:
        print(f"  CDP error: {e}")
        return None


def main():
    print("=" * 60)
    print("Gmail AVD Flow - CDP Select Handling")
    print("=" * 60)
    
    d = u2.connect("emulator-5554")
    print(f"Connected: {d.window_size()}")

    # Clear Chrome and navigate fresh
    print("\n[0] Fresh start...")
    subprocess.run([ADB, "shell", "pm", "clear", "com.android.chrome"], capture_output=True)
    time.sleep(2)
    subprocess.run([ADB, "shell", "am", "start", "-a", "android.intent.action.VIEW",
                   "-d", "https://accounts.google.com/signup"], capture_output=True)
    time.sleep(5)
    
    # Handle Chrome first-run
    for _ in range(5):
        for txt in ["Accept & continue", "No thanks", "No, thanks", 
                     "Use without an account", "Got it"]:
            if d(text=txt).exists(timeout=2):
                d(text=txt).click()
                time.sleep(1)
                print(f"  Clicked: {txt}")
    time.sleep(5)

    # Enable Chrome DevTools
    # Set Chrome flags for remote debugging
    subprocess.run([ADB, "shell", "am", "set-debug-app", "--persistent", "com.android.chrome"], 
                  capture_output=True)
    
    # Step 1: Name
    print("\n[1] Name...")
    inputs = d(className="android.widget.EditText")
    if inputs.exists(timeout=10):
        inputs[0].click()
        time.sleep(0.3)
        d.clear_text()
        d.send_keys("Carlos")
        time.sleep(0.3)
        if inputs.count > 1:
            inputs[1].click()
            time.sleep(0.3)
            d.clear_text()
            d.send_keys("Mendez")
    d(text="Next").click_exists(timeout=5)
    time.sleep(5)
    d.screenshot("avd_f1.png")
    print("  Done")

    # Step 2: Birthday & Gender via CDP
    print("\n[2] Birthday via CDP...")
    time.sleep(2)
    
    # Try CDP to set select values
    try:
        # Check if websocket-client is available
        import websocket
        has_ws = True
    except ImportError:
        print("  Installing websocket-client...")
        subprocess.run(["pip", "install", "websocket-client"], capture_output=True)
        import websocket
        has_ws = True
    
    # Forward CDP port
    subprocess.run([ADB, "forward", "tcp:9222", "localabstract:chrome_devtools_remote"],
                  capture_output=True)
    time.sleep(1)
    
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:9222/json") as resp:
            tabs = json.loads(resp.read().decode())
        print(f"  CDP tabs: {len(tabs)}")
        
        if tabs:
            ws_url = tabs[0]["webSocketDebuggerUrl"]
            print(f"  WebSocket: {ws_url[:60]}")
            
            ws = websocket.create_connection(ws_url)
            
            # Set Month to July (value=7)
            js_month = """
            (function() {
                var sel = document.querySelector('select#month');
                if (sel) { sel.value = '7'; sel.dispatchEvent(new Event('change', {bubbles:true})); return 'month=7'; }
                return 'no month select found';
            })()
            """
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", 
                               "params": {"expression": js_month}}))
            result = json.loads(ws.recv())
            print(f"  Month: {result.get('result', {}).get('result', {}).get('value', '?')}")
            
            # Set Gender to Male (value=1)
            js_gender = """
            (function() {
                var sel = document.querySelector('select#gender');
                if (sel) { sel.value = '1'; sel.dispatchEvent(new Event('change', {bubbles:true})); return 'gender=1'; }
                return 'no gender select found';
            })()
            """
            ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate",
                               "params": {"expression": js_gender}}))
            result = json.loads(ws.recv())
            print(f"  Gender: {result.get('result', {}).get('result', {}).get('value', '?')}")
            
            ws.close()
            print("  Selects set via CDP!")
    except Exception as e:
        print(f"  CDP failed: {e}")
        print("  Falling back to coordinate tap approach...")
        # Try tapping the select area more precisely
        # Month dropdown arrow is at ~220, 557 on 1080x2400 screen
        d.click(145, 560)
        time.sleep(2)
        d.screenshot("avd_dropdown_attempt.png")
    
    # Fill Day and Year via EditText
    inputs = d(className="android.widget.EditText")
    if inputs.exists(timeout=3):
        inputs[0].click()
        time.sleep(0.2)
        d.clear_text()
        d.send_keys("15")
        time.sleep(0.3)
        if inputs.count > 1:
            inputs[1].click()
            time.sleep(0.2)
            d.clear_text()
            d.send_keys("1995")
    
    time.sleep(1)
    d.screenshot("avd_f2.png")
    
    # Click Next
    d(text="Next").click_exists(timeout=3)
    time.sleep(5)
    d.screenshot("avd_f2_after.png")
    
    # Check if we moved past birthday
    texts = []
    for el in d(className="android.widget.TextView"):
        t = el.get_text()
        if t and t.strip():
            texts.append(t.strip())
    joined = " ".join(texts)
    print(f"  Screen: {joined[:100]}")
    
    if "birthday" in joined.lower():
        print("  Still on birthday page!")
    else:
        print("  Moved past birthday!")

    # Continue with remaining steps...
    # Step 3: Username
    print("\n[3] Username...")
    if "username" in joined.lower() or "gmail" in joined.lower():
        radio = d(className="android.widget.RadioButton")
        if radio.exists(timeout=3):
            radio[0].click()
            time.sleep(0.5)
        else:
            inp = d(className="android.widget.EditText")
            if inp.exists(timeout=3):
                inp.click()
                d.clear_text()
                d.send_keys(f"carlos.mendez.t{random.randint(100, 999)}")
        d(text="Next").click_exists(timeout=3)
        time.sleep(5)
    d.screenshot("avd_f3.png")
    
    # Step 4: Password
    print("\n[4] Password...")
    inp = d(className="android.widget.EditText")
    if inp.exists(timeout=5) and inp.count >= 2:
        inp[0].click()
        time.sleep(0.2)
        d.clear_text()
        d.send_keys("C4rl0s_Gm4!l_2026!")
        time.sleep(0.3)
        inp[1].click()
        time.sleep(0.2)
        d.clear_text()
        d.send_keys("C4rl0s_Gm4!l_2026!")
        d(text="Next").click_exists(timeout=3)
        time.sleep(6)
    d.screenshot("avd_f4.png")
    
    # Step 5: VERIFICATION
    print("\n[5] === VERIFICATION CHECK ===")
    time.sleep(3)
    d.screenshot("avd_f5_critical.png")
    
    texts = []
    for el in d(className="android.widget.TextView"):
        t = el.get_text()
        if t and t.strip() and len(t) > 1:
            texts.append(t.strip())
    
    print("  All text:")
    for t in texts:
        print(f"    > {t[:80]}")
    
    joined = " ".join(texts).lower()
    print()
    if "qr" in joined or "scan" in joined:
        print(">>> RESULT: QR CODE BLOCK <<<")
    elif "phone" in joined or "sms" in joined or "verify" in joined:
        print(">>> RESULT: PHONE/SMS VERIFICATION -- SUCCESS! <<<")
    elif "review" in joined or "agree" in joined or "confirm" in joined:
        print(">>> RESULT: REVIEW/CONFIRM STEP <<<")
    elif "birthday" in joined:
        print(">>> STILL ON BIRTHDAY -- CDP didn't work <<<")
    else:
        print(">>> CHECK SCREENSHOTS <<<")


if __name__ == "__main__":
    main()
