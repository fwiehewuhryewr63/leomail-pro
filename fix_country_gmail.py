"""Find country dropdown bounds and tap it, then select Indonesia, and order+enter new number."""
import uiautomator2 as u2
import xml.etree.ElementTree as ET
import subprocess
import time
import re
import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(__file__))

ADB = "C:\\Android\\platform-tools\\adb.exe"

from backend.modules.birth._helpers import get_sms_provider


def main():
    d = u2.connect("emulator-5554")
    
    # Get UI hierarchy to find country dropdown bounds
    print("[1] Finding country dropdown...")
    xml_text = d.dump_hierarchy()
    root = ET.fromstring(xml_text)
    
    for elem in root.iter():
        bounds = elem.get("bounds", "")
        text = elem.get("text", "")
        desc = elem.get("content-desc", "")
        cls = elem.get("class", "")
        clickable = elem.get("clickable", "")
        
        if bounds:
            m = re.findall(r"\[(\d+),(\d+)\]", bounds)
            if len(m) == 2:
                left, top = int(m[0][0]), int(m[0][1])
                right, bottom = int(m[1][0]), int(m[1][1])
                if 800 < top < 1200:
                    label = text or desc or ""
                    print(f"  [{cls}] [{left},{top}][{right},{bottom}] click={clickable} '{label[:50]}'")
    
    # The country dropdown is an HTML select - needs ADB tap
    # From the screenshot, the flag is at approximately:
    # - In screenshot (683 wide): flag at ~(95, 640), arrow at ~(145, 640)
    # - Real device is 1080px wide, so scale factor = 1080/683 = 1.58
    # - Real coords: flag at ~(150, 1010), arrow at ~(230, 1010) 
    # But we need the y from the actual bounds. Phone EditText is likely around y=890-1020
    # The flag/dropdown is to the left of the phone input
    
    # Try tapping at different y positions
    for tx, ty in [(120, 950), (120, 1010), (120, 900), (120, 1050)]:
        print(f"\n  Trying tap ({tx}, {ty})...")
        subprocess.run([ADB, "shell", "input", "tap", str(tx), str(ty)], capture_output=True)
        time.sleep(2)
        
        # Check if country list appeared
        found_country = False
        for el in d(className="android.widget.CheckedTextView"):
            try:
                t = el.get_text()
                if t:
                    print(f"    [CheckedTextView] {t[:40]}")
                    found_country = True
            except:
                break
        
        if found_country:
            print("  Country list opened!")
            break
        
        # Check if any list appeared by looking for country names
        if d(text="Indonesia").exists(timeout=1) or d(textContains="Indonesia").exists(timeout=1):
            print("  Found Indonesia!")
            found_country = True
            break
        
        # Check for native list items
        for el in d(className="android.widget.TextView"):
            try:
                t = el.get_text()
                if t and ("United" in t or "Afghan" in t or "Albania" in t):
                    print(f"    Country found: {t[:40]}")
                    found_country = True
                    break
            except:
                break
        
        if found_country:
            break
        
        # Tap elsewhere to dismiss
        subprocess.run([ADB, "shell", "input", "tap", "540", "1500"], capture_output=True)
        time.sleep(1)
    
    d.screenshot("country_debug.png")
    
    if not found_country:
        print("\n  Country dropdown not opening via taps.")
        print("  Alternative: clear phone field and enter FULL +62 number")
        
        # Clear phone and enter with country code
        inp = d(className="android.widget.EditText")
        if inp.exists(timeout=3):
            for i in range(inp.count):
                try:
                    bounds = inp[i].info.get("bounds", {})
                    if bounds.get("top", 0) > 400:
                        inp[i].click()
                        time.sleep(0.3)
                        d.clear_text()
                        break
                except:
                    pass
        
        # Order a new number
        sms = get_sms_provider("simsms")
        print(f"\n  Balance: {sms.get_balance()}")
        
        # Try ordering from a country that matches US format (US numbers won't work for Google SMS)
        # Actually, let's try entering with +62 prefix - Google might parse it from the full number
        print("\n[2] Ordering new Indonesian number...")
        result = sms._request("getNumber", service="go", country="6")
        print(f"  Result: {result}")
        
        if result.startswith("ACCESS_NUMBER:"):
            parts = result.split(":")
            order_id = parts[1]
            phone = parts[2]
            print(f"  ID: {order_id}")
            print(f"  Phone: +{phone}")
            
            # Enter FULL number with + in the field
            # This sometimes works on Google - it auto-detects the country
            inp = d(className="android.widget.EditText")
            if inp.exists(timeout=3):
                for i in range(inp.count):
                    try:
                        bounds_info = inp[i].info.get("bounds", {})
                        if bounds_info.get("top", 0) > 400:
                            inp[i].click()
                            time.sleep(0.3)
                            d.clear_text()
                            # Enter full international format
                            d.send_keys(f"+{phone}")
                            print(f"  Entered: +{phone}")
                            break
                    except:
                        pass
            
            sms.set_status(order_id, 1)
            time.sleep(1)
            d.screenshot("phone_full.png")
            
            # Click Next
            d(text="Next").click_exists(timeout=3)
            time.sleep(6)
            d.screenshot("after_phone.png")
            
            # Check result
            texts = []
            for el in d(className="android.widget.TextView"):
                try:
                    t = el.get_text()
                    if t and t.strip() and len(t) > 1:
                        texts.append(t.strip())
                except:
                    break
            page = " ".join(texts).lower()
            print(f"  Page: {page[:100]}")
            
            if "format" in page or "not recognized" in page:
                print("  Number still rejected by format!")
                print("  Need to change country dropdown properly.")
                sms.cancel_number(order_id)
            elif "code" in page or "enter" in page or "verify" in page or "sent" in page:
                print("\n[3] SMS code page! Waiting for code...")
                code_result = sms.get_sms_code(order_id, 120)
                print(f"  Result: {code_result}")
                
                if code_result and not isinstance(code_result, dict):
                    code = str(code_result)
                    print(f"  CODE: {code}")
                    
                    inp = d(className="android.widget.EditText")
                    if inp.exists(timeout=5):
                        for i in range(inp.count):
                            try:
                                b = inp[i].info.get("bounds", {})
                                if b.get("top", 0) > 400:
                                    inp[i].click()
                                    time.sleep(0.2)
                                    d.clear_text()
                                    d.send_keys(code)
                                    break
                            except:
                                pass
                    
                    d(text="Next").click_exists(timeout=3)
                    time.sleep(5)
                    sms.complete_activation(order_id)
                    
                    # Handle remaining steps
                    for s in range(8):
                        d.screenshot(f"finish_{s}.png")
                        if d(text="Skip").exists(timeout=1):
                            d(text="Skip").click()
                        elif d(text="I agree").exists(timeout=1):
                            d(text="I agree").click()
                        elif d(textContains="I agree").exists(timeout=1):
                            d(textContains="I agree").click()
                        elif d(text="Not now").exists(timeout=1):
                            d(text="Not now").click()
                        elif d(text="Next").exists(timeout=1):
                            d(text="Next").click()
                        elif d(text="Confirm").exists(timeout=1):
                            d(text="Confirm").click()
                        time.sleep(3)
                    
                    d.screenshot("FINAL.png")
                    print("\n=== DONE! ===")
                else:
                    print("  No code received")
                    sms.cancel_number(order_id)
            else:
                print("  Check screenshots")
                sms.cancel_number(order_id)
        else:
            print(f"  Order failed: {result}")


if __name__ == "__main__":
    main()
