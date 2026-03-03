"""
Yahoo Traffic Spy — Phase 2: Network Interception
Intercepts ALL network traffic during Yahoo signup flow.
Captures: requests, responses, cookies, JS scripts, challenge triggers.

Usage:
    cd Leomail
    python -m tests.yahoo_traffic_spy

Output:
    user_data/debug_screenshots/yahoo_traffic_*.json
    user_data/debug_screenshots/yahoo_traffic_*.md
"""
import asyncio
import sys
import os
import io
import json
import time
import re
from collections import defaultdict
from urllib.parse import urlparse

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.modules.browser_manager import BrowserManager

SCREENSHOT_DIR = os.path.join("user_data", "debug_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ─── Globals for traffic collection ──────────────────────────────────────────

traffic_log = []          # All requests/responses
cookie_snapshots = []     # Cookies at each stage
js_scripts = []           # All loaded JS scripts
stage_markers = []        # Stage transitions
errors_log = []           # Errors encountered


def _domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc
    except Exception:
        return url[:60]


def _is_yahoo(url: str) -> bool:
    """Check if URL belongs to Yahoo ecosystem."""
    d = _domain(url).lower()
    return any(pat in d for pat in [
        "yahoo.com", "yimg.com", "yahoo.net", "aol.com",
        "oath.com", "verizonmedia", "guce.", "consent.",
        "arkose", "funcaptcha", "arkoselabs",
    ])


def _classify_request(url: str, content_type: str = "") -> str:
    """Classify a request by purpose."""
    u = url.lower()
    ct = content_type.lower()

    if "funcaptcha" in u or "arkose" in u or "arkoselabs" in u:
        return "🔒 CAPTCHA (FunCaptcha/Arkose)"
    if "recaptcha" in u or "google.com/recaptcha" in u:
        return "🔒 CAPTCHA (reCAPTCHA)"
    if "challenge" in u:
        return "⚠️ CHALLENGE"
    if "guce.yahoo" in u or "consent.yahoo" in u:
        return "🍪 CONSENT/GUCE"
    if "fingerprint" in u or "fp" in u:
        return "🔍 FINGERPRINT"
    if "/account/create" in u:
        return "📝 SIGNUP"
    if "login.yahoo.com" in u:
        return "🔑 LOGIN/AUTH"
    if ".js" in u or "javascript" in ct:
        return "📜 JS SCRIPT"
    if ".css" in u or "text/css" in ct:
        return "🎨 CSS"
    if "image" in ct or ".png" in u or ".jpg" in u or ".gif" in u or ".svg" in u or ".webp" in u:
        return "🖼️ IMAGE"
    if ".woff" in u or ".ttf" in u or "font" in ct:
        return "🔤 FONT"
    if "beacon" in u or "analytics" in u or "pixel" in u or "tracking" in u:
        return "📊 TRACKING"
    if "api" in u or "json" in ct:
        return "🔌 API"
    if "xml" in ct:
        return "📄 XML"
    return "📦 OTHER"


async def _on_request(request):
    """Handle outgoing request."""
    url = request.url
    if not _is_yahoo(url) and "google" not in url:
        return  # Skip non-Yahoo traffic

    entry = {
        "timestamp": time.strftime("%H:%M:%S"),
        "direction": "→ REQ",
        "method": request.method,
        "url": url,
        "domain": _domain(url),
        "headers": dict(request.headers) if request.headers else {},
        "post_data": None,
        "content_type": request.headers.get("content-type", "") if request.headers else "",
    }

    # Capture POST body (critical for form submissions)
    if request.method == "POST":
        try:
            entry["post_data"] = request.post_data[:2000] if request.post_data else None
        except Exception:
            pass

    entry["category"] = _classify_request(url, entry["content_type"])
    traffic_log.append(entry)

    # Log JS scripts
    if ".js" in url or "javascript" in entry["content_type"]:
        js_scripts.append({
            "url": url,
            "domain": _domain(url),
            "timestamp": entry["timestamp"],
        })

    # Print important requests live
    cat = entry["category"]
    if any(k in cat for k in ["CAPTCHA", "CHALLENGE", "SIGNUP", "API", "CONSENT", "FINGERPRINT", "LOGIN"]):
        print(f"  {cat} {request.method} {url[:120]}")


async def _on_response(response):
    """Handle incoming response."""
    url = response.url
    if not _is_yahoo(url) and "google" not in url:
        return

    entry = {
        "timestamp": time.strftime("%H:%M:%S"),
        "direction": "← RES",
        "status": response.status,
        "url": url,
        "domain": _domain(url),
        "content_type": "",
        "response_preview": None,
    }

    try:
        headers = await response.all_headers()
        entry["content_type"] = headers.get("content-type", "")
    except Exception:
        pass

    # Capture response body for JSON/text API responses
    ct = entry["content_type"].lower()
    if ("json" in ct or "text/html" in ct or "text/plain" in ct) and response.status < 400:
        try:
            body = await response.text()
            if body and len(body) < 5000:
                entry["response_preview"] = body[:2000]
        except Exception:
            pass

    entry["category"] = _classify_request(url, ct)
    traffic_log.append(entry)

    # Log errors
    if response.status >= 400:
        errors_log.append({
            "timestamp": entry["timestamp"],
            "status": response.status,
            "url": url,
            "category": entry["category"],
        })
        print(f"  ❌ HTTP {response.status} {url[:100]}")


async def snapshot_cookies(context, stage: str):
    """Capture all cookies at a given stage."""
    try:
        cookies = await context.cookies()
        yahoo_cookies = [c for c in cookies if "yahoo" in c.get("domain", "").lower()]
        snapshot = {
            "stage": stage,
            "timestamp": time.strftime("%H:%M:%S"),
            "total_cookies": len(cookies),
            "yahoo_cookies": len(yahoo_cookies),
            "cookies": [
                {
                    "name": c["name"],
                    "domain": c["domain"],
                    "value": c["value"][:80] + "..." if len(c.get("value", "")) > 80 else c.get("value", ""),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "path": c.get("path", "/"),
                }
                for c in yahoo_cookies
            ]
        }
        cookie_snapshots.append(snapshot)

        # Print summary
        names = [c["name"] for c in yahoo_cookies]
        print(f"\n  🍪 [{stage}] Yahoo cookies ({len(yahoo_cookies)}): {', '.join(names[:15])}")

        return snapshot
    except Exception as e:
        print(f"  ⚠️ Cookie snapshot failed at {stage}: {e}")
        return None


def mark_stage(name: str):
    """Mark a stage transition in the traffic log."""
    marker = {
        "timestamp": time.strftime("%H:%M:%S"),
        "stage": name,
    }
    stage_markers.append(marker)
    print(f"\n{'='*60}")
    print(f"  📍 STAGE: {name}")
    print(f"{'='*60}")


async def main():
    print("🕵️ Yahoo Traffic Spy — Phase 2: Network Interception")
    print("=" * 60)
    print("   Capturing ALL Yahoo network traffic during signup flow")
    print("=" * 60)

    bm = BrowserManager(headless=False)
    await bm.start()

    try:
        context = await bm.create_context(device_type="desktop")
        page = await context.new_page()

        # ── Attach network listeners ──
        page.on("request", lambda req: asyncio.ensure_future(_on_request(req)))
        page.on("response", lambda res: asyncio.ensure_future(_on_response(res)))

        # ════════════════════════════════════════════════════════════
        # STAGE 1: Pre-warmup (clean state)
        # ════════════════════════════════════════════════════════════
        mark_stage("1. INITIAL STATE (no cookies)")
        await snapshot_cookies(context, "initial")

        # ════════════════════════════════════════════════════════════
        # STAGE 2: Visit yahoo.com (warmup — build session cookies)
        # ════════════════════════════════════════════════════════════
        mark_stage("2. WARMUP — visiting yahoo.com")
        try:
            await page.goto("https://www.yahoo.com", wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"  ⚠️ yahoo.com navigation: {e}")

        await asyncio.sleep(3)

        # Accept consent banner if present
        try:
            consent_btn = page.locator("button:has-text('Accept'), button:has-text('Agree'), button[name='agree']").first
            if await consent_btn.is_visible(timeout=3000):
                await consent_btn.click()
                print("  ✅ Accepted consent banner")
                await asyncio.sleep(2)
        except Exception:
            pass

        # Scroll around (simulate real user)
        await page.evaluate("window.scrollBy(0, 300)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollBy(0, 200)")
        await asyncio.sleep(1)

        await snapshot_cookies(context, "after_warmup")

        # ════════════════════════════════════════════════════════════
        # STAGE 3: Navigate to signup page
        # ════════════════════════════════════════════════════════════
        mark_stage("3. SIGNUP PAGE — login.yahoo.com/account/create")
        try:
            await page.goto("https://login.yahoo.com/account/create",
                          wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ⚠️ Signup navigation: {e}")

        await asyncio.sleep(4)

        # Check for errors
        current_url = page.url
        print(f"  📍 Current URL: {current_url}")

        if "chrome-error" in current_url or "about:blank" == current_url:
            print("  ❌ PROXY DEAD — cannot reach Yahoo")
            return

        await snapshot_cookies(context, "on_signup_page")

        # Take screenshot of signup page
        ts = time.strftime("%H%M%S")
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"spy_signup_page_{ts}.png"))

        # ════════════════════════════════════════════════════════════
        # STAGE 4: Fill form (don't submit yet — analyze what loads)
        # ════════════════════════════════════════════════════════════
        mark_stage("4. FILLING FORM (pre-submit)")

        # Fill form fields with test data
        form_data = {
            "firstName": "TestJohn",
            "lastName": "TestDoe",
            "userId": f"testspy{int(time.time()) % 100000}",
            "password": "TestP@ss2026!Xq",
        }

        field_selectors = {
            "firstName": ['#reg-firstName', 'input[name="firstName"]'],
            "lastName": ['#reg-lastName', 'input[name="lastName"]'],
            "userId": ['#reg-userId', 'input[name="userId"]', 'input[name="yid"]'],
            "password": ['#reg-password', 'input[name="password"]', 'input[type="password"]'],
        }

        for field_name, selectors in field_selectors.items():
            for sel in selectors:
                try:
                    if await page.locator(sel).count() > 0:
                        await page.locator(sel).first.fill(form_data[field_name])
                        print(f"  ✅ Filled {field_name}")
                        await asyncio.sleep(0.5)
                        break
                except Exception:
                    continue

        # Fill birthday
        bday_fields = {
            "mm": "03",
            "dd": "15",
            "yyyy": "1995",
        }
        for name, val in bday_fields.items():
            try:
                sel = f'input[name="{name}"]'
                if await page.locator(sel).count() > 0:
                    await page.locator(sel).first.fill(val)
                    await asyncio.sleep(0.3)
            except Exception:
                pass

        # Check terms checkbox
        try:
            cb = page.locator('input[type="checkbox"]').first
            if await cb.count() > 0 and not await cb.is_checked():
                await cb.click()
                print("  ✅ Checked terms")
        except Exception:
            pass

        await asyncio.sleep(2)
        await snapshot_cookies(context, "form_filled")

        # Screenshot before submit
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"spy_form_filled_{ts}.png"))

        # ════════════════════════════════════════════════════════════
        # STAGE 5: Submit form (this is where detection JS fires)
        # ════════════════════════════════════════════════════════════
        mark_stage("5. SUBMITTING FORM")
        print("  ⚡ Submitting — watch for challenge/fingerprint/captcha requests...")

        submit_btn = None
        for sel in ['button[name="signup"]', 'button:has-text("Next")', 'button[type="submit"]',
                     'button:has-text("Continue")', '#reg-submit-button']:
            try:
                if await page.locator(sel).count() > 0:
                    submit_btn = sel
                    break
            except Exception:
                continue

        if submit_btn:
            await page.locator(submit_btn).first.click()
            print(f"  ✅ Clicked submit: {submit_btn}")
        else:
            await page.keyboard.press("Enter")
            print("  ✅ Pressed Enter (no button found)")

        # Wait and observe traffic
        await asyncio.sleep(8)

        post_submit_url = page.url
        print(f"  📍 After submit: {post_submit_url}")

        await snapshot_cookies(context, "after_submit")

        # Screenshot
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"spy_after_submit_{ts}.png"))

        # ════════════════════════════════════════════════════════════
        # STAGE 6: Phone page (if we reach it)
        # ════════════════════════════════════════════════════════════
        mark_stage("6. POST-SUBMIT (checking for phone/captcha/error)")

        # Check what page we're on
        body_text = ""
        try:
            body_text = await page.locator("body").inner_text()
            body_text = body_text[:1000]
        except Exception:
            pass

        # Detect page type
        url_lower = post_submit_url.lower()
        if "challenge" in url_lower or "captcha" in url_lower:
            print("  🔒 CAPTCHA/CHALLENGE page detected!")
        elif "phone" in body_text.lower() or "add your phone" in body_text.lower():
            print("  📱 PHONE page detected!")
        elif "error" in url_lower:
            print("  ❌ ERROR page detected!")
        elif "not available" in body_text.lower() or "already taken" in body_text.lower():
            print("  ⚠️ Email taken — Yahoo on same page")
        else:
            print(f"  📄 Page text preview: {body_text[:200]}")

        # Try to detect phone input
        phone_input = None
        for sel in ['input#reg-phone', 'input[name="phone"]', 'input[placeholder*="hone"]',
                     'input[autocomplete="tel"]']:
            try:
                if await page.locator(sel).count() > 0:
                    phone_input = sel
                    break
            except Exception:
                continue

        if phone_input:
            print("  📱 Phone input found! (We won't fill it — no SMS provider in spy mode)")

            # Capture what Yahoo shows for country code
            try:
                country_code = await page.evaluate("""() => {
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {
                        const val = inp.value.trim();
                        if (val.startsWith('+') && val.length <= 5 && val.length >= 2) return val;
                    }
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {
                        const opt = sel.options[sel.selectedIndex];
                        if (opt) {
                            const m = opt.text.match(/\+(\d{1,4})/);
                            if (m) return '+' + m[1];
                        }
                    }
                    return null;
                }""")
                if country_code:
                    print(f"  📍 Yahoo country code: {country_code}")
            except Exception:
                pass

            # Check if WhatsApp or SMS buttons
            try:
                has_sms = await page.locator('button:has-text("text"), button:has-text("SMS"), a:has-text("text")').count()
                has_whatsapp = await page.locator('button:has-text("WhatsApp"), a:has-text("WhatsApp")').count()
                print(f"  📱 SMS buttons: {has_sms} | WhatsApp buttons: {has_whatsapp}")
            except Exception:
                pass

        await snapshot_cookies(context, "phone_page")

        # Final screenshot
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"spy_phone_page_{ts}.png"),
                            full_page=True)

        # ════════════════════════════════════════════════════════════
        # ANALYSIS: Build report
        # ════════════════════════════════════════════════════════════
        mark_stage("7. ANALYSIS — building report")

        # ── Summary stats ──
        yahoo_requests = [t for t in traffic_log if t["direction"] == "→ REQ"]
        yahoo_responses = [t for t in traffic_log if t["direction"] == "← RES"]

        categories = defaultdict(int)
        for t in traffic_log:
            categories[t.get("category", "OTHER")] += 1

        domains = defaultdict(int)
        for t in traffic_log:
            domains[t.get("domain", "?")] += 1

        post_requests = [t for t in yahoo_requests if t["method"] == "POST"]

        print(f"\n{'='*60}")
        print("📊 TRAFFIC ANALYSIS SUMMARY")
        print(f"{'='*60}")
        print(f"\n  Total requests captured: {len(yahoo_requests)}")
        print(f"  Total responses captured: {len(yahoo_responses)}")
        print(f"  POST requests: {len(post_requests)}")
        print(f"  JS scripts loaded: {len(js_scripts)}")
        print(f"  HTTP errors: {len(errors_log)}")
        print(f"  Cookie snapshots: {len(cookie_snapshots)}")

        print(f"\n  By category:")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")

        print(f"\n  By domain:")
        for domain, count in sorted(domains.items(), key=lambda x: -x[1])[:20]:
            print(f"    {domain}: {count}")

        print(f"\n  POST requests (form submissions / API calls):")
        for p in post_requests:
            post_preview = (p.get("post_data", "") or "")[:150]
            print(f"    {p['method']} {p['url'][:100]}")
            if post_preview:
                print(f"      body: {post_preview}")

        print(f"\n  JS Scripts (Yahoo):")
        yahoo_js = [s for s in js_scripts if _is_yahoo(s["url"])]
        for s in yahoo_js[:30]:
            print(f"    {s['url'][:120]}")

        print(f"\n  Challenge/Captcha related:")
        challenge_traffic = [t for t in traffic_log if any(k in t.get("category", "")
                            for k in ["CAPTCHA", "CHALLENGE", "FINGERPRINT"])]
        if challenge_traffic:
            for t in challenge_traffic:
                print(f"    {t['direction']} {t.get('method', '')} {t['url'][:100]}")
        else:
            print("    (none detected during this session)")

        # ── Save JSON report ──
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total_requests": len(yahoo_requests),
                "total_responses": len(yahoo_responses),
                "post_requests": len(post_requests),
                "js_scripts": len(js_scripts),
                "http_errors": len(errors_log),
                "categories": dict(categories),
                "domains": dict(domains),
            },
            "stages": stage_markers,
            "cookie_snapshots": cookie_snapshots,
            "post_requests": [
                {
                    "timestamp": p["timestamp"],
                    "method": p["method"],
                    "url": p["url"],
                    "category": p["category"],
                    "post_data": (p.get("post_data") or "")[:500],
                    "content_type": p.get("content_type", ""),
                }
                for p in post_requests
            ],
            "js_scripts": [
                {"url": s["url"], "domain": s["domain"], "timestamp": s["timestamp"]}
                for s in js_scripts
            ],
            "challenge_traffic": [
                {
                    "timestamp": t["timestamp"],
                    "direction": t["direction"],
                    "url": t["url"],
                    "category": t["category"],
                    "status": t.get("status"),
                }
                for t in challenge_traffic
            ],
            "errors": errors_log,
            "traffic_log": [
                {
                    "timestamp": t["timestamp"],
                    "direction": t["direction"],
                    "method": t.get("method", ""),
                    "status": t.get("status"),
                    "url": t["url"][:200],
                    "category": t["category"],
                }
                for t in traffic_log
            ],
        }

        report_path = os.path.join(SCREENSHOT_DIR, f"yahoo_traffic_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n  📄 JSON report saved: {report_path}")

        # ── Save readable markdown ──
        md_path = os.path.join(SCREENSHOT_DIR, f"yahoo_traffic_{time.strftime('%Y%m%d_%H%M%S')}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Yahoo Traffic Spy — Report\n\n")
            f.write(f"**Time:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## Summary\n\n")
            f.write(f"| Metric | Value |\n|---|---|\n")
            f.write(f"| Total requests | {len(yahoo_requests)} |\n")
            f.write(f"| POST requests | {len(post_requests)} |\n")
            f.write(f"| JS scripts | {len(js_scripts)} |\n")
            f.write(f"| HTTP errors | {len(errors_log)} |\n")
            f.write(f"| Cookie snapshots | {len(cookie_snapshots)} |\n\n")

            f.write("## Cookie Flow\n\n")
            for snap in cookie_snapshots:
                f.write(f"### {snap['stage']} ({snap['timestamp']})\n\n")
                f.write(f"Total: {snap['total_cookies']} cookies, Yahoo: {snap['yahoo_cookies']}\n\n")
                if snap["cookies"]:
                    f.write("| Name | Domain | Value | HttpOnly | Secure |\n")
                    f.write("|---|---|---|---|---|\n")
                    for c in snap["cookies"]:
                        val = c['value'][:40] + '...' if len(c.get('value', '')) > 40 else c.get('value', '')
                        f.write(f"| `{c['name']}` | {c['domain']} | `{val}` | {c['httpOnly']} | {c['secure']} |\n")
                    f.write("\n")

            f.write("## POST Requests (Form/API)\n\n")
            for p in post_requests:
                f.write(f"- **{p['method']}** `{p['url'][:120]}`\n")
                if p.get("post_data"):
                    f.write(f"  - Body: `{(p['post_data'] or '')[:200]}`\n")
                f.write("\n")

            f.write("## Yahoo JS Scripts\n\n")
            for s in yahoo_js[:30]:
                f.write(f"- `{s['url'][:150]}`\n")
            f.write("\n")

            f.write("## Challenge/Captcha Traffic\n\n")
            if challenge_traffic:
                for t in challenge_traffic:
                    f.write(f"- {t['direction']} {t.get('method', '')} `{t['url'][:120]}` ({t['category']})\n")
            else:
                f.write("(none detected during this session)\n")
            f.write("\n")

            f.write("## Domains Contacted\n\n")
            f.write("| Domain | Requests |\n|---|---|\n")
            for domain, count in sorted(domains.items(), key=lambda x: -x[1])[:25]:
                f.write(f"| `{domain}` | {count} |\n")

        print(f"  📝 Markdown report saved: {md_path}")

        print(f"\n{'='*60}")
        print("  ✅ Yahoo Traffic Spy complete!")
        print(f"{'='*60}")

        # Keep browser open for inspection
        print("\n⏳ Browser stays open 30s for manual inspection...")
        print("   Press Ctrl+C to close earlier.")
        try:
            await asyncio.sleep(30)
        except KeyboardInterrupt:
            pass

    finally:
        await bm.stop()


if __name__ == "__main__":
    asyncio.run(main())
