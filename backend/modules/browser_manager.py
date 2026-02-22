"""
Leomail v3 — Anti-Detect Browser Engine
Full fingerprint randomization, device emulation, GEO-aware context, persistent sessions.
"""
import os
import json
import random
from pathlib import Path
from loguru import logger

try:
    from playwright.async_api import async_playwright, BrowserContext, Playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    async_playwright = None
    BrowserContext = None
    Playwright = None

from ..data.geo_data import get_country


# ─── User-Agent Pool ───────────────────────────────────────────────────────────

CHROME_VERSIONS = [
    "120.0.6099.109", "120.0.6099.130", "120.0.6099.199", "120.0.6099.216",
    "121.0.6167.85", "121.0.6167.139", "121.0.6167.160", "121.0.6167.184",
    "122.0.6261.57", "122.0.6261.94", "122.0.6261.111", "122.0.6261.128",
    "123.0.6312.58", "123.0.6312.86", "123.0.6312.105", "123.0.6312.122",
    "124.0.6367.60", "124.0.6367.78", "124.0.6367.91", "124.0.6367.118",
    "125.0.6422.53", "125.0.6422.76", "125.0.6422.112", "125.0.6422.141",
    "126.0.6478.55", "126.0.6478.114", "126.0.6478.126", "126.0.6478.182",
    "127.0.6533.72", "127.0.6533.89", "127.0.6533.99", "127.0.6533.119",
    "128.0.6613.84", "128.0.6613.113", "128.0.6613.119", "128.0.6613.137",
    "129.0.6668.58", "129.0.6668.70", "129.0.6668.89", "129.0.6668.100",
    "130.0.6723.58", "130.0.6723.69", "130.0.6723.91", "130.0.6723.116",
    "131.0.6778.69", "131.0.6778.85", "131.0.6778.108", "131.0.6778.139",
]

EDGE_VERSIONS = [
    "120.0.2210.61", "120.0.2210.91", "121.0.2277.83", "121.0.2277.98",
    "122.0.2365.52", "122.0.2365.80", "123.0.2420.65", "123.0.2420.81",
    "124.0.2478.51", "124.0.2478.80", "125.0.2535.51", "125.0.2535.79",
    "126.0.2592.56", "126.0.2592.87", "127.0.2651.74", "127.0.2651.98",
    "128.0.2739.42", "128.0.2739.67", "129.0.2792.52", "129.0.2792.79",
    "130.0.2849.46", "130.0.2849.68", "131.0.2903.51", "131.0.2903.86",
]

WINDOWS_VERSIONS = [
    "Windows NT 10.0; Win64; x64",
    "Windows NT 10.0; WOW64",
    "Windows NT 11.0; Win64; x64",
]

MAC_VERSIONS = [
    "Macintosh; Intel Mac OS X 10_15_7",
    "Macintosh; Intel Mac OS X 11_6_8",
    "Macintosh; Intel Mac OS X 12_7_4",
    "Macintosh; Intel Mac OS X 13_6_4",
    "Macintosh; Intel Mac OS X 14_4_1",
    "Macintosh; Intel Mac OS X 14_7_2",
]

LINUX_VERSIONS = [
    "X11; Linux x86_64",
    "X11; Ubuntu; Linux x86_64",
]

MOBILE_ANDROID = [
    ("Pixel 7", "14", {"width": 412, "height": 915, "scale": 2.625}),
    ("Pixel 7 Pro", "14", {"width": 412, "height": 892, "scale": 3.5}),
    ("Pixel 8", "14", {"width": 412, "height": 915, "scale": 2.625}),
    ("SM-S918B", "14", {"width": 360, "height": 780, "scale": 3}),        # Galaxy S23 Ultra
    ("SM-A546B", "14", {"width": 412, "height": 915, "scale": 2.625}),    # Galaxy A54
    ("SM-G991B", "13", {"width": 360, "height": 800, "scale": 3}),        # Galaxy S21
    ("22101316G", "13", {"width": 393, "height": 873, "scale": 2.75}),    # Xiaomi 13
    ("2201117TG", "13", {"width": 412, "height": 915, "scale": 2.625}),   # Xiaomi 12
    ("CPH2451", "13", {"width": 412, "height": 915, "scale": 2.625}),     # OnePlus Nord CE 3
    ("V2227A", "13", {"width": 393, "height": 851, "scale": 2.75}),       # Vivo X90
]

MOBILE_IOS = [
    ("iPhone 15 Pro", "17.4", {"width": 393, "height": 852, "scale": 3}),
    ("iPhone 15", "17.4", {"width": 390, "height": 844, "scale": 3}),
    ("iPhone 14 Pro Max", "17.3", {"width": 430, "height": 932, "scale": 3}),
    ("iPhone 14", "17.2", {"width": 390, "height": 844, "scale": 3}),
    ("iPhone 13", "17.1", {"width": 390, "height": 844, "scale": 3}),
    ("iPhone SE 3", "17.0", {"width": 375, "height": 667, "scale": 2}),
    ("iPad Pro 12.9", "17.4", {"width": 1024, "height": 1366, "scale": 2}),
    ("iPad Air", "17.3", {"width": 820, "height": 1180, "scale": 2}),
]

DESKTOP_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1600, "height": 900},
    {"width": 1680, "height": 1050},
    {"width": 1920, "height": 1080},
    {"width": 2560, "height": 1440},
]


def _generate_desktop_ua() -> str:
    """Generate a random desktop user-agent string."""
    browser_type = random.choices(["chrome", "edge"], weights=[80, 20])[0]
    os_type = random.choices(["windows", "mac", "linux"], weights=[70, 22, 8])[0]

    if os_type == "windows":
        os_str = random.choice(WINDOWS_VERSIONS)
    elif os_type == "mac":
        os_str = random.choice(MAC_VERSIONS)
    else:
        os_str = random.choice(LINUX_VERSIONS)

    if browser_type == "chrome":
        ver = random.choice(CHROME_VERSIONS)
        return f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver} Safari/537.36"
    else:
        c_ver = random.choice(CHROME_VERSIONS)
        e_ver = random.choice(EDGE_VERSIONS)
        return f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{c_ver} Safari/537.36 Edg/{e_ver}"


def _generate_mobile_ua(device_info: tuple, platform: str) -> str:
    """Generate mobile user-agent string."""
    if platform == "android":
        name, android_ver, _ = device_info
        ver = random.choice(CHROME_VERSIONS[-16:])  # Recent Chrome versions
        return (
            f"Mozilla/5.0 (Linux; Android {android_ver}; {name}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver} Mobile Safari/537.36"
        )
    else:  # ios
        name, ios_ver, _ = device_info
        webkit_ver = random.choice(["605.1.15", "604.1"])
        ver = random.choice(CHROME_VERSIONS[-8:])
        return (
            f"Mozilla/5.0 (iPhone; CPU iPhone OS {ios_ver.replace('.', '_')} like Mac OS X) "
            f"AppleWebKit/{webkit_ver} (KHTML, like Gecko) CriOS/{ver} Mobile/15E148 Safari/{webkit_ver}"
        )


# ─── GPU Combos Pool (WebGL vendor + renderer) ────────────────────────────────

GPU_COMBOS = [
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 2060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1070 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 5700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6600 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 7600 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) HD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) HD Graphics 530 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce MX150 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 2070 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
]


def _build_stealth_scripts(ua: str = "", gpu: tuple = None, hw_concurrency: int = 8,
                           device_memory: int = 8, langs: list = None) -> str:
    """
    Build comprehensive antidetect stealth JS to inject into each browser context.
    Dynamically adapts to UA (platform matching) and rotates GPU per context.
    """
    if not gpu:
        gpu = random.choice(GPU_COMBOS)
    if not langs:
        langs = ["en-US", "en"]

    # Determine platform from UA
    if "Windows" in ua:
        platform = "Win32"
    elif "Macintosh" in ua or "Mac OS" in ua:
        platform = "MacIntel"
    elif "Linux" in ua:
        platform = "Linux x86_64"
    elif "Android" in ua:
        platform = "Linux armv81"
    elif "iPhone" in ua or "iPad" in ua:
        platform = "iPhone"
    else:
        platform = "Win32"

    gpu_vendor, gpu_renderer = gpu
    langs_js = json.dumps(langs)
    canvas_seed = random.randint(1, 999999)

    return f"""
    // ═══ LEOMAIL ANTIDETECT ENGINE v2 ═══

    // 1. Hide webdriver flag (critical)
    Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
    delete navigator.__proto__.webdriver;

    // 2. Chrome runtime object
    if (!window.chrome) {{
        window.chrome = {{ runtime: {{}}, loadTimes: function(){{ return {{}} }}, csi: function(){{ return {{}} }} }};
    }}

    // 3. Navigator.platform — MUST match User-Agent
    Object.defineProperty(navigator, 'platform', {{ get: () => '{platform}' }});

    // 4. Permissions API
    const _origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications'
            ? Promise.resolve({{ state: Notification.permission }})
            : _origQuery.call(navigator.permissions, p)
    );

    // 5. Plugins (real Chrome has these)
    Object.defineProperty(navigator, 'plugins', {{
        get: () => {{
            const p = [
                {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1 }},
                {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1 }},
                {{ name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 2 }},
            ];
            p.namedItem = (n) => p.find(x => x.name === n) || null;
            p.refresh = () => {{}};
            return p;
        }}
    }});

    // 6. Languages + Hardware
    Object.defineProperty(navigator, 'languages', {{ get: () => {langs_js} }});
    Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hw_concurrency} }});
    Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {device_memory} }});

    // 7. WebGL GPU spoofing (per-context rotation)
    const _wglGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {{
        if (p === 37445) return '{gpu_vendor}';
        if (p === 37446) return '{gpu_renderer}';
        return _wglGetParam.call(this, p);
    }};
    // WebGL2 too
    if (typeof WebGL2RenderingContext !== 'undefined') {{
        const _wgl2GetParam = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(p) {{
            if (p === 37445) return '{gpu_vendor}';
            if (p === 37446) return '{gpu_renderer}';
            return _wgl2GetParam.call(this, p);
        }};
    }}
    // debugRendererInfo extension
    const _origGetExtension = WebGLRenderingContext.prototype.getExtension;
    WebGLRenderingContext.prototype.getExtension = function(name) {{
        if (name === 'WEBGL_debug_renderer_info') {{
            return {{ UNMASKED_VENDOR_WEBGL: 37445, UNMASKED_RENDERER_WEBGL: 37446 }};
        }}
        return _origGetExtension.call(this, name);
    }};

    // 8. Canvas fingerprint noise (seeded for consistency within session)
    (function() {{
        let seed = {canvas_seed};
        function seededRandom() {{
            seed = (seed * 16807 + 0) % 2147483647;
            return (seed - 1) / 2147483646;
        }}
        const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {{
            if (this.width > 16 && this.height > 16) {{
                try {{
                    const ctx = this.getContext('2d');
                    if (ctx) {{
                        const img = ctx.getImageData(0, 0, Math.min(this.width, 64), Math.min(this.height, 64));
                        for (let i = 0; i < img.data.length; i += 4) {{
                            img.data[i] = (img.data[i] + (seededRandom() * 2 - 1)) & 0xFF;
                        }}
                        ctx.putImageData(img, 0, 0);
                    }}
                }} catch(e) {{}}
            }}
            return _origToDataURL.apply(this, arguments);
        }};
        const _origToBlob = HTMLCanvasElement.prototype.toBlob;
        HTMLCanvasElement.prototype.toBlob = function(cb, type, quality) {{
            if (this.width > 16 && this.height > 16) {{
                try {{
                    const ctx = this.getContext('2d');
                    if (ctx) {{
                        const img = ctx.getImageData(0, 0, Math.min(this.width, 64), Math.min(this.height, 64));
                        for (let i = 0; i < img.data.length; i += 4) {{
                            img.data[i] = (img.data[i] + (seededRandom() * 2 - 1)) & 0xFF;
                        }}
                        ctx.putImageData(img, 0, 0);
                    }}
                }} catch(e) {{}}
            }}
            return _origToBlob.apply(this, arguments);
        }};
    }})();

    // 9. AudioContext fingerprint noise
    (function() {{
        if (typeof OfflineAudioContext !== 'undefined') {{
            const _origGetChannelData = AudioBuffer.prototype.getChannelData;
            AudioBuffer.prototype.getChannelData = function(ch) {{
                const data = _origGetChannelData.call(this, ch);
                if (data.length > 100) {{
                    for (let i = 0; i < data.length; i += 100) {{
                        data[i] += 1e-7 * (Math.random() * 2 - 1);
                    }}
                }}
                return data;
            }};
        }}
        if (typeof AnalyserNode !== 'undefined') {{
            const _origGetFloat = AnalyserNode.prototype.getFloatFrequencyData;
            AnalyserNode.prototype.getFloatFrequencyData = function(arr) {{
                _origGetFloat.call(this, arr);
                for (let i = 0; i < arr.length; i++) {{
                    arr[i] += 0.1 * (Math.random() - 0.5);
                }}
            }};
        }}
    }})();

    // 10. Battery API spoofing (prevents headless detection)
    navigator.getBattery = () => Promise.resolve({{
        charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1.0,
        addEventListener: () => {{}}, removeEventListener: () => {{}}, dispatchEvent: () => true,
    }});

    // 11. ClientRects sub-pixel noise
    (function() {{
        const _origGetRects = Element.prototype.getClientRects;
        const _origGetBounding = Element.prototype.getBoundingClientRect;
        const noise = () => (Math.random() * 0.003 - 0.0015);
        Element.prototype.getClientRects = function() {{
            const rects = _origGetRects.call(this);
            const out = [];
            for (const r of rects) {{
                out.push(new DOMRect(r.x + noise(), r.y + noise(), r.width + noise(), r.height + noise()));
            }}
            return out;
        }};
        Element.prototype.getBoundingClientRect = function() {{
            const r = _origGetBounding.call(this);
            return new DOMRect(r.x + noise(), r.y + noise(), r.width + noise(), r.height + noise());
        }};
    }})();

    // 12. MediaDevices spoofing (consistent fake device count)
    if (navigator.mediaDevices) {{
        const _origEnum = navigator.mediaDevices.enumerateDevices;
        navigator.mediaDevices.enumerateDevices = async function() {{
            return [
                {{ deviceId: 'default', kind: 'audioinput', label: '', groupId: 'default' }},
                {{ deviceId: 'comms', kind: 'audioinput', label: '', groupId: 'comms' }},
                {{ deviceId: 'default', kind: 'audiooutput', label: '', groupId: 'default' }},
                {{ deviceId: 'comms', kind: 'audiooutput', label: '', groupId: 'comms' }},
                {{ deviceId: 'webcam0', kind: 'videoinput', label: '', groupId: 'webcam' }},
            ];
        }};
    }}

    // 13. Connection API
    if (!navigator.connection) {{
        Object.defineProperty(navigator, 'connection', {{
            get: () => ({{
                effectiveType: '4g', rtt: {random.choice([50, 75, 100])},
                downlink: {random.choice([5, 8, 10, 15])}, saveData: false,
                addEventListener: () => {{}}, removeEventListener: () => {{}},
            }})
        }});
    }}
    """


PROFILES_DIR = Path("user_data/profiles")


# ─── Browser Manager ──────────────────────────────────────────────────────────

class BrowserManager:
    """Anti-detect browser engine with device emulation and persistent sessions."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright: Playwright | None = None
        self.browser = None
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    async def start(self):
        """Launch browser engine."""
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                # Anti-automation
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                # Performance
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                # WebRTC IP leak prevention (CRITICAL)
                "--disable-features=WebRtcHideLocalIpsWithMdns",
                "--enforce-webrtc-ip-permission-check",
                "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                # Anti-fingerprint
                "--disable-reading-from-canvas",
                "--disable-features=AudioServiceOutOfProcess",
                # Window
                "--window-size=1920,1080",
            ]
        )
        logger.info(f"Browser engine started (headless={self.headless})")

    async def stop(self):
        """Shutdown browser engine."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser engine stopped")

    async def create_context(
        self,
        proxy=None,
        device_type: str = "desktop",
        geo: str = None,
        session_path: str = None,
    ) -> BrowserContext:
        """
        Create a new anti-detect browser context.

        Args:
            proxy: Proxy model instance or None
            device_type: "desktop" | "phone_android" | "phone_ios"
            geo: ISO country code for timezone/locale matching (auto from proxy if None)
            session_path: path to saved session.json for persistent login
        """
        # Resolve GEO
        country_code = geo
        if not country_code and proxy and hasattr(proxy, 'geo') and proxy.geo:
            country_code = proxy.geo
        country_data = get_country(country_code) if country_code else None

        # Timezone & locale from GEO
        timezone_id = country_data["tz"] if country_data else random.choice([
            "America/New_York", "America/Chicago", "America/Los_Angeles", "America/Denver",
            "Europe/London", "Europe/Berlin", "Europe/Paris",
        ])
        lang = country_data["lang"] if country_data else "en"
        locale_str = f"{lang}-{country_code}" if country_code else f"{lang}-US"

        # Proxy config — handle SOCKS5 auth via local bridge
        proxy_config = None
        socks5_bridge = None
        if proxy:
            protocol = getattr(proxy, 'protocol', 'http') or 'http'
            has_auth = bool(getattr(proxy, 'username', None))
            is_socks = protocol in ('socks5', 'socks4')

            if is_socks and has_auth:
                # Chromium can't do SOCKS5 auth — start local HTTP bridge
                from ..services.socks5_bridge import Socks5Bridge
                socks5_bridge = Socks5Bridge(
                    proxy.host, proxy.port,
                    proxy.username, proxy.password or "",
                )
                await socks5_bridge.start()
                proxy_config = {"server": f"http://127.0.0.1:{socks5_bridge.port}"}
                logger.debug(f"SOCKS5 auth bridge: :{socks5_bridge.port} → {proxy.host}:{proxy.port}")
            elif hasattr(proxy, 'to_playwright'):
                proxy_config = proxy.to_playwright()
            elif hasattr(proxy, 'host'):
                proxy_config = {"server": f"{protocol}://{proxy.host}:{proxy.port}"}
                if has_auth and not is_socks:
                    proxy_config["username"] = proxy.username
                    proxy_config["password"] = proxy.password or ""

        # Build context options
        context_options = {
            "proxy": proxy_config,
            "locale": locale_str,
            "timezone_id": timezone_id,
            "permissions": ["geolocation"],
            "ignore_https_errors": True,
            "java_script_enabled": True,
        }

        # Device-specific configuration
        if device_type.startswith("phone_android"):
            device_info = random.choice(MOBILE_ANDROID)
            name, android_ver, screen = device_info
            context_options["user_agent"] = _generate_mobile_ua(device_info, "android")
            context_options["viewport"] = {"width": screen["width"], "height": screen["height"]}
            context_options["device_scale_factor"] = screen["scale"]
            context_options["is_mobile"] = True
            context_options["has_touch"] = True
            logger.debug(f"Emulating Android: {name} (Android {android_ver})")

        elif device_type.startswith("phone_ios"):
            device_info = random.choice(MOBILE_IOS)
            name, ios_ver, screen = device_info
            context_options["user_agent"] = _generate_mobile_ua(device_info, "ios")
            context_options["viewport"] = {"width": screen["width"], "height": screen["height"]}
            context_options["device_scale_factor"] = screen["scale"]
            context_options["is_mobile"] = True
            context_options["has_touch"] = True
            logger.debug(f"Emulating iOS: {name} (iOS {ios_ver})")

        else:
            # Desktop
            context_options["user_agent"] = _generate_desktop_ua()
            context_options["viewport"] = random.choice(DESKTOP_VIEWPORTS)
            context_options["device_scale_factor"] = random.choice([1, 1, 1, 1.25, 1.5, 2])
            context_options["is_mobile"] = False
            context_options["has_touch"] = False

        # Load persistent session if available
        if session_path and os.path.exists(session_path):
            try:
                context_options["storage_state"] = session_path
                logger.debug(f"Loading session: {session_path}")
            except Exception as e:
                logger.warning(f"Failed to load session {session_path}: {e}")

        # Create context
        context = await self.browser.new_context(**context_options)

        # Apply antidetect stealth scripts (per-context: GPU rotation, UA-matched platform)
        ctx_ua = context_options.get("user_agent", "")
        ctx_gpu = random.choice(GPU_COMBOS)
        ctx_hw = random.choice([4, 8, 12, 16])
        ctx_mem = random.choice([4, 8, 16])
        stealth_js = _build_stealth_scripts(ua=ctx_ua, gpu=ctx_gpu, hw_concurrency=ctx_hw,
                                             device_memory=ctx_mem)
        await context.add_init_script(script=stealth_js)
        logger.debug(f"Stealth: GPU={ctx_gpu[1][:40]}..., platform from UA, hw={ctx_hw}, mem={ctx_mem}")

        # Override language header to match locale
        await context.set_extra_http_headers({
            "Accept-Language": f"{locale_str},{lang};q=0.9,en;q=0.8",
        })

        logger.debug(
            f"Context created: device={device_type}, geo={country_code or 'random'}, "
            f"tz={timezone_id}, locale={locale_str}"
        )
        return context

    async def save_session(self, context: BrowserContext, account_id: int) -> str:
        """Save browser session (cookies, localStorage) for an account."""
        profile_dir = PROFILES_DIR / str(account_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        session_path = str(profile_dir / "session.json")

        state = await context.storage_state()
        with open(session_path, "w") as f:
            json.dump(state, f)

        logger.info(f"Session saved: account {account_id} → {session_path}")
        return session_path

    async def load_session_context(
        self,
        account_id: int,
        proxy=None,
        device_type: str = "desktop",
        geo: str = None,
    ) -> tuple[BrowserContext, str]:
        """Load a persistent session for an account. Returns (context, session_path)."""
        session_path = str(PROFILES_DIR / str(account_id) / "session.json")
        context = await self.create_context(
            proxy=proxy,
            device_type=device_type,
            geo=geo,
            session_path=session_path if os.path.exists(session_path) else None,
        )
        return context, session_path

    @staticmethod
    def get_session_path(account_id: int) -> str:
        """Get the session file path for an account."""
        return str(PROFILES_DIR / str(account_id) / "session.json")

    @staticmethod
    def has_session(account_id: int) -> bool:
        """Check if a saved session exists for an account."""
        return os.path.exists(PROFILES_DIR / str(account_id) / "session.json")

    async def close_context(self, context: BrowserContext):
        """Close a browser context."""
        try:
            await context.close()
        except Exception:
            pass
