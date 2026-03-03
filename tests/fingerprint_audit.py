"""
Fingerprint Audit v2 — COMPREHENSIVE Phase 1
Run our Playwright stealth engine through 8 bot-detection sites and capture results.

Sites:
  1. bot.sannysoft.com       — webdriver, chrome.runtime, permissions, plugins
  2. browserleaks.com/canvas — canvas fingerprint hash
  3. browserleaks.com/webgl  — WebGL renderer/vendor
  4. pixelscan.net           — consistency (UA vs platform vs screen vs GPU)
  5. browserscan.net         — fingerprint + bot detection + WebRTC
  6. deviceandbrowserinfo.com/are-you-a-bot — webdriver, chrome obj, automation
  7. abrahamjuliot.github.io/creepjs — trust score, lie detection, DOM rects
  8. amiunique.org/fingerprint — uniqueness score

Usage:
    cd Leomail
    python -m tests.fingerprint_audit

Saves screenshots + JSON report to user_data/debug_screenshots/
"""
import asyncio
import sys
import os
import io
import json
import time

# Force UTF-8 output on Windows (line_buffering=True so prints appear in real-time)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# Add project root so we can import backend modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.modules.browser_manager import BrowserManager

SCREENSHOT_DIR = os.path.join("user_data", "debug_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ─── Detection Sites ─────────────────────────────────────────────────────────

AUDIT_SITES = [
    {
        "name": "sannysoft",
        "url": "https://bot.sannysoft.com",
        "desc": "Webdriver / Chrome Runtime / Plugins / Permissions",
        "wait": 6,
    },
    {
        "name": "canvas",
        "url": "https://browserleaks.com/canvas",
        "desc": "Canvas fingerprint hash",
        "wait": 8,
    },
    {
        "name": "webgl",
        "url": "https://browserleaks.com/webgl",
        "desc": "WebGL vendor + renderer",
        "wait": 8,
    },
    {
        "name": "pixelscan",
        "url": "https://pixelscan.net",
        "desc": "Consistency: UA vs platform vs screen vs GPU",
        "wait": 15,
    },
    {
        "name": "browserscan",
        "url": "https://www.browserscan.net/bot-detection",
        "desc": "Bot detection score + fingerprint",
        "wait": 10,
    },
    {
        "name": "devicebrowserinfo",
        "url": "https://deviceandbrowserinfo.com/are_you_a_bot",
        "desc": "Webdriver / Chrome object / Automation signals",
        "wait": 8,
    },
    {
        "name": "creepjs",
        "url": "https://abrahamjuliot.github.io/creepjs/",
        "desc": "Trust score / Lie detection / DOM rects / Full FP",
        "wait": 15,
    },
    {
        "name": "amiunique",
        "url": "https://amiunique.org/fingerprint",
        "desc": "Uniqueness + consistency score",
        "wait": 10,
    },
]


async def audit_site(page, site: dict) -> str:
    """Navigate to a detection site, wait for JS to complete, take screenshot."""
    name = site["name"]
    url = site["url"]
    wait_secs = site["wait"]

    print(f"\n{'='*70}")
    print(f"  🔍 [{name.upper()}] {url}")
    print(f"     {site['desc']}")
    print(f"{'='*70}")

    try:
        await page.goto(url, wait_until="networkidle", timeout=45000)
    except Exception as e:
        print(f"  ⚠️  Navigation timeout (continuing): {e}")

    # Wait for detection scripts to finish
    print(f"  ⏳ Waiting {wait_secs}s for detection scripts...")
    await asyncio.sleep(wait_secs)

    # Scroll down slowly to trigger lazy-loaded checks
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass

    # Screenshot (top of page)
    ts = time.strftime("%H%M%S")
    path_top = os.path.join(SCREENSHOT_DIR, f"audit_{name}_top_{ts}.png")
    await page.screenshot(path=path_top)
    print(f"  📸 Top screenshot: {path_top}")

    # Full-page screenshot
    path_full = os.path.join(SCREENSHOT_DIR, f"audit_{name}_full_{ts}.png")
    try:
        await page.screenshot(path=path_full, full_page=True)
        print(f"  📸 Full screenshot: {path_full}")
    except Exception:
        path_full = path_top  # fallback

    return path_top


async def extract_sannysoft_results(page) -> dict:
    """Extract test results from bot.sannysoft.com table."""
    results = {}
    try:
        rows = await page.query_selector_all("table tr")
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) >= 2:
                key = (await cells[0].inner_text()).strip()
                val = (await cells[1].inner_text()).strip()
                cls = await cells[1].get_attribute("class") or ""
                if "failed" in cls.lower() or "warn" in cls.lower():
                    status = "❌ FAIL"
                elif "passed" in cls.lower() or "ok" in cls.lower():
                    status = "✅ PASS"
                else:
                    bg = await cells[1].evaluate("el => getComputedStyle(el).backgroundColor")
                    if "255, 0" in bg or "red" in bg.lower():
                        status = "❌ FAIL"
                    elif "0, 128" in bg or "0, 255" in bg or "green" in bg.lower():
                        status = "✅ PASS"
                    else:
                        status = "⚠️  WARN"
                results[key] = {"value": val, "status": status}
    except Exception as e:
        print(f"  ⚠️  Could not parse Sannysoft results: {e}")
    return results


async def check_js_properties(page) -> dict:
    """Check 30+ critical fingerprint properties via JS evaluation."""
    checks = {}

    evaluations = {
        # ─── Core Bot Detection ───
        "navigator.webdriver": "navigator.webdriver",
        "'webdriver' in navigator": "'webdriver' in navigator",
        "chrome.runtime": "typeof window.chrome?.runtime",
        "chrome.runtime.id": "window.chrome?.runtime?.id",
        "chrome.app": "typeof window.chrome?.app",
        "chrome.csi": "typeof window.chrome?.csi",
        "chrome.loadTimes": "typeof window.chrome?.loadTimes",
        "chrome.runtime.connect": "typeof window.chrome?.runtime?.connect",

        # ─── Platform & UA ───
        "navigator.platform": "navigator.platform",
        "navigator.userAgent (first 80)": "navigator.userAgent.substring(0, 80)",
        "navigator.userAgentData": "JSON.stringify(navigator.userAgentData?.toJSON?.() || 'missing')",
        "navigator.userAgentData.platform": "navigator.userAgentData?.platform || 'missing'",

        # ─── Hardware ───
        "navigator.hardwareConcurrency": "navigator.hardwareConcurrency",
        "navigator.deviceMemory": "navigator.deviceMemory",
        "navigator.maxTouchPoints": "navigator.maxTouchPoints",
        "navigator.plugins.length": "navigator.plugins?.length",
        "navigator.languages": "JSON.stringify(navigator.languages)",

        # ─── Screen Consistency ───
        "screen.width": "screen.width",
        "screen.height": "screen.height",
        "screen.availWidth": "screen.availWidth",
        "screen.availHeight": "screen.availHeight",
        "screen.colorDepth": "screen.colorDepth",
        "window.innerWidth": "window.innerWidth",
        "window.innerHeight": "window.innerHeight",
        "window.outerWidth": "window.outerWidth",
        "window.outerHeight": "window.outerHeight",
        "devicePixelRatio": "window.devicePixelRatio",

        # ─── Privacy / Permissions ───
        "Notification.permission": "Notification?.permission",
        "navigator.pdfViewerEnabled": "navigator.pdfViewerEnabled",
        "navigator.connection.effectiveType": "navigator.connection?.effectiveType",

        # ─── WebGL ───
        "WebGL vendor": """(function() {
            try {
                const c = document.createElement('canvas');
                const gl = c.getContext('webgl');
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                return ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : 'no ext';
            } catch(e) { return 'error: ' + e.message; }
        })()""",
        "WebGL renderer": """(function() {
            try {
                const c = document.createElement('canvas');
                const gl = c.getContext('webgl');
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'no ext';
            } catch(e) { return 'error: ' + e.message; }
        })()""",

        # ─── Leak Detection ───
        "Error.stack leak": """(function() {
            try { throw new Error('test'); } catch(e) {
                if (e.stack.includes('playwright') || e.stack.includes('pptr')) return 'LEAKED!';
                if (e.stack.includes('__pw')) return 'LEAKED (__pw)!';
                return 'clean';
            }
        })()""",
        "__pwInitScripts exists": "typeof window.__pwInitScripts !== 'undefined'",
        "__playwright exists": "typeof window.__playwright !== 'undefined'",

        # ─── Timezone ───
        "Date.getTimezoneOffset()": "new Date().getTimezoneOffset()",
        "Intl.DateTimeFormat().resolvedOptions().timeZone": "Intl.DateTimeFormat().resolvedOptions().timeZone",

        # ─── Audio / Speech ───
        "speechSynthesis.getVoices().length": """(function() {
            try { return speechSynthesis.getVoices().length; }
            catch(e) { return 'error'; }
        })()""",

        # ─── History ───
        "history.length": "history.length",

        # ─── Battery ───
        "navigator.getBattery": "typeof navigator.getBattery",
    }

    for label, js in evaluations.items():
        try:
            val = await page.evaluate(js)
            checks[label] = str(val)
        except Exception as e:
            checks[label] = f"ERROR: {e}"

    return checks


def grade_check(key: str, value: str) -> str:
    """Return ✅/❌/⚠️ based on expected values."""
    v = value.strip()

    # Critical fails
    if key == "navigator.webdriver" and v not in ("undefined", "None", "false", "null", "False"):
        return "❌"
    if key == "'webdriver' in navigator" and v in ("True", "true"):
        return "⚠️ "  # Cosmetic: Proxy trap should fix this, but not critical if value=false
    # NOTE: chrome.runtime is 'undefined' on non-extension pages in REAL Chrome — this is CORRECT!
    # Only chrome.app, chrome.csi, chrome.loadTimes are expected to exist on all pages
    if key == "chrome.runtime" and v == "undefined":
        return "✅"  # correct: real Chrome has undefined runtime on normal pages
    if key == "chrome.app" and v == "undefined":
        return "❌"
    if key == "chrome.csi" and v == "undefined":
        return "❌"
    if key == "chrome.loadTimes" and v == "undefined":
        return "❌"
    if key == "chrome.runtime.connect" and v == "undefined":
        return "✅"  # correct: runtime.connect is undefined on normal pages
    if key == "navigator.plugins.length" and v == "0":
        return "❌"
    if key == "navigator.pdfViewerEnabled" and v not in ("True", "true"):
        return "❌"
    if key == "Error.stack leak" and "LEAKED" in v:
        return "❌"
    if key == "__pwInitScripts exists" and v in ("True", "true"):
        return "❌"
    if key == "__playwright exists" and v in ("True", "true"):
        return "❌"
    if key == "navigator.userAgentData" and "missing" in v:
        return "⚠️ "
    if key == "navigator.userAgentData.platform" and v == "missing":
        return "⚠️ "
    if key == "navigator.maxTouchPoints" and v not in ("0", "None"):
        return "⚠️ "  # desktop should be 0
    if key == "screen.width" and (v == "0" or v == "None"):
        return "❌"
    if key == "screen.height" and (v == "0" or v == "None"):
        return "❌"
    if key == "speechSynthesis.getVoices().length" and v in ("0", "error"):
        return "⚠️ "
    if key == "navigator.getBattery" and v == "undefined":
        return "⚠️ "
    if key == "history.length" and v in ("0",):
        return "⚠️ "
    if key == "Notification.permission" and v == "denied":
        return "⚠️ "

    return "✅"


async def main():
    print("🚀 Fingerprint Audit v2 — Comprehensive Phase 1")
    print("=" * 70)
    print(f"   {len(AUDIT_SITES)} detection sites | 30+ JS property checks")
    print(f"   Screenshots → {SCREENSHOT_DIR}/")
    print("=" * 70)

    bm = BrowserManager(headless=False)
    await bm.start()

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "js_checks": {},
        "sannysoft_results": {},
        "screenshots": {},
        "summary": {},
    }

    try:
        # Create desktop context (same as registration engines use)
        context = await bm.create_context(device_type="desktop")
        page = await context.new_page()

        # ─── Step 1: JS property checks ─────────────────────────────────
        print("\n" + "─" * 70)
        print("📋 STEP 1: Direct JS Property Checks (30+ items)")
        print("─" * 70)

        # Use a real page for JS checks — about:blank doesn't load Chrome APIs
        try:
            await page.goto("https://example.com", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            # Fallback if example.com is unreachable (VPN/network issues)
            try:
                await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass  # Continue with whatever page loaded
        await asyncio.sleep(1)
        js_props = await check_js_properties(page)
        report["js_checks"] = js_props

        # Count pass/fail
        pass_count = 0
        fail_count = 0
        warn_count = 0

        print(f"\n  {'Property':<45} {'Value':<40} {'Grade'}")
        print(f"  {'─'*45} {'─'*40} {'─'*5}")
        for k, v in js_props.items():
            grade = grade_check(k, v)
            display_val = v[:40] + "..." if len(v) > 40 else v
            print(f"  {k:<45} {display_val:<40} {grade}")
            if "❌" in grade:
                fail_count += 1
            elif "⚠" in grade:
                warn_count += 1
            else:
                pass_count += 1

        total_checks = len(js_props)
        print(f"\n  JS Checks: {pass_count}✅ / {warn_count}⚠️  / {fail_count}❌ (total {total_checks})")
        report["summary"]["js_pass"] = pass_count
        report["summary"]["js_warn"] = warn_count
        report["summary"]["js_fail"] = fail_count
        report["summary"]["js_total"] = total_checks

        # ─── Step 2: Visit all detection sites ──────────────────────────
        print("\n" + "─" * 70)
        print("📋 STEP 2: Detection Site Audit")
        print("─" * 70)

        for site in AUDIT_SITES:
            path = await audit_site(page, site)
            report["screenshots"][site["name"]] = path

            # Special parsers per site
            if site["name"] == "sannysoft":
                sanny = await extract_sannysoft_results(page)
                report["sannysoft_results"] = sanny
                if sanny:
                    s_pass = sum(1 for d in sanny.values() if "PASS" in d["status"])
                    s_fail = sum(1 for d in sanny.values() if "FAIL" in d["status"])
                    s_warn = sum(1 for d in sanny.values() if "WARN" in d["status"] or "UNKNOWN" in d["status"])
                    print(f"\n  Sannysoft: {s_pass}✅ / {s_warn}⚠️  / {s_fail}❌")
                    report["summary"]["sannysoft_pass"] = s_pass
                    report["summary"]["sannysoft_fail"] = s_fail
                    # Show fails only
                    for test_name, data in sanny.items():
                        if "FAIL" in data["status"]:
                            print(f"    ❌ {test_name}: {data['value']}")

            elif site["name"] == "pixelscan":
                # Try to extract pixelscan status
                try:
                    ps_status = await page.evaluate("""
                        () => {
                            // Look for status indicators
                            const els = document.querySelectorAll('[class*="status"], [class*="result"], [class*="score"]');
                            const texts = [];
                            els.forEach(el => texts.push(el.textContent.trim()));
                            // Also check for red/green indicators
                            const all = document.body.innerText.substring(0, 2000);
                            return { elements: texts.slice(0, 10), bodyPreview: all.substring(0, 500) };
                        }
                    """)
                    if ps_status:
                        preview = ps_status.get("bodyPreview", "")
                        if "consistent" in preview.lower() or "passed" in preview.lower():
                            report["summary"]["pixelscan"] = "CONSISTENT ✅"
                            print(f"\n  Pixelscan: CONSISTENT ✅")
                        elif "inconsistent" in preview.lower() or "failed" in preview.lower() or "bot" in preview.lower():
                            report["summary"]["pixelscan"] = "INCONSISTENT ❌"
                            print(f"\n  Pixelscan: INCONSISTENT ❌")
                        else:
                            report["summary"]["pixelscan"] = "CHECK SCREENSHOT"
                            print(f"\n  Pixelscan: Check screenshot manually")
                except Exception as e:
                    print(f"  ⚠️  Could not parse pixelscan: {e}")

            elif site["name"] == "browserscan":
                # Try to extract bot detection result
                try:
                    bs_status = await page.evaluate("""
                        () => {
                            const body = document.body.innerText.substring(0, 3000);
                            return body;
                        }
                    """)
                    if bs_status:
                        low = bs_status.lower()
                        if "not detected" in low or "human" in low or "normal" in low:
                            report["summary"]["browserscan"] = "NOT DETECTED ✅"
                            print(f"\n  BrowserScan: NOT DETECTED ✅")
                        elif "detected" in low or "bot" in low:
                            report["summary"]["browserscan"] = "BOT DETECTED ❌"
                            print(f"\n  BrowserScan: BOT DETECTED ❌")
                        else:
                            report["summary"]["browserscan"] = "CHECK SCREENSHOT"
                            print(f"\n  BrowserScan: Check screenshot manually")
                except Exception:
                    pass

            elif site["name"] == "creepjs":
                # Try to extract trust score
                try:
                    cjs = await page.evaluate("""
                        () => {
                            const el = document.querySelector('[class*="trust"], [class*="grade"], #fingerprint-data');
                            if (el) return el.textContent.trim().substring(0, 200);
                            return document.body.innerText.substring(0, 500);
                        }
                    """)
                    if cjs:
                        report["summary"]["creepjs_preview"] = cjs[:200]
                        print(f"\n  CreepJS preview: {cjs[:100]}...")
                except Exception:
                    pass

        # ─── Final Summary ────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("📊 AUDIT COMPLETE — FINAL SUMMARY")
        print("=" * 70)

        print(f"\n  JS Property Checks:  {report['summary'].get('js_pass', 0)}✅ / "
              f"{report['summary'].get('js_warn', 0)}⚠️  / "
              f"{report['summary'].get('js_fail', 0)}❌")

        if "sannysoft_pass" in report["summary"]:
            print(f"  Sannysoft:           {report['summary']['sannysoft_pass']}✅ / "
                  f"{report['summary'].get('sannysoft_fail', 0)}❌")

        for key in ["pixelscan", "browserscan"]:
            if key in report["summary"]:
                print(f"  {key.capitalize():<22} {report['summary'][key]}")

        print(f"\n  📸 Screenshots saved to: {SCREENSHOT_DIR}/")

        # Save JSON report
        report_path = os.path.join(SCREENSHOT_DIR, f"audit_report_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  📄 JSON report: {report_path}")

        # Overall verdict
        if report["summary"].get("js_fail", 0) == 0 and report["summary"].get("sannysoft_fail", 0) == 0:
            print(f"\n  🟢 OVERALL: Looking good! Check pixelscan/browserscan screenshots for details.")
        else:
            print(f"\n  🔴 OVERALL: Found {report['summary'].get('js_fail', 0)} JS fails + "
                  f"{report['summary'].get('sannysoft_fail', 0)} Sannysoft fails. FIX REQUIRED!")

        print("=" * 70)

        # Keep browser open for inspection
        print("\n⏳ Browser stays open 60s for manual inspection...")
        print("   Press Ctrl+C to close earlier.")
        try:
            await asyncio.sleep(60)
        except KeyboardInterrupt:
            pass

    finally:
        await bm.stop()


if __name__ == "__main__":
    asyncio.run(main())
