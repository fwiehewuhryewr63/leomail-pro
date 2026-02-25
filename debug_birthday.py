"""
Debug script — dump UI hierarchy on birthday page
NO registration, NO proxy, NO GrizzlySMS
Just opens a tainted AVD and inspects elements
"""
import sys, os, time, subprocess
import uiautomator2 as u2

ADB = r"C:\Android\platform-tools\adb.exe"
EMU = r"C:\Android\emulator\emulator.exe"

def adb(*args):
    return subprocess.run([ADB] + list(args), capture_output=True, text=True, timeout=30)

# Use already-tainted AVD (gmail_single_5 or whatever exists)
# Boot it without proxy
print("Booting AVD...")
subprocess.Popen([EMU, "-avd", "gmail_single_5", "-no-audio", "-no-boot-anim"],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for i in range(60):
    time.sleep(3)
    r = adb("shell", "getprop", "sys.boot_completed")
    if r.stdout.strip() == "1":
        print(f"Booted ({(i+1)*3}s)")
        break

# Init u2
subprocess.run([sys.executable, "-m", "uiautomator2", "init"],
               capture_output=True, text=True, timeout=60)

d = u2.connect("emulator-5554")
print(f"Screen: {d.window_size()}")

# Open signup directly (no proxy — will work without proxy for first page)
adb("shell", "pm", "clear", "com.android.chrome")
time.sleep(2)
adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
    "-d", "https://accounts.google.com/signup")
time.sleep(15)

# Dismiss Chrome dialogs
for _ in range(5):
    for txt in ["Accept & continue", "No thanks", "Use without an account", "Got it"]:
        if d(text=txt).exists(timeout=2):
            d(text=txt).click()
            time.sleep(1)
time.sleep(5)

# Type name and go to birthday page
page_text = ""
for el in d(className="android.widget.TextView"):
    try:
        t = el.get_text()
        if t: page_text += t + " "
    except: pass
print(f"\nPage: {page_text[:100]}")

inp = d(className="android.widget.EditText")
if inp.exists(timeout=5):
    inp[0].click()
    time.sleep(0.3)
    try: d.clear_text()
    except: pass
    d.send_keys("Test")
    time.sleep(0.5)
    if inp.count > 1:
        inp[1].click()
        time.sleep(0.3)
        try: d.clear_text()
        except: pass
        d.send_keys("User")
    
    # Scroll and click Next
    d.swipe(540, 1800, 540, 800, duration=0.3)
    time.sleep(1)
    if d(text="Next").exists(timeout=3):
        d(text="Next").click()
        time.sleep(8)

# Now on birthday page — DUMP EVERYTHING
print("\n" + "="*60)
print("BIRTHDAY PAGE — FULL ELEMENT DUMP")
print("="*60)

# Dump XML hierarchy
xml = d.dump_hierarchy()
with open("birthday_hierarchy.xml", "w", encoding="utf-8") as f:
    f.write(xml)
print("Saved: birthday_hierarchy.xml")

# List all elements with class, text, bounds
print("\nAll visible elements:")
for el_class in ["android.widget.Spinner", "android.widget.EditText", 
                  "android.widget.TextView", "android.widget.Button",
                  "android.widget.CheckedTextView", "android.view.View"]:
    elems = d(className=el_class)
    if elems.exists(timeout=1):
        for i in range(elems.count):
            try:
                info = elems[i].info
                text = info.get("text", "")
                desc = info.get("contentDescription", "")
                bounds = info.get("bounds", {})
                focused = info.get("focused", False)
                clickable = info.get("clickable", False)
                if text or desc or clickable:
                    print(f"  [{el_class.split('.')[-1]}] text='{text}' desc='{desc}' "
                          f"bounds={bounds} clickable={clickable} focused={focused}")
            except: pass

d.screenshot("birthday_debug.png")
print("\nSaved: birthday_debug.png")
print("Done. Check birthday_hierarchy.xml for Month field details.")
