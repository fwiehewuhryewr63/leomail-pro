"""Try different country numbers from SimSMS to find one Google accepts."""
import sys
import os
import time
import subprocess
import uiautomator2 as u2

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(__file__))
ADB = "C:\\Android\\platform-tools\\adb.exe"

from backend.modules.birth._helpers import get_sms_provider


def try_number(d, sms, country_code, country_name):
    """Order number from country, enter it, check if Google accepts."""
    print(f"\n  Trying {country_name} (code={country_code})...")
    result = sms._request("getNumber", service="go", country=country_code)
    
    if not result.startswith("ACCESS_NUMBER:"):
        print(f"    No numbers: {result}")
        return False
    
    parts = result.split(":")
    order_id = parts[1]
    phone = parts[2]
    print(f"    Phone: +{phone} (ID: {order_id})")
    
    # Enter phone number
    inp = d(className="android.widget.EditText")
    if inp.exists(timeout=3):
        for i in range(inp.count):
            try:
                b = inp[i].info.get("bounds", {})
                if b.get("top", 0) > 400:
                    inp[i].click()
                    time.sleep(0.3)
                    d.clear_text()
                    d.send_keys(f"+{phone}")
                    break
            except:
                pass
    
    time.sleep(0.5)
    d(text="Next").click_exists(timeout=3)
    time.sleep(5)
    
    # Check response
    texts = []
    for el in d(className="android.widget.TextView"):
        try:
            t = el.get_text()
            if t and t.strip() and len(t) > 1:
                texts.append(t.strip())
        except:
            break
    page = " ".join(texts).lower()
    
    if "cannot be used" in page or "can't be used" in page:
        print(f"    REJECTED: number blocked by Google")
        sms.cancel_number(order_id)
        return False
    elif "not recognized" in page or "format" in page:
        print(f"    FORMAT ERROR")
        sms.cancel_number(order_id)
        return False
    elif "code" in page or "enter the" in page or "sent" in page or "verify" in page:
        print(f"    ACCEPTED! Waiting for SMS...")
        sms.set_status(order_id, 1)
        code_result = sms.get_sms_code(order_id, 120)
        print(f"    SMS result: {code_result}")
        
        if code_result and not isinstance(code_result, dict):
            code = str(code_result)
            print(f"    CODE: {code}")
            
            # Enter code
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
                d.screenshot(f"final_{s}.png")
                if d(text="Skip").exists(timeout=1):
                    d(text="Skip").click()
                elif d(textContains="I agree").exists(timeout=1):
                    d(textContains="I agree").click()
                elif d(text="Not now").exists(timeout=1):
                    d(text="Not now").click()
                elif d(text="Accept").exists(timeout=1):
                    d(text="Accept").click()
                elif d(text="Confirm").exists(timeout=1):
                    d(text="Confirm").click()
                elif d(text="Next").exists(timeout=1):
                    d(text="Next").click()
                time.sleep(3)
            
            d.screenshot("GMAIL_CREATED.png")
            print(f"\n=== GMAIL CREATED! Phone: +{phone} ===")
            return True
        else:
            print("    SMS timed out")
            sms.cancel_number(order_id)
            return False
    else:
        print(f"    Unknown response: {page[:60]}")
        sms.cancel_number(order_id)
        return False


def main():
    sms = get_sms_provider("simsms")
    bal = sms.get_balance()
    print(f"Balance: {bal} RUB")
    
    d = u2.connect("emulator-5554")
    
    # Countries to try, ordered by quality (most expensive first)
    # These typically have real SIM numbers
    countries = [
        ("22", "India"),         # Large pool, cheap
        ("4", "Philippines"),    # Real SIMs
        ("10", "Brazil"),        # Good quality
        ("52", "Thailand"),      # Real SIMs  
        ("1", "Ukraine"),        # Real SIMs
        ("2", "Kazakhstan"),     # Real SIMs
        ("54", "Mexico"),        # Real SIMs
        ("8", "Kenya"),          # Real SIMs
    ]
    
    for code, name in countries:
        if try_number(d, sms, code, name):
            return
        
        # Check balance
        bal = sms.get_balance()
        print(f"  Balance remaining: {bal}")
        if float(bal) < 2:
            print("  LOW BALANCE - stopping")
            return
    
    print("\nAll countries tried. Need different SMS provider or premium numbers.")


if __name__ == "__main__":
    main()
