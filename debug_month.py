"""Debug: find Month, Day, Year, Gender elements on birthday page and try to set month."""
import uiautomator2 as u2
import xml.etree.ElementTree as ET
import subprocess, time, re

ADB = "C:\\Android\\platform-tools\\adb.exe"

d = u2.connect("emulator-5554")

# First: navigate to birthday page (retry from current state)
page_texts = []
for el in d(className="android.widget.TextView"):
    try:
        t = el.get_text()
        if t and t.strip():
            page_texts.append(t.strip())
    except:
        break
page = " ".join(page_texts).lower() 
print(f"Current page: {page[:80]}")

# Dump hierarchy to find Month dropdown
xml_text = d.dump_hierarchy()
root = ET.fromstring(xml_text)

print("\nElements with bounds in birthday area (y 500-1200):")
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
            if 500 < top < 1200:
                label = text or desc or ""
                if label or clickable == "true":
                    print(f"  [{cls}] [{left},{top}][{right},{bottom}] click={clickable} '{label[:40]}'")

# Now try clicking the Month area — the select element
# From screenshot: Month is leftmost field, centered around x=150, y=570 in screenshot
# Real coords (1080px wide device): scale = 1080/685 = 1.577
# Month: x=100-230 screenshot → 158-363 real, y=540-610 screenshot → 852-963 real
# Center: x=260, y=907
print("\n\nTrying Month tap at various coordinates...")
for tx, ty in [(150, 880), (150, 910), (150, 940), (260, 880), (260, 910)]:
    print(f"\n  Tap ({tx}, {ty})...")
    subprocess.run([ADB, "shell", "input", "tap", str(tx), str(ty)], capture_output=True)
    time.sleep(2)
    
    # Check if dropdown opened
    found = False
    for el in d(className="android.widget.CheckedTextView"):
        try:
            t = el.get_text()
            if t:
                print(f"    CheckedTextView: {t[:30]}")
                found = True
        except:
            break
    
    if not found:
        for month_name in ["January", "February", "March"]:
            if d(text=month_name).exists(timeout=1):
                print(f"    Found: {month_name}")
                found = True
                break
    
    if found:
        # Select a month
        if d(text="October").exists(timeout=2):
            d(text="October").click()
            print("    Selected October!")
        time.sleep(1)
        break
    else:
        # Dismiss any popup by tapping elsewhere
        subprocess.run([ADB, "shell", "input", "tap", "540", "1500"], capture_output=True)
        time.sleep(1)

d.screenshot("month_debug.png")
print("\nDone. Check month_debug.png")
