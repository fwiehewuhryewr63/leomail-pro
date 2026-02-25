"""
Gmail Mobile Emulation Test
Tests if Playwright with full mobile emulation + Client Hints
can bypass Google's QR code requirement.

Run: python test_gmail_mobile.py
"""
import asyncio
import random
from playwright.async_api import async_playwright

CHROME_VER = "131.0.2903.86"
DEVICE = "Pixel 7"
ANDROID_VER = "14"

MOBILE_UA = (
    f"Mozilla/5.0 (Linux; Android {ANDROID_VER}; {DEVICE}) "
    f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{CHROME_VER} Mobile Safari/537.36"
)

# Client Hints that real mobile Chrome sends
CLIENT_HINTS = {
    "Sec-CH-UA": f'"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
    "Sec-CH-UA-Arch": '""',
    "Sec-CH-UA-Bitness": '"64"',
    "Sec-CH-UA-Full-Version-List": f'"Chromium";v="{CHROME_VER}", "Google Chrome";v="{CHROME_VER}", "Not_A Brand";v="24.0.0.0"',
    "Sec-CH-UA-Mobile": "?1",
    "Sec-CH-UA-Model": f'"{DEVICE}"',
    "Sec-CH-UA-Platform": '"Android"',
    "Sec-CH-UA-Platform-Version": f'"{ANDROID_VER}.0.0"',
    "Sec-CH-UA-WoW64": "?0",
}

STEALTH_JS = """
// Hide webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
delete navigator.__proto__.webdriver;

// Platform
Object.defineProperty(navigator, 'platform', { get: () => 'Linux armv81' });

// Chrome runtime
if (!window.chrome) {
    window.chrome = { runtime: {}, loadTimes: function(){ return {} }, csi: function(){ return {} } };
}

// Mobile: no plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => { const p = []; p.namedItem = () => null; p.refresh = () => {}; return p; }
});

// Touch
Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
if (typeof TouchEvent === 'undefined') {
    window.TouchEvent = class TouchEvent extends UIEvent { constructor(t,i){super(t,i)} };
}

// Battery (realistic mobile)
navigator.getBattery = () => Promise.resolve({
    charging: false, chargingTime: Infinity, dischargingTime: 8400, level: 0.72,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
});

// WebGL mobile GPU
const _wglGetParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Qualcomm';
    if (p === 37446) return 'Adreno (TM) 730';
    return _wglGetParam.call(this, p);
};
if (typeof WebGL2RenderingContext !== 'undefined') {
    const _wgl2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'Qualcomm';
        if (p === 37446) return 'Adreno (TM) 730';
        return _wgl2.call(this, p);
    };
}

// Hardware (mobile)
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// Connection
Object.defineProperty(navigator, 'connection', {
    configurable: true,
    get: () => ({
        effectiveType: '4g', type: 'wifi', rtt: 50, downlink: 20, saveData: false,
        addEventListener: () => {}, removeEventListener: () => {},
    })
});

// Screen orientation
Object.defineProperty(screen, 'orientation', {
    get: () => ({
        type: 'portrait-primary', angle: 0,
        addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
        lock: () => Promise.resolve(), unlock: () => {},
    })
});

// Vibrate
navigator.vibrate = () => true;

// MediaDevices (mobile cameras)
if (navigator.mediaDevices) {
    navigator.mediaDevices.enumerateDevices = async () => [
        { deviceId: 'mic0', kind: 'audioinput', label: '', groupId: 'mic' },
        { deviceId: 'speaker0', kind: 'audiooutput', label: '', groupId: 'speaker' },
        { deviceId: 'cam_front', kind: 'videoinput', label: '', groupId: 'cam_f' },
        { deviceId: 'cam_back', kind: 'videoinput', label: '', groupId: 'cam_b' },
    ];
}

// Languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// DeviceMotion & Orientation
if (typeof DeviceMotionEvent === 'undefined') {
    window.DeviceMotionEvent = class extends Event { constructor(t,i){super(t,i)} };
}
if (typeof DeviceOrientationEvent === 'undefined') {
    window.DeviceOrientationEvent = class extends Event { constructor(t,i){super(t,i)} };
}
"""


async def main():
    print("=" * 60)
    print("Gmail Mobile Emulation Test")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--disable-extensions",
            ]
        )

        context = await browser.new_context(
            user_agent=MOBILE_UA,
            viewport={"width": 412, "height": 915},
            device_scale_factor=2.625,
            is_mobile=True,
            has_touch=True,
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation"],
            ignore_https_errors=True,
            extra_http_headers=CLIENT_HINTS,
        )

        # Add stealth scripts
        await context.add_init_script(script=STEALTH_JS)

        page = await context.new_page()

        print(f"\nUA: {MOBILE_UA[:80]}...")
        print(f"Viewport: 412x915 (Pixel 7)")
        print(f"is_mobile=True, has_touch=True")
        print(f"Client Hints: Sec-CH-UA-Mobile=?1, Platform=Android")
        print()

        # Navigate to Gmail signup
        print("[1] Navigating to Gmail signup...")
        await page.goto("https://accounts.google.com/signup", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        print(f"    URL: {page.url}")

        # Fill name
        print("[2] Filling name...")
        try:
            await page.fill('#firstName', 'Test')
            await asyncio.sleep(0.5)
            await page.fill('#lastName', 'Mobile')
            await asyncio.sleep(0.5)
            # Click Next
            await page.click('button:has-text("Next")')
            await asyncio.sleep(3)
            print(f"    URL: {page.url}")
        except Exception as e:
            print(f"    Error: {e}")

        # Fill birthday
        print("[3] Filling birthday...")
        try:
            # Month dropdown — on mobile Google uses select#month
            try:
                await page.select_option('select#month', '7')
            except Exception:
                # Fallback: try aria-label
                try:
                    await page.locator('div[id="month"] select, select[aria-label*="onth"]').first.select_option('7')
                except Exception:
                    print("    Could not select month, trying to type...")
                    await page.locator('#month').first.click()
                    await asyncio.sleep(0.3)

            await page.fill('#day', '15')
            await page.fill('#year', '1995')
            await asyncio.sleep(0.5)

            # Gender
            gender_sel = page.locator('select#gender')
            if await gender_sel.count() > 0:
                await gender_sel.select_option("1")  # Male

            await page.click('button:has-text("Next")')
            await asyncio.sleep(3)
            print(f"    URL: {page.url}")
        except Exception as e:
            print(f"    Error: {e}")

        # Username
        print("[4] Username step...")
        try:
            url_now = page.url.lower()
            if "username" in url_now:
                # Try to find username input or suggested emails
                suggested = page.locator('input[type="radio"]')
                if await suggested.count() > 0:
                    await suggested.first.click()
                else:
                    # Custom username
                    custom_input = page.locator('input[aria-label*="sername"], input[name*="Username"]')
                    if await custom_input.count() > 0:
                        await custom_input.first.fill(f"testmobile.{random.randint(100000,999999)}")

                await asyncio.sleep(1)
                await page.click('button:has-text("Next")')
                await asyncio.sleep(3)
            print(f"    URL: {page.url}")
        except Exception as e:
            print(f"    Error: {e}")

        # Password
        print("[5] Password step...")
        try:
            url_now = page.url.lower()
            if "password" in url_now:
                pw_input = page.locator('input[aria-label*="assword"], input[type="password"]')
                if await pw_input.count() >= 2:
                    await pw_input.nth(0).fill("T3st_M0b!le_2026!")
                    await pw_input.nth(1).fill("T3st_M0b!le_2026!")
                elif await pw_input.count() == 1:
                    await pw_input.first.fill("T3st_M0b!le_2026!")

                await asyncio.sleep(1)
                await page.click('button:has-text("Next")')
                await asyncio.sleep(5)
            print(f"    URL: {page.url}")
        except Exception as e:
            print(f"    Error: {e}")

        # Check what we got
        final_url = page.url.lower()
        print()
        print("=" * 60)
        print(f"FINAL URL: {page.url}")
        print()

        if "mophoneverification" in final_url:
            page_text = await page.locator('body').inner_text()
            if "qr code" in page_text.lower() or "scan" in page_text.lower():
                print("RESULT: QR CODE BLOCK -- Mobile emulation NOT enough")
                print("   Google still requires real mobile device")
            elif "phone" in page_text.lower() and "number" in page_text.lower():
                print("RESULT: PHONE NUMBER INPUT -- Mobile emulation WORKS!")
                print("   We can enter SMS number here!")
            else:
                print(f"UNKNOWN: {page_text[:200]}")
        elif "phoneverification" in final_url or "phone" in final_url:
            print("RESULT: Phone verification page!")
        else:
            print(f"Unexpected URL: {final_url}")

        # Take screenshot
        await page.screenshot(path="gmail_mobile_test_result.png")
        print("\nScreenshot saved: gmail_mobile_test_result.png")
        print("\nBrowser will stay open for 30s for inspection...")
        await asyncio.sleep(30)

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
