"""
Quick test: connect to running emulator via uiautomator2,
open Chrome, navigate to Gmail signup, and check what verification appears.
"""
import uiautomator2 as u2
import time
import subprocess
import sys

ANDROID_HOME = "C:\\Android"
ADB = f"{ANDROID_HOME}\\platform-tools\\adb.exe"

def main():
    print("=" * 50)
    print("Gmail AVD Test - uiautomator2")
    print("=" * 50)
    
    # Connect to emulator
    print("[1] Connecting to emulator...")
    d = u2.connect("emulator-5554")
    print(f"    Device: {d.info.get('productName', '?')}")
    print(f"    Screen: {d.window_size()}")
    print(f"    SDK: {d.info.get('sdkInt', '?')}")
    
    # Open Chrome  
    print("[2] Opening Chrome...")
    # First check if Chrome is installed
    try:
        d.app_start("com.android.chrome")
        time.sleep(3)
        
        # Handle first-run dialogs
        for _ in range(3):
            # "Accept & continue"
            if d(text="Accept & continue").exists(timeout=2):
                d(text="Accept & continue").click()
                time.sleep(1)
            # "No thanks"  
            if d(text="No thanks").exists(timeout=2):
                d(text="No thanks").click()
                time.sleep(1)
            # "No, thanks"
            if d(text="No, thanks").exists(timeout=2):
                d(text="No, thanks").click()
                time.sleep(1)
            # "Use without an account"
            if d(text="Use without an account").exists(timeout=2):
                d(text="Use without an account").click()
                time.sleep(1)
            # "Got it"
            if d(text="Got it").exists(timeout=1):
                d(text="Got it").click()
                time.sleep(1)
        
        print("    Chrome opened!")
    except Exception as e:
        print(f"    Chrome error: {e}")
        # Try with ADB
        print("    Trying via ADB intent...")
        subprocess.run([ADB, "shell", "am", "start", "-a", "android.intent.action.VIEW", 
                       "-d", "https://accounts.google.com/signup", 
                       "-n", "com.android.chrome/com.google.android.apps.chrome.Main"], 
                      capture_output=True, text=True)
        time.sleep(5)
    
    # Navigate to Gmail signup
    print("[3] Navigating to Gmail signup...")
    try:
        # Use ADB to navigate
        subprocess.run([ADB, "shell", "am", "start", "-a", "android.intent.action.VIEW",
                       "-d", "https://accounts.google.com/signup"], 
                      capture_output=True, text=True)
        time.sleep(8)
        print("    Navigated!")
    except Exception as e:
        print(f"    Navigation error: {e}")
    
    # Take screenshot
    print("[4] Taking screenshot...")
    try:
        d.screenshot("gmail_avd_test.png")
        print("    Screenshot saved: gmail_avd_test.png")
    except Exception as e:
        print(f"    Screenshot error: {e}")
    
    # Check what's on screen
    print("[5] Checking page content...")
    try:
        # Look for key elements
        has_name = d(text="First name").exists(timeout=3)
        has_qr = d(textContains="QR").exists(timeout=2) or d(textContains="Scan").exists(timeout=2)
        has_phone = d(textContains="phone number").exists(timeout=2)
        
        print(f"    Has 'First name': {has_name}")
        print(f"    Has 'QR/Scan': {has_qr}")
        print(f"    Has 'phone number': {has_phone}")
        
        # Dump UI hierarchy
        xml = d.dump_hierarchy()
        with open("gmail_avd_hierarchy.xml", "w", encoding="utf-8") as f:
            f.write(xml)
        print("    UI hierarchy saved: gmail_avd_hierarchy.xml")
        
    except Exception as e:
        print(f"    Content check error: {e}")
    
    print("\nDone!")

if __name__ == "__main__":
    main()
