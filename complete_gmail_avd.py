"""Complete Gmail registration - order number with specific country."""
import sys
import os
import time
import subprocess

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(__file__))

import uiautomator2 as u2
ADB = "C:\\Android\\platform-tools\\adb.exe"

from backend.modules.birth._helpers import get_sms_provider


def main():
    sms = get_sms_provider("simsms")
    bal = sms.get_balance()
    print(f"Balance: {bal}")

    # Order number with specific country (Russia = 0)
    print("\n[1] Ordering Gmail number (Russia)...")
    result = sms._request("getNumber", service="go", country="0")
    print(f"  Raw: {result}")

    if not result.startswith("ACCESS_NUMBER:"):
        # Try Indonesia = 6
        print("  Russia failed, trying Indonesia...")
        result = sms._request("getNumber", service="go", country="6")
        print(f"  Raw: {result}")

    if not result.startswith("ACCESS_NUMBER:"):
        # Try Brazil = 10
        print("  Indonesia failed, trying Brazil...")
        result = sms._request("getNumber", service="go", country="10")
        print(f"  Raw: {result}")

    if not result.startswith("ACCESS_NUMBER:"):
        # Try India = 22
        print("  Brazil failed, trying India...")
        result = sms._request("getNumber", service="go", country="22")
        print(f"  Raw: {result}")

    if not result.startswith("ACCESS_NUMBER:"):
        print(f"  ALL COUNTRIES FAILED: {result}")
        return

    parts = result.split(":")
    order_id = parts[1]
    phone = parts[2]
    print(f"  Order ID: {order_id}")
    print(f"  Phone: +{phone}")

    try:
        # Connect emulator
        d = u2.connect("emulator-5554")

        # Verify we're on phone page
        print("\n[2] Checking AVD page...")
        texts = []
        for el in d(className="android.widget.TextView"):
            try:
                t = el.get_text()
                if t and t.strip() and len(t) > 1:
                    texts.append(t.strip())
            except:
                break
        page = " ".join(texts).lower()
        print(f"  Page: {page[:80]}")

        if "phone" not in page and "robot" not in page:
            print("  NOT on phone page! Cancelling...")
            sms.cancel_number(order_id)
            return

        # Change country code if needed
        # Phone starts with country digits
        # Google shows US flag by default, we may need to change it
        # For Russian numbers: +7...
        # For Indonesian: +62...
        # For Brazilian: +55...
        # For Indian: +91...
        
        # Click country dropdown to change it
        print("\n[3] Setting country code...")
        # The country flag/code is on the left of the phone input
        # Let's tap it
        subprocess.run([ADB, "shell", "input", "tap", "110", "640"], capture_output=True)
        time.sleep(2)
        
        # Determine country from phone prefix
        if phone.startswith("7"):
            country_name = "Russia"
        elif phone.startswith("62"):
            country_name = "Indonesia"
        elif phone.startswith("55"):
            country_name = "Brazil"
        elif phone.startswith("91"):
            country_name = "India"
        else:
            country_name = None
        
        if country_name:
            # Search for country in the dropdown
            # The dropdown might show a search or list
            d.screenshot("country_dropdown.png")
            
            if d(text=country_name).exists(timeout=3):
                d(text=country_name).click()
                print(f"  Selected: {country_name}")
                time.sleep(1)
            elif d(textContains=country_name).exists(timeout=3):
                d(textContains=country_name).click()
                print(f"  Selected: {country_name}")
                time.sleep(1)
            else:
                print(f"  Country {country_name} not found in dropdown")
                # Try scrolling
                d.swipe(300, 1500, 300, 500)
                time.sleep(1)
                if d(text=country_name).exists(timeout=2):
                    d(text=country_name).click()

        # Enter phone number (without country code)
        print(f"\n[4] Entering phone number...")
        local_num = phone
        if phone.startswith("7") and len(phone) == 11:
            local_num = phone[1:]  # 7XXXXXXXXXX -> XXXXXXXXXX
        elif phone.startswith("62"):
            local_num = phone[2:]
        elif phone.startswith("55"):
            local_num = phone[2:]
        elif phone.startswith("91"):
            local_num = phone[2:]
        
        inp = d(className="android.widget.EditText")
        if inp.exists(timeout=5):
            for i in range(inp.count):
                try:
                    bounds = inp[i].info.get("bounds", {})
                    if bounds.get("top", 0) > 400:
                        inp[i].click()
                        time.sleep(0.3)
                        d.clear_text()
                        d.send_keys(local_num)
                        print(f"  Entered: {local_num}")
                        break
                except:
                    pass

        sms.set_status(order_id, 1)
        print("  Status: READY")

        time.sleep(1)
        d.screenshot("phone_ready.png")

        # Click Next
        print("  Clicking Next...")
        d(text="Next").click_exists(timeout=5)
        time.sleep(6)
        d.screenshot("after_phone.png")

        # Check what happened
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

        if "code" in page or "enter" in page or "verify" in page:
            print("\n[5] Waiting for SMS code (2 min)...")
            code_result = sms.get_sms_code(order_id, 120)
            print(f"  Result: {code_result}")

            if code_result and not isinstance(code_result, dict):
                code = str(code_result)
                print(f"  CODE: {code}")

                inp = d(className="android.widget.EditText")
                if inp.exists(timeout=5):
                    for i in range(inp.count):
                        try:
                            bounds = inp[i].info.get("bounds", {})
                            if bounds.get("top", 0) > 400:
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
                print("  Activation done!")

                # Walk through remaining steps
                for step in range(8):
                    d.screenshot(f"final_{step}.png")
                    texts = []
                    for el in d(className="android.widget.TextView"):
                        try:
                            t = el.get_text()
                            if t and t.strip() and len(t) > 1:
                                texts.append(t.strip())
                        except:
                            break
                    page = " ".join(texts).lower()
                    print(f"  Step {step}: {page[:60]}")

                    if "welcome" in page or "inbox" in page or "myaccount" in page:
                        print("\n  === GMAIL ACCOUNT CREATED! ===")
                        break
                    elif d(text="Skip").exists(timeout=1):
                        d(text="Skip").click()
                    elif d(text="I agree").exists(timeout=1):
                        d(text="I agree").click()
                    elif d(textContains="I agree").exists(timeout=1):
                        d(textContains="I agree").click()
                    elif d(text="Confirm").exists(timeout=1):
                        d(text="Confirm").click()
                    elif d(text="Accept").exists(timeout=1):
                        d(text="Accept").click()
                    elif d(text="Next").exists(timeout=1):
                        d(text="Next").click()
                    elif d(text="Not now").exists(timeout=1):
                        d(text="Not now").click()
                    time.sleep(3)

                d.screenshot("GMAIL_FINAL.png")
                print("\nDone! Username: carlos.mendez.t1695@gmail.com")

            else:
                print("  No SMS code received!")
                sms.cancel_number(order_id)
        else:
            print("  Not on code page!")
            d.screenshot("unexpected.png")
            sms.cancel_number(order_id)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sms.cancel_number(order_id)


if __name__ == "__main__":
    main()
