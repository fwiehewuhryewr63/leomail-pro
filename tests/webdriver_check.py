"""Verify delete Navigator.prototype.webdriver works with system Chrome."""
import asyncio, sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

async def test():
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        channel="chrome",
        headless=False,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    )
    ctx = await browser.new_context()
    await ctx.add_init_script(script="""
        // Delete webdriver from prototype (configurable:true in real Chrome)
        const proto = Object.getPrototypeOf(navigator);
        if (proto) {
            const desc = Object.getOwnPropertyDescriptor(proto, 'webdriver');
            if (desc && desc.configurable) {
                delete proto.webdriver;
            }
        }
        // Also try Navigator.prototype
        try {
            const pDesc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
            if (pDesc && pDesc.configurable) {
                delete Navigator.prototype.webdriver;
            }
        } catch(e) {}
        // Also delete from navigator own props
        try {
            const ownDesc = Object.getOwnPropertyDescriptor(navigator, 'webdriver');
            if (ownDesc && ownDesc.configurable) {
                delete navigator.webdriver;
            }
        } catch(e) {}
    """)
    page = await ctx.new_page()
    
    await page.goto("https://example.com", wait_until="domcontentloaded", timeout=10000)
    wd = await page.evaluate("navigator.webdriver")
    in_nav = await page.evaluate("'webdriver' in navigator")
    print(f"webdriver={wd}  'webdriver' in navigator={in_nav}")
    
    # Now test on sannysoft
    await page.goto("https://bot.sannysoft.com", wait_until="networkidle", timeout=15000)
    await asyncio.sleep(4)
    wd2 = await page.evaluate("navigator.webdriver")
    in2 = await page.evaluate("'webdriver' in navigator")
    cell = await page.evaluate("""
        () => {
            const rows = document.querySelectorAll('table tr');
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 2 && cells[0].textContent.includes('WebDriver') && !cells[0].textContent.includes('Advanced')) {
                    return {
                        test: cells[0].textContent.trim(),
                        value: cells[1].textContent.trim(),
                        className: cells[1].className,
                    };
                }
            }
            return null;
        }
    """)
    print(f"[sannysoft] webdriver={wd2}  in={in2}")
    print(f"[sannysoft] cell={cell}")
    
    await browser.close()
    await p.stop()

asyncio.run(test())
