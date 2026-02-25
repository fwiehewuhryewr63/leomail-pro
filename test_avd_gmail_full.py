"""
Full Gmail signup flow on Android Emulator
Walk through ALL steps and check if SMS verification appears instead of QR.
"""
import uiautomator2 as u2
import subprocess
import time
import sys

ADB = "C:\\Android\\platform-tools\\adb.exe"

def main():
    print("=" * 60)
    print("Gmail AVD Full Signup Flow Test")
    print("=" * 60)
    
    d = u2.connect("emulator-5554")
    print(f"Connected: {d.window_size()}")
    
    # Navigate to Gmail signup via ADB
    subprocess.run([ADB, "shell", "am", "start", "-a", "android.intent.action.VIEW",
                   "-d", "https://accounts.google.com/signup"], 
                  capture_output=True, text=True)
    time.sleep(5)

    # Step 1: Name
    print("\n[STEP 1] Filling name...")
    for attempt in range(3):
        fname = d(text="First name")
        if fname.exists(timeout=5):
            fname.click()
            time.sleep(0.5)
            d.send_keys("Carlos", clear=True)
            time.sleep(0.5)
            
            lname = d(text="Last name (optional)")
            if lname.exists(timeout=2):
                lname.click()
                time.sleep(0.5)
                d.send_keys("Mendez", clear=True)
            
            time.sleep(0.5)
            nxt = d(text="Next")
            if nxt.exists(timeout=3):
                nxt.click()
            time.sleep(4)
            print("    Done!")
            break
        else:
            print(f"    Attempt {attempt+1}: First name not found, waiting...")
            time.sleep(3)

    d.screenshot("avd_step1.png")

    # Step 2: Birthday + Gender
    print("\n[STEP 2] Filling birthday & gender...")
    time.sleep(2)
    
    # Month dropdown
    month = d(text="Month")
    if month.exists(timeout=5):
        month.click()
        time.sleep(1)
        july = d(text="July")
        if july.exists(timeout=3):
            july.click()
            time.sleep(0.5)
    
    # Day
    day = d(text="Day")
    if day.exists(timeout=3):
        day.click()
        time.sleep(0.3)
        d.send_keys("15", clear=True)
    
    # Year
    year = d(text="Year")
    if year.exists(timeout=3):
        year.click()
        time.sleep(0.3)
        d.send_keys("1995", clear=True)
    
    # Gender
    time.sleep(0.5)
    gender = d(text="Gender")
    if gender.exists(timeout=3):
        gender.click()
        time.sleep(1)
        male = d(text="Male")
        if male.exists(timeout=3):
            male.click()
            time.sleep(0.5)
    
    # Next
    nxt = d(text="Next")
    if nxt.exists(timeout=3):
        nxt.click()
    time.sleep(4)
    print("    Done!")
    d.screenshot("avd_step2.png")

    # Step 3: Username
    print("\n[STEP 3] Username...")
    time.sleep(2)
    
    # Check for suggested addresses or custom input
    # Try selecting suggested email first
    import random
    rid = random.randint(100, 999)
    
    # Look for radio buttons or suggested options
    custom = d(textContains="Create your own")
    if custom.exists(timeout=3):
        custom.click()
        time.sleep(1)
        # Find input and type username
        inputs = d(className="android.widget.EditText")
        if inputs.exists(timeout=3):
            inputs.click()
            time.sleep(0.3)
            d.send_keys(f"carlosmendez.test{rid}", clear=True)
    else:
        # Maybe it shows only custom input field
        inputs = d(className="android.widget.EditText")
        if inputs.exists(timeout=3):
            inputs.click()
            time.sleep(0.3)
            d.send_keys(f"carlosmendez.test{rid}", clear=True)
        else:
            # Try first suggested option
            radios = d(className="android.widget.RadioButton")
            if radios.exists(timeout=2):
                radios[0].click()
                time.sleep(0.5)
    
    # Next
    nxt = d(text="Next")
    if nxt.exists(timeout=3):
        nxt.click()
    time.sleep(4)
    print("    Done!")
    d.screenshot("avd_step3.png")

    # Step 4: Password
    print("\n[STEP 4] Password...")
    time.sleep(2)
    
    pwd_inputs = d(className="android.widget.EditText")
    if pwd_inputs.exists(timeout=5):
        count = pwd_inputs.count
        print(f"    Found {count} input fields")
        if count >= 2:
            pwd_inputs[0].click()
            time.sleep(0.3)
            d.send_keys("C4rl0s_Gm4!l_2026!", clear=True)
            time.sleep(0.3)
            pwd_inputs[1].click()
            time.sleep(0.3)
            d.send_keys("C4rl0s_Gm4!l_2026!", clear=True)
        elif count == 1:
            pwd_inputs[0].click()
            d.send_keys("C4rl0s_Gm4!l_2026!", clear=True)
    
    nxt = d(text="Next")
    if nxt.exists(timeout=3):
        nxt.click()
    time.sleep(6)
    print("    Done!")
    d.screenshot("avd_step4.png")

    # Step 5: CRITICAL - What verification appears?
    print("\n[STEP 5] VERIFICATION CHECK...")
    time.sleep(3)
    d.screenshot("avd_step5_verification.png")
    
    # Check for QR code indicators
    has_qr = d(textContains="QR").exists(timeout=3) or d(textContains="Scan").exists(timeout=3)
    has_phone = (d(textContains="phone number").exists(timeout=3) or 
                 d(textContains="Phone number").exists(timeout=3) or
                 d(textContains="Verify your phone").exists(timeout=3) or
                 d(textContains="Add phone").exists(timeout=3))
    has_verify = d(textContains="Verify").exists(timeout=3)
    has_skip = d(text="Skip").exists(timeout=2)
    
    print(f"    QR/Scan text: {has_qr}")
    print(f"    Phone number text: {has_phone}")
    print(f"    Verify text: {has_verify}")
    print(f"    Skip option: {has_skip}")
    
    # Dump relevant text elements 
    print("\n    All text on screen:")
    try:
        all_text_elems = d(className="android.widget.TextView")
        for i in range(min(all_text_elems.count, 15)):
            txt = all_text_elems[i].get_text()
            if txt and len(txt.strip()) > 0:
                print(f"      [{i}] {txt[:80]}")
    except Exception as e:
        print(f"      Error reading text: {e}")
    
    # Save UI hierarchy for analysis
    xml = d.dump_hierarchy()
    with open("avd_step5_hierarchy.xml", "w", encoding="utf-8") as f:
        f.write(xml)
    print("\n    Hierarchy saved to avd_step5_hierarchy.xml")
    
    print("\n" + "=" * 60)
    if has_phone and not has_qr:
        print("RESULT: SMS PHONE VERIFICATION --- AVD WORKS!")
    elif has_qr:
        print("RESULT: QR CODE --- even AVD doesn't bypass")
    else:
        print("RESULT: Unknown page - check screenshots")
    print("=" * 60)


if __name__ == "__main__":
    main()
