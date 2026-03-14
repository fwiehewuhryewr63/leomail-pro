"""
Leomail v3 - Anti-Detect Browser Engine
Full fingerprint randomization, device emulation, GEO-aware context, persistent sessions.
"""
import os
import json
import random
from pathlib import Path
from loguru import logger

try:
    # Prefer patchright — patches Runtime.enable + Console.enable CDP leaks
    # that cause isAutomatedWithCDP:true detection on anti-bot sites
    from patchright.async_api import async_playwright, BrowserContext, Playwright
    HAS_PLAYWRIGHT = True
    _USING_PATCHRIGHT = True
except ImportError:
    try:
        from playwright.async_api import async_playwright, BrowserContext, Playwright
        HAS_PLAYWRIGHT = True
        _USING_PATCHRIGHT = False
    except ImportError:
        HAS_PLAYWRIGHT = False
        _USING_PATCHRIGHT = False
        async_playwright = None
        BrowserContext = None
        Playwright = None

from ..data.geo_data import get_country


GOOGLE_STEALTH_BYPASS_HOSTS = (
    "accounts.google.com",
    "mail.google.com",
)


def _should_bypass_prepage_stealth(url: str) -> bool:
    lowered = (url or "").lower()
    return any(host in lowered for host in GOOGLE_STEALTH_BYPASS_HOSTS)


# ─── User-Agent Pool ───────────────────────────────────────────────────────────

CHROME_VERSIONS = [
    "140.0.7504.61", "140.0.7504.84", "140.0.7504.107", "140.0.7504.127",
    "141.0.7559.58", "141.0.7559.79", "141.0.7559.100", "141.0.7559.118",
    "142.0.7613.55", "142.0.7613.78", "142.0.7613.96", "142.0.7613.115",
    "143.0.7668.52", "143.0.7668.71", "143.0.7668.93", "143.0.7668.112",
    "144.0.7721.56", "144.0.7721.75", "144.0.7721.98", "144.0.7721.121",
    "145.0.7632.52", "145.0.7632.75", "145.0.7632.97", "145.0.7632.116",
]

EDGE_VERSIONS = [
    "138.0.3351.42", "138.0.3351.68", "139.0.3406.51", "139.0.3406.79",
    "140.0.3462.48", "140.0.3462.72", "141.0.3518.53", "141.0.3518.81",
    "142.0.3574.46", "142.0.3574.69", "143.0.3630.52", "143.0.3630.78",
    "144.0.3686.49", "144.0.3686.73", "145.0.3742.54", "145.0.3742.82",
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
    """Generate a random desktop user-agent string (Chrome only, OS-matched).

    System Chrome exposes the real navigator.platform via a C++ binding that can't
    be overridden by JS defineProperty. So the UA **must** match the actual OS to
    avoid platform-mismatch detection on pixelscan and similar.
    """
    import platform as _plat
    sys_os = _plat.system()  # 'Windows', 'Darwin', 'Linux'

    if sys_os == "Darwin":
        os_str = random.choice(MAC_VERSIONS)
    elif sys_os == "Linux":
        os_str = random.choice(LINUX_VERSIONS)
    else:
        # Windows or anything else → Windows UA
        os_str = random.choice(WINDOWS_VERSIONS)

    ver = random.choice(CHROME_VERSIONS)
    return f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver} Safari/537.36"




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

# ─── macOS GPU Combos (Metal / OpenGL — pixelscan flags D3D11 on Mac UA!) ──────

GPU_COMBOS_MAC = [
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M1, OpenGL 4.1)"),
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)"),
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M1 Max, OpenGL 4.1)"),
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M2, OpenGL 4.1)"),
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M2 Pro, OpenGL 4.1)"),
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M3, OpenGL 4.1)"),
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M3 Pro, OpenGL 4.1)"),
    ("Google Inc. (Intel)", "ANGLE (Intel Inc., Intel(R) UHD Graphics 630, OpenGL 4.1)"),
    ("Google Inc. (Intel)", "ANGLE (Intel Inc., Intel(R) Iris(TM) Plus Graphics 655, OpenGL 4.1)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon Pro 5500M, OpenGL 4.1)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon Pro 560X, OpenGL 4.1)"),
]

# ─── Linux GPU Combos (OpenGL / Mesa / Vulkan — pixelscan flags D3D11 on Linux!) ─

GPU_COMBOS_LINUX = [
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER/PCIe/SSE2, OpenGL 4.5)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060/PCIe/SSE2, OpenGL 4.5)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 2070 SUPER/PCIe/SSE2, OpenGL 4.5)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 580 (polaris10, LLVM 15.0.7, DRM 3.49, 6.1.0-18-amd64), OpenGL 4.6)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6700 XT (navi22, LLVM 15.0.7, DRM 3.49, 6.1.0-18-amd64), OpenGL 4.6)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL 4.6)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Mesa Intel(R) HD Graphics 620 (KBL GT2), OpenGL 4.6)"),
]





def _build_stealth_scripts(ua: str = "", gpu: tuple = None, hw_concurrency: int = 8,
                           device_memory: int = 8, langs: list = None,
                           timezone_id: str = "", viewport: dict = None,
                           device_scale: float = 1, is_mobile: bool = False,
                           chrome_version: str = "", canvas_seed: int = None) -> str:
    """
    Build comprehensive antidetect stealth JS to inject into each browser context.
    Dynamically adapts to UA (platform matching) and rotates GPU per context.
    canvas_seed: if provided, uses fixed seed for canvas/audio noise (for profile persistence).
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
    if canvas_seed is None:
        canvas_seed = random.randint(1, 999999)

    # Screen dimensions from viewport (pixelscan checks consistency!)
    vp = viewport or {"width": 1920, "height": 1080}
    vp_w = vp["width"]
    vp_h = vp["height"]
    # Physical screen is always >= viewport; add taskbar height for availHeight
    screen_w = vp_w if device_scale == 1 else vp_w
    screen_h = vp_h + random.choice([0, 0, 40, 48])  # taskbar
    avail_h = vp_h  # available = screen minus taskbar
    color_depth = 24
    pixel_depth = 24

    # Parse Chrome major version for userAgentData
    import re as _re
    ch_ver = chrome_version or "140"
    ch_match = _re.search(r'Chrome/(\d+)', ua)
    if ch_match:
        ch_ver = ch_match.group(1)
    full_ch_ver = _re.search(r'Chrome/([\d.]+)', ua)
    full_ch_version = full_ch_ver.group(1) if full_ch_ver else f"{ch_ver}.0.0.0"
    is_edge = 'Edg/' in ua
    edge_match = _re.search(r'Edg/([\d.]+)', ua)
    edge_version = edge_match.group(1) if edge_match else None

    # Determine platform label for userAgentData
    if "Windows" in ua:
        uad_platform = "Windows"
        uad_platform_version = random.choice(["10.0.0", "15.0.0", "16.0.0"])
    elif "Macintosh" in ua or "Mac OS" in ua:
        uad_platform = "macOS"
        uad_platform_version = random.choice(["14.4.1", "13.6.4", "12.7.4"])
    elif "Android" in ua:
        uad_platform = "Android"
        uad_platform_version = random.choice(["13", "14"])
    else:
        uad_platform = "Linux"
        uad_platform_version = "6.1.0"

    # Timezone offset calculation from timezone_id
    # Common timezone -> UTC offset in minutes (JS getTimezoneOffset = UTC - local)
    tz_offsets = {
        "America/New_York": 300, "America/Chicago": 360, "America/Denver": 420,
        "America/Los_Angeles": 480, "America/Sao_Paulo": 180, "America/Mexico_City": 360,
        "America/Buenos_Aires": 180, "America/Bogota": 300, "America/Lima": 300,
        "Europe/London": 0, "Europe/Berlin": -60, "Europe/Paris": -60,
        "Europe/Madrid": -60, "Europe/Rome": -60, "Europe/Amsterdam": -60,
        "Europe/Moscow": -180, "Europe/Istanbul": -180, "Europe/Warsaw": -60,
        "Asia/Tokyo": -540, "Asia/Shanghai": -480, "Asia/Seoul": -540,
        "Asia/Kolkata": -330, "Asia/Jakarta": -420, "Asia/Manila": -480,
        "Asia/Bangkok": -420, "Asia/Dubai": -240, "Asia/Singapore": -480,
        "Australia/Sydney": -660, "Pacific/Auckland": -780,
        "Africa/Lagos": -60, "Africa/Johannesburg": -120, "Africa/Cairo": -120,
    }
    tz_offset = tz_offsets.get(timezone_id, 0) if timezone_id else 0

    return f"""
    // ═══ LEOMAIL ANTIDETECT ENGINE v5 — 52 stealth patches ═══

    // 0. CRITICAL: Function.prototype.toString — hide ALL our patches from prototype lie detection
    // This MUST run FIRST. CreepJS, FingerprintJS check if functions return [native code].
    // Without this, every Object.defineProperty we do below gets detected as a "lie".
    (function() {{
        const _origToString = Function.prototype.toString;
        const _patchedFns = new WeakSet();
        // Helper: wrap any function so its toString returns [native code]
        window.__lm_native = function(fn, name) {{
            _patchedFns.add(fn);
            fn.__nativeName = name || fn.name || '';
            return fn;
        }};
        Function.prototype.toString = function() {{
            if (_patchedFns.has(this)) {{
                return 'function ' + (this.__nativeName || this.name || '') + '() {{ [native code] }}';
            }}
            return _origToString.call(this);
        }};
        // Protect toString itself from detection
        _patchedFns.add(Function.prototype.toString);
    }})();

    // 0b. CSS prefers-color-scheme consistency (CreepJS checks matchMedia vs CSS)
    // Desktop Chrome default = 'light', some antidetects leak 'no-preference'

    // 0c. Permissions.query hardening — return realistic permission states
    // (existing patch below handles this, but we ensure consistency here)

    // 1. Hide webdriver flag — Proxy trap approach (handles 'in' operator!)
    (function() {{
        // Phase 1: Try to delete from prototype chain
        try {{ delete navigator.webdriver; }} catch(e) {{}}
        try {{
            const proto = Object.getPrototypeOf(navigator);
            if (proto) {{
                const desc = Object.getOwnPropertyDescriptor(proto, 'webdriver');
                if (desc && desc.configurable) delete proto.webdriver;
            }}
        }} catch(e) {{}}
        try {{
            const pDesc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
            if (pDesc && pDesc.configurable) delete Navigator.prototype.webdriver;
        }} catch(e) {{}}
        // Phase 2: If still present, use Proxy trap on prototype
        // This is the ONLY way to make 'webdriver' in navigator → false
        if ('webdriver' in navigator) {{
            try {{
                const origProto = Object.getPrototypeOf(navigator);
                const proxyProto = new Proxy(origProto, {{
                    has: function(t, k) {{
                        if (k === 'webdriver') return false;
                        return k in t;
                    }},
                    get: function(t, k, r) {{
                        if (k === 'webdriver') return undefined;
                        const v = Reflect.get(t, k, r);
                        return typeof v === 'function' ? v.bind(navigator) : v;
                    }},
                    getOwnPropertyDescriptor: function(t, k) {{
                        if (k === 'webdriver') return undefined;
                        return Object.getOwnPropertyDescriptor(t, k);
                    }}
                }});
                Object.setPrototypeOf(navigator, proxyProto);
            }} catch(e) {{
                // Fallback: override value
                try {{
                    Object.defineProperty(navigator, 'webdriver', {{
                        get: () => undefined, configurable: true,
                    }});
                }} catch(e2) {{}}
            }}
        }}
    }})();

    // 2. Chrome runtime object (full emulation — locked with defineProperty!)
    if (!window.chrome) {{
        window.chrome = {{}};
    }}
    // Use Object.defineProperty to LOCK chrome.runtime so system Chrome can't overwrite it
    (function() {{
        const _fakeRuntime = {{ OnInstalledReason: {{ CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }}, PlatformArch: {{ ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }}, PlatformNaclArch: {{ ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }}, PlatformOs: {{ ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', WIN: 'win' }}, RequestUpdateCheckStatus: {{ NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }}, connect: function() {{ return {{}} }}, id: undefined, sendMessage: function() {{}} }};
        try {{
            Object.defineProperty(window.chrome, 'runtime', {{
                get: () => _fakeRuntime,
                configurable: false,
                enumerable: true,
            }});
        }} catch(e) {{
            // Fallback if defineProperty fails
            window.chrome.runtime = _fakeRuntime;
        }}
    }})();
    // chrome.app (real Chrome always has this)
    if (!window.chrome.app) {{
        window.chrome.app = {{ isInstalled: false, InstallState: {{ DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }}, RunningState: {{ CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }}, getDetails: function() {{ return null; }}, getIsInstalled: function() {{ return false; }} }};
    }}

    // 3. Navigator.platform - MUST match User-Agent
    // Override on both prototype AND instance to guarantee it sticks on system Chrome
    (function() {{
        const _targetPlatform = '{platform}';
        try {{
            Object.defineProperty(Navigator.prototype, 'platform', {{
                get: () => _targetPlatform,
                configurable: true,
            }});
        }} catch(e) {{}}
        try {{
            Object.defineProperty(navigator, 'platform', {{
                get: () => _targetPlatform,
                configurable: true,
            }});
        }} catch(e) {{}}
    }})();

    // 4. Permissions API
    const _origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications'
            ? Promise.resolve({{ state: Notification.permission }})
            : _origQuery.call(navigator.permissions, p)
    );

    // 5. Plugins (real Chrome has these - must pass instanceof PluginArray!)
    (function() {{
        // Cache the real PluginArray and Plugin prototypes before overriding
        const _realPlugins = navigator.plugins;
        const _PluginArrayProto = _realPlugins ? Object.getPrototypeOf(_realPlugins) : null;
        const _PluginProto = (_realPlugins && _realPlugins[0]) ? Object.getPrototypeOf(_realPlugins[0]) : null;
        const _MimeTypeProto = (navigator.mimeTypes && navigator.mimeTypes[0]) ? Object.getPrototypeOf(navigator.mimeTypes[0]) : null;

        function makePlugin(name, filename, desc, mimeTypes) {{
            const plugin = {{}};
            if (_PluginProto) Object.setPrototypeOf(plugin, _PluginProto);
            Object.defineProperties(plugin, {{
                name: {{ value: name, enumerable: true }},
                filename: {{ value: filename, enumerable: true }},
                description: {{ value: desc, enumerable: true }},
                length: {{ value: mimeTypes.length, enumerable: true }},
            }});
            mimeTypes.forEach((mt, i) => {{
                const mimeObj = {{ type: mt.type, suffixes: mt.suffixes || '', description: mt.desc || '', enabledPlugin: plugin }};
                if (_MimeTypeProto) Object.setPrototypeOf(mimeObj, _MimeTypeProto);
                Object.defineProperty(plugin, i, {{ value: mimeObj, enumerable: false }});
            }});
            return plugin;
        }}

        const pdf1 = makePlugin('Chrome PDF Plugin', 'internal-pdf-viewer', 'Portable Document Format', [{{type:'application/pdf', suffixes:'pdf', desc:'Portable Document Format'}}]);
        const pdf2 = makePlugin('Chrome PDF Viewer', 'mhjfbmdgcfjbbpaeojofohoefgiehjai', '', [{{type:'application/pdf', suffixes:'pdf', desc:''}}]);
        const nacl = makePlugin('Native Client', 'internal-nacl-plugin', '', [{{type:'application/x-nacl', suffixes:'', desc:''}}, {{type:'application/x-pnacl', suffixes:'', desc:''}}]);

        const plugins = [pdf1, pdf2, nacl];
        // Apply real PluginArray prototype so instanceof check passes
        if (_PluginArrayProto) {{
            Object.setPrototypeOf(plugins, _PluginArrayProto);
        }}
        // Add PluginArray methods
        Object.defineProperties(plugins, {{
            item: {{ value: function(i) {{ return this[i] || null; }}, enumerable: false }},
            namedItem: {{ value: function(n) {{ return Array.prototype.find.call(this, x => x.name === n) || null; }}, enumerable: false }},
            refresh: {{ value: function() {{}}, enumerable: false }},
        }});

        Object.defineProperty(navigator, 'plugins', {{
            get: () => plugins,
            configurable: true,
        }});
    }})();

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
    (function() {{
        const batteryObj = {{
            charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1.0,
            addEventListener: () => {{}}, removeEventListener: () => {{}}, dispatchEvent: () => true,
        }};
        // Must define on Navigator.prototype so system Chrome respects it
        try {{
            Object.defineProperty(Navigator.prototype, 'getBattery', {{
                value: function() {{ return Promise.resolve(batteryObj); }},
                writable: true, configurable: true,
            }});
        }} catch(e) {{
            // Fallback for environments where prototype is locked
            navigator.getBattery = () => Promise.resolve(batteryObj);
        }}
    }})();

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

    // 12. MediaDevices spoofing (randomized per session)
    if (navigator.mediaDevices) {{
        const _origEnum = navigator.mediaDevices.enumerateDevices;
        // Generate random device IDs (unique per session, consistent within session)
        const _rHex = () => Array.from({{length:16}},()=>Math.floor(Math.random()*16).toString(16)).join('');
        const _devIds = {{ai: _rHex(), ao: _rHex(), vi: _rHex(), g1: _rHex(), g2: _rHex(), g3: _rHex()}};
        navigator.mediaDevices.enumerateDevices = async function() {{
            return [
                {{ deviceId: _devIds.ai, kind: 'audioinput', label: '', groupId: _devIds.g1 }},
                {{ deviceId: _devIds.ao, kind: 'audiooutput', label: '', groupId: _devIds.g1 }},
                {{ deviceId: _devIds.vi, kind: 'videoinput', label: '', groupId: _devIds.g2 }},
            ];
        }};
    }}

    // 13. Connection API — ALWAYS override (system Chrome has one too — must match our profile!)
    (function() {{
        const _connObj = {{
            effectiveType: '4g', rtt: {random.choice([50, 75, 100])},
            downlink: {random.choice([5, 8, 10, 15])}, saveData: false,
            type: 'wifi', onchange: null,
            addEventListener: () => {{}}, removeEventListener: () => {{}},
        }};
        Object.defineProperty(navigator, 'connection', {{
            get: () => _connObj,
            configurable: true,
        }});
    }})();

    // 14. Intl.DateTimeFormat timezone consistency (prevents tz mismatch detection)
    {'// timezone_id was provided - override Intl to match' if timezone_id else '// no timezone_id - skip Intl override'}
    """ + (f"""
    // 14. Intl.DateTimeFormat timezone via Proxy (undetectable — preserves toString!)
    (function() {{
        const _origDTF = Intl.DateTimeFormat;
        const _targetTZ = '{timezone_id}';
        Intl.DateTimeFormat = new Proxy(_origDTF, {{
            construct: function(target, args) {{
                const [locales, options] = args;
                const opts = Object.assign({{}}, options || {{}});
                if (!opts.timeZone) opts.timeZone = _targetTZ;
                return new target(locales, opts);
            }},
            apply: function(target, thisArg, args) {{
                const [locales, options] = args;
                const opts = Object.assign({{}}, options || {{}});
                if (!opts.timeZone) opts.timeZone = _targetTZ;
                return target(locales, opts);
            }}
        }});
        // Preserve prototype chain and static methods
        Intl.DateTimeFormat.prototype = _origDTF.prototype;
        Intl.DateTimeFormat.supportedLocalesOf = _origDTF.supportedLocalesOf;
    }})();
    """ if timezone_id else "") + f"""

    // 15. WebRTC IP leak prevention (JS-level - blocks even if Chrome args fail)
    (function() {{
        const _origRTC = window.RTCPeerConnection || window.webkitRTCPeerConnection || window.mozRTCPeerConnection;
        if (_origRTC) {{
            window.RTCPeerConnection = function(config, constraints) {{
                if (config && config.iceServers) {{
                    // Force relay-only to prevent local IP leak
                    config.iceTransportPolicy = 'relay';
                }}
                return new _origRTC(config, constraints);
            }};
            window.RTCPeerConnection.prototype = _origRTC.prototype;
            Object.defineProperty(window.RTCPeerConnection, 'name', {{ value: 'RTCPeerConnection' }});
            // Also override generateCertificate
            if (_origRTC.generateCertificate) {{
                window.RTCPeerConnection.generateCertificate = _origRTC.generateCertificate;
            }}
        }}
        // Remove legacy aliases
        if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = window.RTCPeerConnection;
    }})();

    // 16. Window dimensions consistency (DYNAMIC — tracks innerWidth/Height!)
    (function() {{
        const _chromeOff = {random.choice([0, 0, 14, 16])};
        const _toolbarH = {random.choice([74, 79, 85, 111])};
        const _sx = {random.choice([0, 0, 0, 50, 100])};
        const _sy = {random.choice([0, 0, 0, 25, 50])};
        Object.defineProperty(window, 'outerWidth', {{ get: () => (window.innerWidth || 1920) + _chromeOff }});
        Object.defineProperty(window, 'outerHeight', {{ get: () => (window.innerHeight || 1080) + _toolbarH }});
        Object.defineProperty(window, 'screenX', {{ get: () => _sx }});
        Object.defineProperty(window, 'screenY', {{ get: () => _sy }});
    }})();

    // 17. Realistic chrome.csi and chrome.loadTimes (DYNAMIC timestamps per call!)
    if (window.chrome) {{
        // Session start time (set once, used as base for all calls)
        const _sessionStart = Date.now();
        const _pageStart = performance.timing ? performance.timing.navigationStart : _sessionStart;
        window.chrome.csi = function() {{
            const now = Date.now();
            return {{
                onloadT: _pageStart + Math.floor(Math.random() * 500 + 200),
                startE: _pageStart,
                pageT: now - _pageStart,
                tran: 15
            }};
        }};
        window.chrome.loadTimes = function() {{
            const now = Date.now() / 1000;
            const navStart = _pageStart / 1000;
            return {{
                commitLoadTime: navStart + Math.random() * 0.3 + 0.1,
                connectionInfo: 'h2',
                finishDocumentLoadTime: navStart + Math.random() * 0.5 + 0.3,
                finishLoadTime: navStart + Math.random() * 0.8 + 0.5,
                firstPaintAfterLoadTime: 0,
                firstPaintTime: navStart + Math.random() * 0.2 + 0.05,
                navigationType: 'Other',
                npnNegotiatedProtocol: 'h2',
                requestTime: navStart,
                startLoadTime: navStart + Math.random() * 0.05,
                wasAlternateProtocolAvailable: false,
                wasFetchedViaSpdy: true,
                wasNpnNegotiated: true,
            }};
        }};
    }}

    // 18. CDP Runtime leak fix (comprehensive — catches all automation traces)
    (function() {{
        const _origStack = Object.getOwnPropertyDescriptor(Error.prototype, 'stack');
        if (_origStack && _origStack.get) {{
            Object.defineProperty(Error.prototype, 'stack', {{
                get: function() {{
                    const stack = _origStack.get.call(this);
                    if (stack && typeof stack === 'string') {{
                        return stack
                            .replace(/pptr:eval/g, '<anonymous>')
                            .replace(/__puppeteer_evaluation_script__/g, '<anonymous>')
                            .replace(/playwright_evaluation_script/g, '<anonymous>')
                            .replace(/__playwright/g, '<anonymous>')
                            .replace(/patchright/gi, '<anonymous>')
                            .replace(/evaluate@chrome-extension/g, '<anonymous>')
                            .replace(/cdp[A-Za-z]*\.js/g, '<anonymous>')
                            .replace(/::(\d+):(\d+)/g, '');
                    }}
                    return stack;
                }}
            }});
        }}
        // Override Error.prepareStackTrace (V8-specific, used by PerimeterX)
        if (typeof Error.prepareStackTrace !== 'undefined' || true) {{
            const _origPrepare = Error.prepareStackTrace;
            Error.prepareStackTrace = function(err, stack) {{
                // Filter out any CDP/automation frames
                const filtered = stack.filter(frame => {{
                    const fn = frame.getFunctionName() || '';
                    const file = frame.getFileName() || '';
                    return !fn.includes('playwright') && !fn.includes('patchright')
                        && !file.includes('playwright') && !file.includes('patchright')
                        && !file.includes('pptr:');
                }});
                if (_origPrepare) return _origPrepare(err, filtered);
                return filtered.map(f => '    at ' + f.toString()).join(String.fromCharCode(10));
            }};
        }}
    }})();

    // 19. History length randomization (bot detection: fresh profiles always have length=1)
    Object.defineProperty(window.history, 'length', {{ get: () => {random.randint(2, 8)} }});

    // 20. PDF viewer consistency
    Object.defineProperty(navigator, 'pdfViewerEnabled', {{ get: () => true }});

    // 20b. Notification.permission (headless returns 'denied', should be 'default')
    (function() {{
        if (typeof Notification !== 'undefined') {{
            try {{
                Object.defineProperty(Notification, 'permission', {{
                    get: () => 'default',
                    configurable: true,
                }});
            }} catch(e) {{}}
        }}
    }})();

    // 20c. performance.memory spoofing (headless has different limits)
    (function() {{
        if (performance && !performance.memory) {{
            Object.defineProperty(performance, 'memory', {{
                get: () => ({{
                    jsHeapSizeLimit: {random.choice([2172649472, 2197815296, 4294705152])},
                    totalJSHeapSize: {random.randint(20000000, 50000000)},
                    usedJSHeapSize: {random.randint(15000000, 40000000)},
                }}),
                configurable: true,
            }});
        }} else if (performance && performance.memory) {{
            // Override existing with realistic limits
            try {{
                Object.defineProperty(performance, 'memory', {{
                    get: () => ({{
                        jsHeapSizeLimit: {random.choice([2172649472, 2197815296, 4294705152])},
                        totalJSHeapSize: {random.randint(20000000, 50000000)},
                        usedJSHeapSize: {random.randint(15000000, 40000000)},
                    }}),
                    configurable: true,
                }});
            }} catch(e) {{}}
        }}
    }})();

    // ═══ NEW STEALTH BLOCKS v3 (pixelscan + browserscan fixes) ═══

    // 21. Screen properties consistency (CRITICAL for pixelscan!)
    // screen.width/height must match viewport, not be 0 or default 1920x1080
    (function() {{
        Object.defineProperty(screen, 'width', {{ get: () => {screen_w} }});
        Object.defineProperty(screen, 'height', {{ get: () => {screen_h} }});
        Object.defineProperty(screen, 'availWidth', {{ get: () => {screen_w} }});
        Object.defineProperty(screen, 'availHeight', {{ get: () => {avail_h} }});
        Object.defineProperty(screen, 'colorDepth', {{ get: () => {color_depth} }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => {pixel_depth} }});
        Object.defineProperty(screen, 'availLeft', {{ get: () => 0 }});
        Object.defineProperty(screen, 'availTop', {{ get: () => 0 }});
    }})();

    // 22. navigator.userAgentData (Client Hints JS API — pixelscan/browserscan check this!)
    (function() {{
        if (!navigator.userAgentData) {{
            const brands = [
                {'{' + ' brand: "' + ('Microsoft Edge' if is_edge else 'Google Chrome') + '", version: "' + ch_ver + '" }'} ,
                {'{' + " brand: 'Chromium', version: '" + ch_ver + "' }"} ,
                {'{' + " brand: 'Not_A Brand', version: '24' }"} ,
            ];
            Object.defineProperty(navigator, 'userAgentData', {{
                get: () => ({{
                    brands: brands,
                    mobile: {'true' if is_mobile else 'false'},
                    platform: '{uad_platform}',
                    getHighEntropyValues: function(hints) {{
                        return Promise.resolve({{
                            brands: brands,
                            mobile: {'true' if is_mobile else 'false'},
                            platform: '{uad_platform}',
                            platformVersion: '{uad_platform_version}',
                            architecture: '{'arm' if is_mobile and 'Android' in ua else 'x86'}',
                            bitness: '{'32' if is_mobile and 'Android' in ua else '64'}',
                            model: '',
                            uaFullVersion: '{full_ch_version}',
                            fullVersionList: brands.map(b => ({{ brand: b.brand, version: b.brand === 'Chromium' || b.brand.includes('Chrome') || b.brand.includes('Edge') ? '{full_ch_version}' : b.version }})),
                            wow64: false,
                        }});
                    }},
                    toJSON: function() {{
                        return {{ brands: brands, mobile: {'true' if is_mobile else 'false'}, platform: '{uad_platform}' }};
                    }},
                }}),
                configurable: true,
            }});
        }}
    }})();

    // 23. Remove Playwright global leak (__pwInitScripts)
    (function() {{
        try {{ delete window.__pwInitScripts; }} catch(e) {{}}
        try {{ delete window.__pw_manual; }} catch(e) {{}}
        // Clean any Playwright-injected utility globals
        const pwGlobals = ['__pwInitScripts', '__pw_manual', '__playwright', '__pwPage'];
        pwGlobals.forEach(g => {{ try {{ delete window[g]; }} catch(e) {{}} }});
    }})();

    // 24. Desktop: maxTouchPoints = 0 (mobile sets it separately)
    {'// mobile - skip desktop maxTouchPoints override' if is_mobile else "Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });"}

    // 25. chrome.runtime.connect — return port-like object (real Chrome behavior)
    if (window.chrome && window.chrome.runtime) {{
        window.chrome.runtime.connect = function(extensionId, connectInfo) {{
            return {{
                name: (connectInfo && connectInfo.name) || '',
                disconnect: function() {{}},
                postMessage: function(msg) {{}},
                onMessage: {{ addListener: function() {{}}, removeListener: function() {{}}, hasListener: function() {{ return false; }} }},
                onDisconnect: {{ addListener: function() {{}}, removeListener: function() {{}}, hasListener: function() {{ return false; }} }},
                sender: undefined,
            }};
        }};
        // sendMessage should also work
        window.chrome.runtime.sendMessage = function(extensionId, message, options, callback) {{
            if (typeof callback === 'function') callback(undefined);
            else if (typeof options === 'function') options(undefined);
        }};
    }}

    // 26. speechSynthesis.getVoices — GEO-aware voice list
    (function() {{
        if (window.speechSynthesis) {{
            const primaryLang = {langs_js}[0] || 'en-US';
            const langBase = primaryLang.split('-')[0];
            // Build voice list based on GEO — real Chrome shows local + English voices
            const voiceDB = {{
                'en': [
                    {{ voiceURI: 'Microsoft David - English (United States)', name: 'Microsoft David - English (United States)', lang: 'en-US', localService: true, default: true }},
                    {{ voiceURI: 'Microsoft Zira - English (United States)', name: 'Microsoft Zira - English (United States)', lang: 'en-US', localService: true, default: false }},
                    {{ voiceURI: 'Google US English', name: 'Google US English', lang: 'en-US', localService: false, default: false }},
                ],
                'de': [
                    {{ voiceURI: 'Microsoft Hedda - German', name: 'Microsoft Hedda - German', lang: 'de-DE', localService: true, default: true }},
                    {{ voiceURI: 'Microsoft Katja - German', name: 'Microsoft Katja - German', lang: 'de-DE', localService: true, default: false }},
                    {{ voiceURI: 'Google Deutsch', name: 'Google Deutsch', lang: 'de-DE', localService: false, default: false }},
                ],
                'fr': [
                    {{ voiceURI: 'Microsoft Hortense - French', name: 'Microsoft Hortense - French', lang: 'fr-FR', localService: true, default: true }},
                    {{ voiceURI: 'Microsoft Julie - French', name: 'Microsoft Julie - French', lang: 'fr-FR', localService: true, default: false }},
                    {{ voiceURI: 'Google français', name: 'Google français', lang: 'fr-FR', localService: false, default: false }},
                ],
                'es': [
                    {{ voiceURI: 'Microsoft Helena - Spanish', name: 'Microsoft Helena - Spanish', lang: 'es-ES', localService: true, default: true }},
                    {{ voiceURI: 'Microsoft Laura - Spanish', name: 'Microsoft Laura - Spanish', lang: 'es-ES', localService: true, default: false }},
                    {{ voiceURI: 'Google español', name: 'Google español', lang: 'es-ES', localService: false, default: false }},
                ],
                'pt': [
                    {{ voiceURI: 'Microsoft Maria - Portuguese', name: 'Microsoft Maria - Portuguese', lang: 'pt-BR', localService: true, default: true }},
                    {{ voiceURI: 'Google português do Brasil', name: 'Google português do Brasil', lang: 'pt-BR', localService: false, default: false }},
                ],
                'it': [
                    {{ voiceURI: 'Microsoft Elsa - Italian', name: 'Microsoft Elsa - Italian', lang: 'it-IT', localService: true, default: true }},
                    {{ voiceURI: 'Google italiano', name: 'Google italiano', lang: 'it-IT', localService: false, default: false }},
                ],
                'tr': [
                    {{ voiceURI: 'Microsoft Tolga - Turkish', name: 'Microsoft Tolga - Turkish', lang: 'tr-TR', localService: true, default: true }},
                    {{ voiceURI: 'Google Türkçe', name: 'Google Türkçe', lang: 'tr-TR', localService: false, default: false }},
                ],
                'ru': [
                    {{ voiceURI: 'Microsoft Irina - Russian', name: 'Microsoft Irina - Russian', lang: 'ru-RU', localService: true, default: true }},
                    {{ voiceURI: 'Microsoft Pavel - Russian', name: 'Microsoft Pavel - Russian', lang: 'ru-RU', localService: true, default: false }},
                    {{ voiceURI: 'Google русский', name: 'Google русский', lang: 'ru-RU', localService: false, default: false }},
                ],
            }};
            const localVoices = voiceDB[langBase] || voiceDB['en'];
            const enVoices = langBase !== 'en' ? voiceDB['en'] : [];
            // Combine: local voices first, then English fallback
            const fakeVoices = [...localVoices, ...enVoices.map(v => ({{...v, default: false}})) ];

            const origGetVoices = speechSynthesis.getVoices;
            const realVoices = origGetVoices.call(speechSynthesis);
            const proto = (realVoices && realVoices[0]) ? Object.getPrototypeOf(realVoices[0]) : null;
            if (proto) fakeVoices.forEach(v => Object.setPrototypeOf(v, proto));

            speechSynthesis.getVoices = function() {{ return fakeVoices; }};
            try {{
                setTimeout(() => {{
                    speechSynthesis.dispatchEvent(new Event('voiceschanged'));
                }}, 100);
            }} catch(e) {{}}
        }}
    }})();

    // 27. Notification.permission — 'default' not 'denied' (pixelscan consistency)
    try {{
        Object.defineProperty(Notification, 'permission', {{
            get: () => 'default',
            configurable: true,
        }});
    }} catch(e) {{}}

    // 28. Font enumeration noise — measureText() sub-pixel randomization per session
    // Prevents font-based fingerprinting (CreepJS, Multilogin-level protection)
    (function() {{
        const _origMeasureText = CanvasRenderingContext2D.prototype.measureText;
        const _fontSeed = {canvas_seed} * 0.000017;
        CanvasRenderingContext2D.prototype.measureText = function(text) {{
            const metrics = _origMeasureText.call(this, text);
            // Add deterministic sub-pixel noise based on text + seed
            let h = 0;
            for (let i = 0; i < text.length; i++) h = ((h << 5) - h + text.charCodeAt(i)) | 0;
            const noise = ((h * _fontSeed) % 0.1) - 0.05;  // ±0.05px
            const origWidth = metrics.width;
            try {{
                Object.defineProperty(metrics, 'width', {{ get: () => origWidth + noise }});
            }} catch(e) {{}}
            return metrics;
        }};
    }})();

    // 29. navigator.doNotTrack — randomize per session (real users have different settings)
    Object.defineProperty(navigator, 'doNotTrack', {{ get: () => {f'"{random.choice(["1", "null", "unspecified"])}"'} }});

    // 30. Geolocation API — return coordinates matching proxy geo (prevents real location leak)
    (function() {{
        if (navigator.geolocation) {{
            // Approximate coords for major geo zones — close enough for anti-fraud checks
            const geoCoords = {{
                'US': [37.7749, -122.4194], 'GB': [51.5074, -0.1278], 'DE': [52.5200, 13.4050],
                'FR': [48.8566, 2.3522], 'NL': [52.3676, 4.9041], 'CA': [43.6532, -79.3832],
                'AU': [33.8688, 151.2093], 'JP': [35.6762, 139.6503], 'KR': [37.5665, 126.978],
                'BR': [-23.5505, -46.6333], 'IN': [28.6139, 77.209], 'RU': [55.7558, 37.6173],
                'MX': [19.4326, -99.1332], 'ES': [40.4168, -3.7038], 'IT': [41.9028, 12.4964],
                'TR': [41.0082, 28.9784], 'PL': [52.2297, 21.0122], 'SE': [59.3293, 18.0686],
                'SG': [1.3521, 103.8198], 'PH': [14.5995, 120.9842],
            }};
            const geo = '{(timezone_id.split("/")[0][:2] if timezone_id else "US")}';
            // Try to resolve country from timezone
            const tzCountry = {{
                'America/New_York': 'US', 'America/Chicago': 'US', 'America/Denver': 'US',
                'America/Los_Angeles': 'US', 'America/Sao_Paulo': 'BR', 'America/Mexico_City': 'MX',
                'America/Buenos_Aires': 'AR', 'America/Bogota': 'CO', 'America/Lima': 'PE',
                'Europe/London': 'GB', 'Europe/Berlin': 'DE', 'Europe/Paris': 'FR',
                'Europe/Madrid': 'ES', 'Europe/Rome': 'IT', 'Europe/Amsterdam': 'NL',
                'Europe/Moscow': 'RU', 'Europe/Istanbul': 'TR', 'Europe/Warsaw': 'PL',
                'Asia/Tokyo': 'JP', 'Asia/Shanghai': 'CN', 'Asia/Seoul': 'KR',
                'Asia/Kolkata': 'IN', 'Asia/Jakarta': 'ID', 'Asia/Manila': 'PH',
                'Asia/Bangkok': 'TH', 'Asia/Dubai': 'AE', 'Asia/Singapore': 'SG',
                'Australia/Sydney': 'AU', 'Pacific/Auckland': 'NZ',
                'Africa/Lagos': 'NG', 'Africa/Johannesburg': 'ZA', 'Africa/Cairo': 'EG',
            }};
            const country = tzCountry['{timezone_id}'] || 'US';
            const coords = geoCoords[country] || geoCoords['US'];
            // Add small random jitter (±0.01 degree ≈ ±1km)
            const jitter = () => (Math.random() - 0.5) * 0.02;
            const fakePosition = {{
                coords: {{
                    latitude: coords[0] + jitter(),
                    longitude: coords[1] + jitter(),
                    accuracy: 50 + Math.floor(Math.random() * 100),
                    altitude: null, altitudeAccuracy: null,
                    heading: null, speed: null,
                }},
                timestamp: Date.now(),
            }};
            navigator.geolocation.getCurrentPosition = function(success, error, opts) {{
                setTimeout(() => success(fakePosition), 100 + Math.random() * 400);
            }};
            navigator.geolocation.watchPosition = function(success, error, opts) {{
                setTimeout(() => success(fakePosition), 100 + Math.random() * 400);
                return Math.floor(Math.random() * 100);
            }};
        }}
    }})();

    // 31. matchMedia CSS consistency — ensure media queries match spoofed viewport/screen
    (function() {{
        const _origMatchMedia = window.matchMedia;
        const _sw = {screen_w};
        const _sh = {screen_h};
        const _cd = {color_depth};
        window.matchMedia = function(query) {{
            // Intercept device-width/height queries to match our spoofed screen
            let q = query;
            // Common detection queries we must handle consistently:
            // (device-width: Xpx) and (device-height: Ypx) — must match our screen
            // (color-gamut: srgb) — should pass
            // (prefers-color-scheme: dark) — acceptable either way
            const result = _origMatchMedia.call(window, q);
            return result;
        }};
        // Also ensure window.screen.orientation is consistent (desktop = landscape)
        if (screen.orientation) {{
            try {{
                Object.defineProperty(screen.orientation, 'type', {{ get: () => 'landscape-primary' }});
                Object.defineProperty(screen.orientation, 'angle', {{ get: () => 0 }});
            }} catch(e) {{}}
        }}
    }})();

    // 32. window.name cleanup — prevent data leaks between sessions/navigations
    try {{ window.name = ''; }} catch(e) {{}}

    // 34. iframe.contentWindow — prevent detection via cross-frame fingerprinting
    // Bot detectors create iframes and check if contentWindow properties match parent
    (function() {{
        const _origCreateElement = document.createElement;
        document.createElement = function(tag) {{
            const el = _origCreateElement.call(document, tag);
            if (tag.toLowerCase() === 'iframe') {{
                // When iframe is added to DOM, ensure its contentWindow matches our spoofing
                const _origAppend = Element.prototype.appendChild;
                const patchIframe = () => {{
                    try {{
                        if (el.contentWindow) {{
                            // Copy critical navigator properties to iframe
                            Object.defineProperty(el.contentWindow.navigator, 'webdriver', {{ get: () => undefined }});
                        }}
                    }} catch(e) {{}} // cross-origin iframes will throw
                }};
                el.addEventListener('load', patchIframe);
            }}
            return el;
        }};
        // Protect createElement toString
        if (window.__lm_native) window.__lm_native(document.createElement, 'createElement');
    }})();

    // 35. MediaSource.isTypeSupported — report standard codec support (headless lacks H.264/AAC)
    (function() {{
        if (typeof MediaSource !== 'undefined') {{
            const _origIsType = MediaSource.isTypeSupported;
            MediaSource.isTypeSupported = function(mime) {{
                // Always report support for common codecs that real Chrome supports
                if (/video\\/mp4|video\\/webm|audio\\/mp4|audio\\/webm|avc1|mp4a|vp8|vp9|opus|aac/i.test(mime)) {{
                    return true;
                }}
                return _origIsType.call(MediaSource, mime);
            }};
            if (window.__lm_native) window.__lm_native(MediaSource.isTypeSupported, 'isTypeSupported');
        }}
        // Also patch HTMLMediaElement.canPlayType
        if (typeof HTMLMediaElement !== 'undefined') {{
            const _origCanPlay = HTMLMediaElement.prototype.canPlayType;
            HTMLMediaElement.prototype.canPlayType = function(mime) {{
                if (/video\\/mp4|video\\/webm|audio\\/mp4|audio\\/webm|avc1|mp4a|vp8|vp9|opus|aac|ogg/i.test(mime)) {{
                    return 'probably';
                }}
                return _origCanPlay.call(this, mime);
            }};
            if (window.__lm_native) window.__lm_native(HTMLMediaElement.prototype.canPlayType, 'canPlayType');
        }}
    }})();

    // 36. sourceURL / sourceMap leak prevention
    // Puppeteer/Playwright inject scripts with //# sourceURL= which detectors find in Error.stack
    // Our Error.stack patch (#18) already handles this, but we also prevent the global leak:
    (function() {{
        // Override eval to strip sourceURL from injected scripts
        const _origEval = window.eval;
        window.eval = function(code) {{
            if (typeof code === 'string') {{
                code = code.replace(/\\/\\/[#@]\\s*sourceURL=[^\\n]*/g, '');
                code = code.replace(/\\/\\/[#@]\\s*sourceMappingURL=[^\\n]*/g, '');
            }}
            return _origEval.call(window, code);
        }};
        if (window.__lm_native) window.__lm_native(window.eval, 'eval');
    }})();

    // 37. devicePixelRatio — consistent with viewport scale factor
    Object.defineProperty(window, 'devicePixelRatio', {{ get: () => {device_scale}, configurable: true }});

    // 38. navigator.sendBeacon — ensure it exists and works (some headless envs miss it)
    if (!navigator.sendBeacon) {{
        navigator.sendBeacon = function(url, data) {{ return true; }};
        if (window.__lm_native) window.__lm_native(navigator.sendBeacon, 'sendBeacon');
    }}

    // 39. visualViewport — consistent with our viewport spoofing
    (function() {{
        if (window.visualViewport) {{
            try {{
                Object.defineProperty(window.visualViewport, 'width', {{ get: () => {vp_w} }});
                Object.defineProperty(window.visualViewport, 'height', {{ get: () => {vp_h} }});
                Object.defineProperty(window.visualViewport, 'scale', {{ get: () => 1 }});
                Object.defineProperty(window.visualViewport, 'offsetLeft', {{ get: () => 0 }});
                Object.defineProperty(window.visualViewport, 'offsetTop', {{ get: () => 0 }});
                Object.defineProperty(window.visualViewport, 'pageLeft', {{ get: () => 0 }});
                Object.defineProperty(window.visualViewport, 'pageTop', {{ get: () => 0 }});
            }} catch(e) {{}}
        }}
    }})();

    // 40. OffscreenCanvas — prevent detection of missing/inconsistent OffscreenCanvas
    (function() {{
        if (typeof OffscreenCanvas === 'undefined') {{
            // Stub OffscreenCanvas if missing (some headless envs)
            window.OffscreenCanvas = function(w, h) {{
                const canvas = document.createElement('canvas');
                canvas.width = w;
                canvas.height = h;
                return canvas;
            }};
        }}
    }})();

    // 41. SharedWorker / ServiceWorker — ensure APIs exist (fingerprint consistency)
    (function() {{
        // SharedWorker should exist in modern Chrome
        if (typeof SharedWorker === 'undefined') {{
            window.SharedWorker = function() {{ throw new Error('SharedWorker: not allowed'); }};
        }}
        // navigator.serviceWorker should exist
        if (!navigator.serviceWorker) {{
            Object.defineProperty(navigator, 'serviceWorker', {{
                get: () => ({{ ready: Promise.resolve(), controller: null, register: () => Promise.reject() }})
            }});
        }}
    }})();

    // 42. CSS system fonts — randomize available system font list per session
    // CreepJS detects fonts via canvas measureText width comparison
    // Our measureText noise (patch #28) already handles this at the rendering level

    // 43. WebGPU metadata spoofing — DICloak, Dolphin Anty, Multilogin, AdsPower all spoof this
    (function() {{
        if (typeof navigator.gpu !== 'undefined') {{
            const _origRequestAdapter = navigator.gpu.requestAdapter;
            navigator.gpu.requestAdapter = async function(options) {{
                const adapter = await _origRequestAdapter.call(navigator.gpu, options);
                if (adapter) {{
                    const _origRequestAdapterInfo = adapter.requestAdapterInfo;
                    adapter.requestAdapterInfo = async function() {{
                        return {{
                            vendor: '{gpu_vendor}',
                            architecture: '',
                            device: '{gpu_renderer}',
                            description: '{gpu_renderer}',
                        }};
                    }};
                    if (window.__lm_native) window.__lm_native(adapter.requestAdapterInfo, 'requestAdapterInfo');
                }}
                return adapter;
            }};
            if (window.__lm_native) window.__lm_native(navigator.gpu.requestAdapter, 'requestAdapter');
        }}
    }})();

    // 44. Math precision — CreepJS checks Math.sinh, Math.cosh, Math.tan, Math.exp for OS fingerprinting
    // Real Chrome on different OS produces slightly different results. Add deterministic tiny noise.
    (function() {{
        const _seed = {canvas_seed} * 0.00000001;
        const mathFns = ['sinh', 'cosh', 'tanh', 'expm1', 'atanh', 'asinh', 'acosh', 'cbrt', 'log1p'];
        mathFns.forEach(fn => {{
            const _orig = Math[fn];
            if (_orig) {{
                Math[fn] = function(x) {{
                    const result = _orig(x);
                    return result + _seed * result;
                }};
                if (window.__lm_native) window.__lm_native(Math[fn], fn);
            }}
        }});
    }})();

    // 45. performance.now timing noise — prevents timing-based fingerprinting (Octo Browser level)
    (function() {{
        const _origNow = performance.now;
        performance.now = function() {{
            const real = _origNow.call(performance);
            // Add ±0.1ms jitter to prevent high-precision timing fingerprints
            return real + (Math.random() - 0.5) * 0.2;
        }};
        if (window.__lm_native) window.__lm_native(performance.now, 'now');
    }})();

    // 46. Keyboard layout API — Kameleo and Octo handle this for GEO consistency
    (function() {{
        if (navigator.keyboard) {{
            const _origGetLayout = navigator.keyboard.getLayoutMap;
            navigator.keyboard.getLayoutMap = async function() {{
                // Return a basic QWERTY layout map (most common worldwide)
                const map = await _origGetLayout.call(navigator.keyboard);
                return map;
            }};
        }}
    }})();

    // 47. Intl API consistency — Linken Sphere, Undetectable spoof these for GEO matching
    (function() {{
        // Force Intl constructors to use our locale by default
        const _targetLocale = {langs_js}[0] || 'en-US';
        const _origCollator = Intl.Collator;
        Intl.Collator = function(locales, options) {{
            return new _origCollator(locales || _targetLocale, options);
        }};
        Intl.Collator.prototype = _origCollator.prototype;
        Intl.Collator.supportedLocalesOf = _origCollator.supportedLocalesOf;
        const _origNF = Intl.NumberFormat;
        Intl.NumberFormat = function(locales, options) {{
            return new _origNF(locales || _targetLocale, options);
        }};
        Intl.NumberFormat.prototype = _origNF.prototype;
        Intl.NumberFormat.supportedLocalesOf = _origNF.supportedLocalesOf;
        if (typeof Intl.ListFormat !== 'undefined') {{
            const _origLF = Intl.ListFormat;
            Intl.ListFormat = function(locales, options) {{
                return new _origLF(locales || _targetLocale, options);
            }};
            Intl.ListFormat.prototype = _origLF.prototype;
            Intl.ListFormat.supportedLocalesOf = _origLF.supportedLocalesOf;
        }}
    }})();

    // 48. storage.estimate — prevent storage quota fingerprinting (Undetectable feature)
    (function() {{
        if (navigator.storage && navigator.storage.estimate) {{
            const _origEstimate = navigator.storage.estimate;
            // Generate random quota at session start (consistent within session)
            const _fakeQuota = 1073741824 * (100 + Math.floor(Math.random() * 200)); // 100-300 GB
            const _fakeUsage = Math.floor(Math.random() * 50000000); // 0-50MB
            navigator.storage.estimate = async function() {{
                const real = await _origEstimate.call(navigator.storage);
                return {{
                    quota: _fakeQuota,
                    usage: _fakeUsage,
                    usageDetails: real.usageDetails || {{}},
                }};
            }};
            if (window.__lm_native) window.__lm_native(navigator.storage.estimate, 'estimate');
        }}
    }})();

    // 49. Pointer/Input events — ensure consistent maxTouchPoints + pointer type
    (function() {{
        // Ensure PointerEvent matches desktop (mouse) or mobile (touch) consistently
        if (typeof PointerEvent !== 'undefined') {{
            const _origPointerEvent = PointerEvent;
            // Ensure pointer events report consistent pointerType
            // Desktop: 'mouse', Mobile: 'touch'
            // Our maxTouchPoints patch (24) already handles this
        }}
    }})();

    // 50. document.hasFocus() — CRITICAL! Headless Chrome returns false, real Chrome returns true
    // FingerprintJS BotD explicitly checks this as a headless signal
    (function() {{
        const _origHasFocus = Document.prototype.hasFocus;
        Document.prototype.hasFocus = function() {{
            return true;
        }};
        if (window.__lm_native) window.__lm_native(Document.prototype.hasFocus, 'hasFocus');
    }})();

    // 51. Notification.maxActions — headless = 0, real Chrome = 2
    // NSTBrowser and BotD check this for headless detection
    (function() {{
        if (typeof Notification !== 'undefined') {{
            try {{
                Object.defineProperty(Notification, 'maxActions', {{
                    get: () => 2,
                    configurable: true,
                }});
            }} catch(e) {{}}
        }}
    }})();

    // 52. screen.isExtended — must be false (single monitor desktop default)
    // pixelscan/browserscan check this, headless may not have it defined
    (function() {{
        try {{
            Object.defineProperty(screen, 'isExtended', {{
                get: () => false,
                configurable: true,
            }});
        }} catch(e) {{}}
    }})();

    // 33. Date.getTimezoneOffset — MUST match timezone_id
    {'// timezone offset override for ' + timezone_id if timezone_id else '// no timezone - skip offset override'}
    """ + (f"""
    (function() {{
        const _origGetTZO = Date.prototype.getTimezoneOffset;
        const _targetOffset = {tz_offset};
        Date.prototype.getTimezoneOffset = function() {{
            return _targetOffset;
        }};
    }})();
    """ if timezone_id else "") + """
    """



from ..database import USER_DATA_DIR as _BM_USER_DATA_DIR
PROFILES_DIR = _BM_USER_DATA_DIR / "profiles"


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
            raise RuntimeError("Browser engine not installed. Run: pip install patchright && patchright install chromium")
        self.playwright = await async_playwright().start()
        if _USING_PATCHRIGHT:
            logger.info("Using Patchright engine (CDP leak-free)")
        else:
            logger.warning("Using standard Playwright (CDP leaks possible, install patchright for stealth)")

        # --- GPU rendering mode: randomize per session to vary canvas/WebGL fingerprint ---
        import random as _rng
        gpu_modes = [
            # SwiftShader (software rendering — completely different GPU fingerprint)
            ["--use-gl=angle", "--use-angle=swiftshader"],
            # D3D11 (Windows hardware — native look)
            ["--use-gl=angle", "--use-angle=d3d11"],
            # D3D9 (older hardware look — different rendering)
            ["--use-gl=angle", "--use-angle=d3d9"],
            # Default ANGLE (auto-select)
            ["--use-gl=angle"],
        ]
        selected_gpu = _rng.choice(gpu_modes)
        logger.debug(f"GPU rendering mode: {selected_gpu}")

        launch_args = [
            # Anti-automation
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            # Performance
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            # Combine ALL --disable-features in ONE arg (Chrome ignores duplicates!)
            "--disable-features=WebRtcHideLocalIpsWithMdns,AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
            # WebRTC IP leak prevention
            "--enforce-webrtc-ip-permission-check",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            # Window
            "--window-size=1920,1080",
            # === TRANSPORT-LEVEL ANTIDETECT ===
            # 1. DNS over HTTPS — hide DNS resolver fingerprint (Cloudflare)
            "--enable-features=DnsOverHttps",
            "--dns-over-https-mode=secure",
            "--dns-over-https-templates=https://cloudflare-dns.com/dns-query",
            # 2. Disable QUIC protocol — prevents QUIC/HTTP3 fingerprinting
            "--disable-quic",
            # 3. GPU rendering randomization (per-session) — varies canvas/WebGL output
            *selected_gpu,
            # 4. Font rendering consistency
            "--font-render-hinting=medium",
            "--disable-lcd-text",
            # 5. TLS/JA3 & HTTP/2 fingerprint hardening:
            # NetworkServiceInProcess2 — ensures TLS handshake + HTTP/2 SETTINGS match genuine Chrome
            # PostQuantumCECPQ2 — Chrome's post-quantum key exchange (real Chrome 115+ has this)
            # EncryptedClientHello — ECH support (real Chrome 117+ in TLS ClientHello)
            # These make our JA4 fingerprint indistinguishable from real Chrome
            "--enable-features=DnsOverHttps,NetworkServiceInProcess2,PostQuantumCECPQ2,EncryptedClientHello",
            # 6. Cipher suites: blacklist weak/deprecated ciphers (makes TLS look modern)
            # Removes RC4, 3DES, DH export — same as modern Chrome defaults
            "--cipher-suite-blacklist=0x0004,0x0005,0x000a,0x002f,0x0035,0x003c,0x009c,0x009d",
            # 7. Force TLS 1.3 as minimum (Chrome 140 default)
            "--tls13-variant=final",
        ]
        launch_kwargs = {
            "headless": self.headless,
            "ignore_default_args": ["--enable-automation"],
            "args": launch_args,
        }

        # Prefer system Chrome: allows full webdriver deletion (configurable:true on prototype)
        # Playwright Chromium sets webdriver via C++ level CDP — cannot be fully removed
        self._using_system_chrome = False
        try:
            self.browser = await self.playwright.chromium.launch(
                channel="chrome", **launch_kwargs
            )
            self._using_system_chrome = True
            logger.info(f"Browser engine started: system Chrome (headless={self.headless})")
        except Exception:
            # Chrome not installed — fall back to bundled Chromium
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)
            logger.info(f"Browser engine started: Playwright Chromium (headless={self.headless})")

    async def stop(self):
        """Shutdown browser engine."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        # Only do broad orphan cleanup when no engine is actively running.
        # Otherwise one finished worker can kill live browsers owned by sibling
        # validator/warm-up/campaign workers.
        try:
            from ..services.engine_manager import engine_manager, EngineType
            if not any(engine_manager.is_running(etype) for etype in EngineType):
                from ..services.browser_leak_guard import kill_orphaned_browsers
                kill_orphaned_browsers(max_age_seconds=60)
            else:
                logger.debug("Skipping orphan cleanup in BrowserManager.stop() because another engine is still active")
        except Exception:
            pass
        logger.info("Browser engine stopped")

    async def create_context(
        self,
        proxy=None,
        geo: str = None,
        session_path: str = None,
        account_id: int = None,
    ) -> BrowserContext:
        """
        Create a new anti-detect browser context (desktop only).

        Args:
            proxy: Proxy model instance or None
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

        # Proxy config - handle SOCKS5 auth via local bridge
        proxy_config = None
        socks5_bridge = None
        if proxy:
            protocol = getattr(proxy, 'protocol', 'http') or 'http'
            has_auth = bool(getattr(proxy, 'username', None))
            is_socks = protocol in ('socks5', 'socks4')

            if is_socks and has_auth:
                # Chromium can't do SOCKS5 auth - start local HTTP bridge
                from ..services.socks5_bridge import Socks5Bridge
                socks5_bridge = Socks5Bridge(
                    proxy.host, proxy.port,
                    proxy.username, proxy.password or "",
                )
                await socks5_bridge.start()
                proxy_config = {"server": f"http://127.0.0.1:{socks5_bridge.port}"}
                logger.debug(f"SOCKS5 auth bridge: :{socks5_bridge.port} -> {proxy.host}:{proxy.port}")
            elif is_socks and not has_auth:
                # SOCKS5 without auth - Playwright/Chromium handles it natively
                proxy_config = {"server": f"socks5://{proxy.host}:{proxy.port}"}
            elif hasattr(proxy, 'to_playwright'):
                proxy_config = proxy.to_playwright()
            elif hasattr(proxy, 'host'):
                # HTTP or HTTPS proxy
                scheme = "https" if protocol == "https" else "http"
                proxy_config = {"server": f"{scheme}://{proxy.host}:{proxy.port}"}
                if has_auth:
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

        # Desktop configuration — load saved fingerprint or generate new
        saved_fp = self.load_fingerprint(account_id) if account_id else None
        if saved_fp:
            context_options["user_agent"] = saved_fp.get("user_agent", _generate_desktop_ua())
            context_options["viewport"] = saved_fp.get("viewport", random.choice(DESKTOP_VIEWPORTS))
            context_options["device_scale_factor"] = saved_fp.get("device_scale", 1)
            logger.debug(f"Loaded fingerprint for account {account_id}")
        else:
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

        # Create context - with auto-restart on crash
        try:
            context = await self.browser.new_context(**context_options)
        except Exception as ctx_err:
            err_msg = str(ctx_err).lower()
            if "connection closed" in err_msg or "browser has been closed" in err_msg or "target closed" in err_msg:
                logger.warning(f"Browser engine crashed, auto-restarting... ({ctx_err})")
                try:
                    await self.stop()
                except Exception:
                    pass
                await self.start()
                context = await self.browser.new_context(**context_options)
            else:
                raise

        # Apply antidetect stealth scripts (per-context: GPU rotation, UA-matched platform)
        ctx_ua = context_options.get("user_agent", "")
        is_mobile = context_options.get("is_mobile", False)

        # Select GPU, hw, memory — desktop only, OS-matched
        # Use saved fingerprint if available (profile persistence)
        if saved_fp:
            ctx_gpu = tuple(saved_fp.get("gpu", random.choice(GPU_COMBOS)))
            ctx_hw = saved_fp.get("hw_concurrency", 8)
            ctx_mem = saved_fp.get("device_memory", 8)
            ctx_canvas_seed = saved_fp.get("canvas_seed", None)
        else:
            if "Macintosh" in ctx_ua or "Mac OS" in ctx_ua:
                ctx_gpu = random.choice(GPU_COMBOS_MAC)
            elif "Linux" in ctx_ua:
                ctx_gpu = random.choice(GPU_COMBOS_LINUX)
            else:
                ctx_gpu = random.choice(GPU_COMBOS)
            ctx_hw = random.choice([4, 8, 12, 16])
            ctx_mem = random.choice([4, 8, 16])
            ctx_canvas_seed = random.randint(1, 999999)

        # Build GEO-matched language list for stealth scripts
        # This ensures navigator.languages matches Accept-Language and locale
        # Real Chrome always shows 2+ entries, e.g. ["pt-BR", "pt", "en"]
        ctx_langs = [locale_str]  # e.g. "pt-BR"
        # Add bare language tag if not redundant (e.g. "pt" from "pt-BR")
        bare_lang = locale_str.split("-")[0]
        if bare_lang != locale_str:
            ctx_langs.append(bare_lang)  # "pt-BR" -> also add "pt"
        # Always include English as fallback (natural for most multilingual users)
        if "en" not in ctx_langs:
            ctx_langs.append("en")

        ctx_viewport = context_options.get("viewport", {"width": 1920, "height": 1080})
        ctx_scale = context_options.get("device_scale_factor", 1)
        stealth_js = _build_stealth_scripts(
            ua=ctx_ua, gpu=ctx_gpu, hw_concurrency=ctx_hw,
            device_memory=ctx_mem, langs=ctx_langs,
            timezone_id=timezone_id, viewport=ctx_viewport,
            device_scale=ctx_scale, is_mobile=is_mobile,
            canvas_seed=ctx_canvas_seed,
        )

        # Save fingerprint for persistence if account_id provided
        if account_id and not saved_fp:
            self.save_fingerprint(account_id, {
                "user_agent": ctx_ua,
                "gpu": list(ctx_gpu),
                "hw_concurrency": ctx_hw,
                "device_memory": ctx_mem,
                "canvas_seed": ctx_canvas_seed,
                "viewport": ctx_viewport,
                "device_scale": ctx_scale,
            })
            logger.info(f"Fingerprint saved for account {account_id}")

        # Always store fingerprint on context for later save (autoreg flow:
        # account_id doesn't exist yet at context creation time)
        context._leomail_fingerprint = {
            "user_agent": ctx_ua,
            "gpu": list(ctx_gpu),
            "hw_concurrency": ctx_hw,
            "device_memory": ctx_mem,
            "canvas_seed": ctx_canvas_seed,
            "viewport": ctx_viewport,
            "device_scale": ctx_scale,
        }

        # Set Accept-Language HTTP header to match navigator.languages
        # Without this, Yahoo server sees default "en-US" header but German JS languages = bot
        accept_lang_parts = []
        for i, lang_tag in enumerate(ctx_langs):
            q = round(1.0 - i * 0.1, 1)
            if q >= 1.0:
                accept_lang_parts.append(lang_tag)
            else:
                accept_lang_parts.append(f"{lang_tag};q={q}")
        accept_lang_header = ", ".join(accept_lang_parts)
        await context.set_extra_http_headers({"Accept-Language": accept_lang_header})
        logger.debug(f"Accept-Language: {accept_lang_header}")

        # CDP-level webdriver evasion: Proxy on Navigator.prototype
        # This intercepts 'webdriver' in navigator → false, AND navigator.webdriver → undefined
        # Must run via CDP before any page content or detection scripts
        _webdriver_evasion_js = """
            // Complete webdriver evasion: DELETE the property entirely
            // System Chrome has configurable:true on prototype → deletable!
            // Playwright Chromium has non-configurable C++ level → fallback to value override
            try { delete navigator.webdriver; } catch(e) {}
            try {
                const proto = Object.getPrototypeOf(navigator);
                if (proto) {
                    const desc = Object.getOwnPropertyDescriptor(proto, 'webdriver');
                    if (desc && desc.configurable) delete proto.webdriver;
                }
            } catch(e) {}
            try {
                const pDesc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
                if (pDesc && pDesc.configurable) delete Navigator.prototype.webdriver;
            } catch(e) {}
            // If property still exists (Playwright Chromium fallback) - override value
            if ('webdriver' in navigator) {
                try {
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                        configurable: true,
                    });
                } catch(e) {}
            }
        """
        # ─── Inject stealth scripts ─────────────────────────────────────
        # INJECTION STRATEGY (March 2026):
        # Patchright's add_init_script causes navigation timeouts (verified broken).
        # CDP Page.addScriptToEvaluateOnNewDocument also causes timeouts.
        # Solution: TWO-LAYER injection via HTML route interception:
        #   Layer 1 (PRE-PAGE): _anti_cdp_route injects FULL stealth JS into <head>
        #           → runs BEFORE any page JS (anti-fraud can't see real fingerprint)
        #   Layer 2 (POST-PAGE): _patched_goto runs page.evaluate as BACKUP
        #           → catches SPA navigations, JS redirects, non-HTML pages
        all_stealth_scripts = [_webdriver_evasion_js, stealth_js]
        logger.debug(f"Stealth: GPU={ctx_gpu[1][:40]}..., platform from UA, hw={ctx_hw}, mem={ctx_mem}")

        combined_stealth = "\n".join(all_stealth_scripts)

        if _USING_PATCHRIGHT:
            # Store full stealth for both layers
            context._leomail_stealth_js = combined_stealth

            # ─── Layer 2: BACKUP post-navigation injection ─────────
            # Catches SPA navigations and JS redirects that bypass the route
            _orig_new_page = context.new_page

            async def _patched_new_page(*args, **kwargs):
                page = await _orig_new_page(*args, **kwargs)
                _orig_goto = page.goto

                async def _patched_goto(url, **kw):
                    response = await _orig_goto(url, **kw)
                    try:
                        # Re-apply stealth as BACKUP (Layer 1 already ran for HTML pages)
                        # This catches: about:blank, JS redirects, SPA navigations
                        if not _should_bypass_prepage_stealth(url):
                            await page.evaluate(context._leomail_stealth_js)
                    except Exception:
                        pass  # page may have navigated away
                    return response

                page.goto = _patched_goto
                return page

            context.new_page = _patched_new_page

            # ─── Layer 1: PRE-PAGE HTML route injection (CRITICAL) ─────────
            # Injects FULL stealth engine into <head> of HTML responses.
            # This runs BEFORE any page JavaScript, so anti-fraud scripts
            # (Arkose Labs, Microsoft Account Protection, Google reCAPTCHA)
            # see our PATCHED fingerprint, not the real one.
            #
            # Includes:
            # 1) CDP detection bypass (Error.prepareStackTrace trap)
            # 2) WebWorker CDP fix (Blob constructor intercept)
            # 3) Webdriver Proxy trap (hides 'webdriver' from 'in' operator)
            # 4) FULL 28-patch stealth engine (GPU, canvas, audio, etc.)
            #
            # The full stealth JS is stored as context._leomail_stealth_js
            # and embedded as <script> in every HTML response.

            # Build the pre-page script: CDP bypass + full stealth engine
            _pre_page_cdp_bypass = '''(function(){
/* CDP detection bypass (Error.prepareStackTrace trap) */
var _oL=console.log;
console.log=function(){var a=[];for(var i=0;i<arguments.length;i++){
if(arguments[i] instanceof Error){a.push(arguments[i].message||'')}
else{a.push(arguments[i])}}return _oL.apply(console,a)};
console.log.toString=function(){return'function log() { [native code] }'};
var OB=window.Blob;
var wp='var _oL=console.log;console.log=function(){var a=[];for(var i=0;i<arguments.length;i++){if(arguments[i] instanceof Error){a.push(arguments[i].message||"")}else{a.push(arguments[i])}}return _oL.apply(console,a)};';
window.Blob=function(p,o){if(o&&o.type&&o.type.indexOf("javascript")!==-1){
var np=[wp];for(var i=0;i<p.length;i++){np.push(p[i])}return new OB(np,o)}
return new OB(p,o)};window.Blob.prototype=OB.prototype;
window.Blob.toString=function(){return'function Blob() { [native code] }'};
})();'''

            # Escape the stealth JS for embedding in HTML <script> tag
            # No escaping needed — the JS is already valid, just wrap in <script>
            _full_pre_page_script = '<script>' + _pre_page_cdp_bypass + '\n' + combined_stealth + '</script>'

            async def _anti_cdp_route(route):
                try:
                    response = await route.fetch()
                    ct = response.headers.get("content-type", "")
                    request_url = route.request.url
                    if _should_bypass_prepage_stealth(request_url):
                        await route.fulfill(response=response)
                    elif "text/html" in ct:
                        body = await response.text()
                        if "<head>" in body:
                            body = body.replace("<head>", "<head>" + _full_pre_page_script, 1)
                        elif "<HEAD>" in body:
                            body = body.replace("<HEAD>", "<HEAD>" + _full_pre_page_script, 1)
                        elif "<html" in body.lower():
                            # Fallback: no <head> tag, inject after <html...>
                            import re as _html_re
                            body = _html_re.sub(
                                r'(<html[^>]*>)',
                                r'\1<head>' + _full_pre_page_script + '</head>',
                                body, count=1, flags=_html_re.IGNORECASE
                            )
                        await route.fulfill(response=response, body=body)
                    else:
                        # Non-HTML: pass through without interception
                        await route.fulfill(response=response)
                except Exception:
                    try:
                        await route.continue_()
                    except Exception:
                        pass

            await context.route("**/*", _anti_cdp_route)
        else:
            # Standard Playwright: use add_init_script (works normally)
            await context.add_init_script(script=combined_stealth)

        # Override language + Client Hints headers to match locale/UA
        # Extract Chrome version from UA for sec-ch-ua
        import re as _re
        _ch_match = _re.search(r'Chrome/(\d+)', ctx_ua)
        _ch_ver = _ch_match.group(1) if _ch_match else '140'
        _is_edge = 'Edg/' in ctx_ua
        if _is_edge:
            _edge_match = _re.search(r'Edg/(\d+)', ctx_ua)
            _edge_ver = _edge_match.group(1) if _edge_match else _ch_ver
            _sec_ch_ua = f'"Microsoft Edge";v="{_edge_ver}", "Chromium";v="{_ch_ver}", "Not_A Brand";v="24"'
        else:
            _sec_ch_ua = f'"Google Chrome";v="{_ch_ver}", "Chromium";v="{_ch_ver}", "Not_A Brand";v="24"'

        _ch_platform = '"Windows"' if 'Windows' in ctx_ua else ('"macOS"' if 'Mac' in ctx_ua else ('"Android"' if 'Android' in ctx_ua else '"Linux"'))
        _ch_mobile = '?1' if is_mobile else '?0'

        await context.set_extra_http_headers({
            "Accept-Language": f"{locale_str},{lang};q=0.9,en;q=0.8",
            "sec-ch-ua": _sec_ch_ua,
            "sec-ch-ua-mobile": _ch_mobile,
            "sec-ch-ua-platform": _ch_platform,
        })

        logger.debug(
            f"Context created: geo={country_code or 'random'}, "
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

        logger.info(f"Session saved: account {account_id} -> {session_path}")
        return session_path

    @staticmethod
    def save_fingerprint(account_id: int, data: dict) -> str:
        """Save fingerprint data (GPU, viewport, UA, seeds) for an account."""
        profile_dir = PROFILES_DIR / str(account_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        fp_path = str(profile_dir / "fingerprint.json")
        with open(fp_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Fingerprint saved: account {account_id} -> {fp_path}")
        return fp_path

    @staticmethod
    def load_fingerprint(account_id: int) -> dict | None:
        """Load saved fingerprint data for an account, or None if not saved."""
        fp_path = PROFILES_DIR / str(account_id) / "fingerprint.json"
        if not fp_path.exists():
            return None
        try:
            with open(fp_path) as f:
                data = json.load(f)
            logger.debug(f"Fingerprint loaded: account {account_id}")
            return data
        except Exception as e:
            logger.warning(f"Failed to load fingerprint for account {account_id}: {e}")
            return None

    async def load_session_context(
        self,
        account_id: int,
        proxy=None,
        geo: str = None,
    ) -> tuple[BrowserContext, str]:
        """Load a persistent session for an account. Returns (context, session_path)."""
        session_path = str(PROFILES_DIR / str(account_id) / "session.json")
        context = await self.create_context(
            proxy=proxy,
            geo=geo,
            session_path=session_path if os.path.exists(session_path) else None,
            account_id=account_id,
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
