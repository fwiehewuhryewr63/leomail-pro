"""Gmail AVD completion with GrizzlySMS provider."""
import sys
import os
import time
import subprocess
import uiautomator2 as u2

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(__file__))
ADB = "C:\\Android\\platform-tools\\adb.exe"

from backend.modules.birth._helpers import get_sms_provider


def main():
    sms = get_sms_provider("grizzly")
    if not sms:
        print("No GrizzlySMS API key!")
        return
    
    bal = sms.get_balance()
    print(f"GrizzlySMS balance: {bal} RUB")
    
    d = u2.connect("emulator-5554")
    
    # Verify we're on phone verification page
    texts = []
    for el in d(className="android.widget.TextView"):
        try:
            t = el.get_text()
            if t and t.strip() and len(t) > 1:
                texts.append(t.strip())
        except:
            break
    page = " ".join(texts).lower()
    print(f"Page: {page[:80]}")
    
    if "phone" not in page and "robot" not in page:
        print("NOT on phone verification page!")
        return
    
    # Order number with auto (tries real countries)
    print("\n[1] Ordering number (auto = real SIM only)...")
    order = sms.order_number("gmail", "auto")
    print(f"Order: {order}")
    
    if "error" in order:
        print(f"ERROR: {order['error']}")
        # Try specific countries manually
        from backend.services.sms_provider import GRIZZLY_COUNTRY_CODES
        print(f"\nAvailable country codes: {list(GRIZZLY_COUNTRY_CODES.keys())[:20]}")
        return
    
    order_id = order["id"]
    phone = order["number"]
    country = order.get("country", "?")
    print(f"  Country: {country}")
    print(f"  Phone: +{phone}")
    print(f"  Order ID: {order_id}")
    
    # Enter phone in emulator
    print("\n[2] Entering phone...")
    inp = d(className="android.widget.EditText")
    if inp.exists(timeout=5):
        for i in range(inp.count):
            try:
                b = inp[i].info.get("bounds", {})
                if b.get("top", 0) > 400:
                    inp[i].click()
                    time.sleep(0.3)
                    d.clear_text()
                    d.send_keys(f"+{phone}")
                    print(f"  Entered: +{phone}")
                    break
            except:
                pass
    
    sms.set_status(order_id, 1)
    time.sleep(1)
    d.screenshot("grizzly_phone.png")
    
    # Click Next
    d(text="Next").click_exists(timeout=5)
    time.sleep(6)
    d.screenshot("grizzly_after.png")
    
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
    
    if "cannot be used" in page or "can't be used" in page:
        print("  REJECTED by Google!")
        sms.cancel_number(order_id)
        
        # Try more numbers
        for attempt in range(3):
            print(f"\n  Retry {attempt+1}...")
            order2 = sms.order_number("gmail", "auto")
            print(f"  Order: {order2}")
            if "error" in order2:
                print(f"  No more numbers: {order2['error']}")
                break
            
            o2_id = order2["id"]
            p2 = order2["number"]
            c2 = order2.get("country", "?")
            print(f"  Country: {c2}, Phone: +{p2}")
            
            inp = d(className="android.widget.EditText")
            if inp.exists(timeout=3):
                for i in range(inp.count):
                    try:
                        b = inp[i].info.get("bounds", {})
                        if b.get("top", 0) > 400:
                            inp[i].click()
                            time.sleep(0.2)
                            d.clear_text()
                            d.send_keys(f"+{p2}")
                            break
                    except:
                        pass
            
            sms.set_status(o2_id, 1)
            d(text="Next").click_exists(timeout=3)
            time.sleep(5)
            
            texts = []
            for el in d(className="android.widget.TextView"):
                try:
                    t = el.get_text()
                    if t and t.strip() and len(t) > 1:
                        texts.append(t.strip())
                except:
                    break
            page = " ".join(texts).lower()
            
            if "cannot be used" in page:
                print(f"  REJECTED again")
                sms.cancel_number(o2_id)
                continue
            elif "code" in page or "enter" in page or "sent" in page:
                print(f"  ACCEPTED! Waiting for SMS...")
                order_id = o2_id
                phone = p2
                break
            else:
                print(f"  Unknown: {page[:60]}")
                sms.cancel_number(o2_id)
                continue
        else:
            print("All retries exhausted")
            return
    
    if "code" in page or "enter" in page or "sent" in page or "verify" in page:
        # Wait for SMS
        print(f"\n[3] Waiting for SMS code (5 min)...")
        code_result = sms.get_sms_code(order_id, 300)
        print(f"  Result: {code_result}")
        
        if code_result and not isinstance(code_result, dict):
            code = str(code_result)
            print(f"  CODE RECEIVED: {code}")
            
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
                            print(f"  Entered code: {code}")
                            break
                    except:
                        pass
            
            # Click Next/Verify
            d(text="Next").click_exists(timeout=3)
            if not d(text="Next").exists(timeout=1):
                d(text="Verify").click_exists(timeout=2)
            time.sleep(5)
            
            sms.complete_activation(order_id)
            print("  Activation completed!")
            
            # Walk through remaining registration steps
            for step in range(10):
                d.screenshot(f"grizzly_final_{step}.png")
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
                
                if "welcome" in page or "inbox" in page or "myaccount" in page or "manage" in page:
                    print(f"\n{'='*60}")
                    print(f"  GMAIL ACCOUNT CREATED!")
                    print(f"  Email: carlos.mendez.t1695@gmail.com")
                    print(f"  Phone: +{phone}")
                    print(f"{'='*60}")
                    break
                
                clicked = False
                for btn_text in ["Skip", "Not now", "I agree", "Accept", "Confirm", "Next", "Done"]:
                    if d(text=btn_text).exists(timeout=1):
                        d(text=btn_text).click()
                        print(f"    Clicked: {btn_text}")
                        clicked = True
                        break
                    if d(textContains=btn_text).exists(timeout=0.5):
                        d(textContains=btn_text).click()
                        print(f"    Clicked (partial): {btn_text}")
                        clicked = True
                        break
                
                if not clicked:
                    # Try scrolling down to find buttons
                    d.swipe(540, 1800, 540, 800)
                    time.sleep(1)
                    for btn_text in ["I agree", "Accept", "Next", "Skip"]:
                        if d(text=btn_text).exists(timeout=1):
                            d(text=btn_text).click()
                            print(f"    Clicked after scroll: {btn_text}")
                            break
                
                time.sleep(3)
            
            d.screenshot("GMAIL_DONE.png")
            print("\nDone! Check GMAIL_DONE.png")
        else:
            error = code_result.get("error", "?") if isinstance(code_result, dict) else "No code"
            print(f"  SMS FAILED: {error}")
            sms.cancel_number(order_id)
    else:
        print("  Not on code page, check screenshots")
        sms.cancel_number(order_id)


if __name__ == "__main__":
    main()
