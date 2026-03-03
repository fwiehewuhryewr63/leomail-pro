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

# ─── Mobile GPU Combos (Adreno, Mali, Apple - must match mobile devices!) ─────

MOBILE_GPU_ANDROID = [
    ("Qualcomm", "Adreno (TM) 730"),       # Snapdragon 8 Gen 1 (Pixel 7, Galaxy S22)
    ("Qualcomm", "Adreno (TM) 740"),       # Snapdragon 8 Gen 2 (Galaxy S23, Pixel 8)
    ("Qualcomm", "Adreno (TM) 750"),       # Snapdragon 8 Gen 3 (Galaxy S24)
    ("Qualcomm", "Adreno (TM) 660"),       # Snapdragon 778G (Nord CE 3)
    ("Qualcomm", "Adreno (TM) 650"),       # Snapdragon 865
    ("Qualcomm", "Adreno (TM) 642L"),      # Snapdragon 7 Gen 1
    ("ARM", "Mali-G715"),                    # Exynos 2300 (Galaxy S23 FE)
    ("ARM", "Mali-G710"),                    # Mediatek Dimensity 9000
    ("ARM", "Mali-G78"),                     # Exynos 2100 (Galaxy S21)
    ("ARM", "Mali-G77"),                     # Exynos 990
    ("Imagination Technologies", "PowerVR GE8320"),  # Budget devices
]

MOBILE_GPU_IOS = [
    ("Apple", "Apple GPU"),                  # All modern iPhones
    ("Apple", "ANGLE (Apple, ANGLE Metal Renderer: Apple A17 Pro GPU, Unspecified Version)"),
    ("Apple", "ANGLE (Apple, ANGLE Metal Renderer: Apple A16 GPU, Unspecified Version)"),
    ("Apple", "ANGLE (Apple, ANGLE Metal Renderer: Apple A15 GPU, Unspecified Version)"),

]


def _build_mobile_stealth_extra(platform: str = "android") -> str:
    """
    Additional stealth scripts specific to mobile device emulation.
    Adds sensors, touch events, screen orientation, realistic battery, etc.
    """
    battery_level = round(random.uniform(0.35, 0.95), 2)
    battery_charging = random.choice([True, False])
    charging_time = 0 if battery_charging else float('inf')
    discharge_time = float('inf') if battery_charging else random.randint(3600, 14400)

    screen_orientation = random.choice(["portrait-primary", "landscape-primary"])
    orientation_angle = 0 if screen_orientation == "portrait-primary" else 90

    conn_type = random.choice(["wifi", "cellular"])
    conn_effective = "4g" if conn_type == "cellular" else "4g"
    conn_rtt = random.choice([50, 75, 100, 150]) if conn_type == "cellular" else random.choice([25, 50, 75])
    conn_downlink = random.choice([5, 8, 10, 15]) if conn_type == "cellular" else random.choice([20, 50, 100])

    return f"""
    // ═══ MOBILE-SPECIFIC STEALTH ═══

    // M1. Realistic Battery API (not always full/charging)
    navigator.getBattery = () => Promise.resolve({{
        charging: {'true' if battery_charging else 'false'},
        chargingTime: {charging_time if charging_time != float('inf') else 'Infinity'},
        dischargingTime: {discharge_time if discharge_time != float('inf') else 'Infinity'},
        level: {battery_level},
        addEventListener: () => {{}}, removeEventListener: () => {{}}, dispatchEvent: () => true,
    }});

    // M2. No plugins on mobile Chrome
    Object.defineProperty(navigator, 'plugins', {{
        get: () => {{
            const p = [];
            p.length = 0;
            p.namedItem = () => null;
            p.refresh = () => {{}};
            return p;
        }}
    }});
    Object.defineProperty(navigator, 'mimeTypes', {{
        get: () => {{
            const m = [];
            m.length = 0;
            m.namedItem = () => null;
            return m;
        }}
    }});

    // M3. Screen Orientation API
    if (!screen.orientation || !screen.orientation.type) {{
        Object.defineProperty(screen, 'orientation', {{
            get: () => ({{
                type: '{screen_orientation}',
                angle: {orientation_angle},
                addEventListener: () => {{}},
                removeEventListener: () => {{}},
                dispatchEvent: () => true,
                lock: () => Promise.resolve(),
                unlock: () => {{}},
            }})
        }});
    }}

    // M4. DeviceMotionEvent & DeviceOrientationEvent (essential for mobile fingerprinting)
    if (typeof DeviceMotionEvent === 'undefined') {{
        window.DeviceMotionEvent = class DeviceMotionEvent extends Event {{
            constructor(type, init) {{ super(type, init); }}
        }};
    }}
    if (typeof DeviceOrientationEvent === 'undefined') {{
        window.DeviceOrientationEvent = class DeviceOrientationEvent extends Event {{
            constructor(type, init) {{ super(type, init); }}
        }};
    }}
    // Simulate periodic sensor data
    (function() {{
        let alpha = {random.randint(0, 359)}, beta = {random.randint(-5, 5)}, gamma = {random.randint(-3, 3)};
        setInterval(() => {{
            alpha = (alpha + (Math.random() * 0.1 - 0.05)) % 360;
            beta += Math.random() * 0.05 - 0.025;
            gamma += Math.random() * 0.05 - 0.025;
            try {{
                window.dispatchEvent(new DeviceOrientationEvent('deviceorientation', {{
                    alpha: alpha, beta: beta, gamma: gamma, absolute: false
                }}));
                window.dispatchEvent(new DeviceMotionEvent('devicemotion', {{
                    acceleration: {{ x: Math.random() * 0.02 - 0.01, y: 9.8 + Math.random() * 0.04 - 0.02, z: Math.random() * 0.02 - 0.01 }},
                    accelerationIncludingGravity: {{ x: 0, y: 9.8, z: 0 }},
                    rotationRate: {{ alpha: 0, beta: 0, gamma: 0 }},
                    interval: 16
                }}));
            }} catch(e) {{}}
        }}, 1000 + Math.random() * 500);
    }})();

    // M5. TouchEvent constructor (critical - Google checks this!)
    if (typeof TouchEvent === 'undefined') {{
        window.TouchEvent = class TouchEvent extends UIEvent {{
            constructor(type, init) {{ super(type, init); }}
        }};
    }}
    // Ensure maxTouchPoints is set for mobile
    Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => {random.choice([5, 10])} }});

    // M6. Connection API with realistic mobile values
    Object.defineProperty(navigator, 'connection', {{
        configurable: true,
        get: () => ({{
            effectiveType: '{conn_effective}',
            type: '{conn_type}',
            rtt: {conn_rtt},
            downlink: {conn_downlink},
            saveData: false,
            addEventListener: () => {{}}, removeEventListener: () => {{}},
        }})
    }});

    // M7. Vibrate API (mobile-only)
    if (!navigator.vibrate) {{
        navigator.vibrate = function(pattern) {{ return true; }};
    }}

    // M8. MediaDevices - mobile has front+back cameras
    if (navigator.mediaDevices) {{
        navigator.mediaDevices.enumerateDevices = async function() {{
            return [
                {{ deviceId: 'mic0', kind: 'audioinput', label: '', groupId: 'mic' }},
                {{ deviceId: 'speaker0', kind: 'audiooutput', label: '', groupId: 'speaker' }},
                {{ deviceId: 'cam_front', kind: 'videoinput', label: '', groupId: 'cam_front' }},
                {{ deviceId: 'cam_back', kind: 'videoinput', label: '', groupId: 'cam_back' }},
            ];
        }};
    }}

    // M9. Disable Notification permission (mobile Chrome rarely has it)
    const _origPQuery = window.navigator.permissions?.query;
    if (_origPQuery) {{
        window.navigator.permissions.query = (p) => {{
            if (p.name === 'notifications') return Promise.resolve({{ state: 'default' }});
            return _origPQuery.call(navigator.permissions, p);
        }};
    }}
    """  # noqa: E501


def _build_stealth_scripts(ua: str = "", gpu: tuple = None, hw_concurrency: int = 8,
                           device_memory: int = 8, langs: list = None,
                           timezone_id: str = "", viewport: dict = None,
                           device_scale: float = 1, is_mobile: bool = False,
                           chrome_version: str = "") -> str:
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
    // ═══ LEOMAIL ANTIDETECT ENGINE v2 ═══

    // 1. Hide webdriver flag (primary evasion is in CDP-level script, this is backup)
    (function() {{
        try {{
            // Delete from prototype and instance
            delete navigator.webdriver;
            const proto = Object.getPrototypeOf(navigator);
            if (proto) {{
                const desc = Object.getOwnPropertyDescriptor(proto, 'webdriver');
                if (desc && desc.configurable) delete proto.webdriver;
            }}
        }} catch(e) {{}}
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

    // 14. Intl.DateTimeFormat timezone consistency (prevents tz mismatch detection)
    {'// timezone_id was provided - override Intl to match' if timezone_id else '// no timezone_id - skip Intl override'}
    """ + (f"""
    (function() {{
        const _origDTF = Intl.DateTimeFormat;
        const _targetTZ = '{timezone_id}';
        Intl.DateTimeFormat = function(locales, options) {{
            if (!options) options = {{}};
            if (!options.timeZone) options.timeZone = _targetTZ;
            return new _origDTF(locales, options);
        }};
        Intl.DateTimeFormat.prototype = _origDTF.prototype;
        Intl.DateTimeFormat.supportedLocalesOf = _origDTF.supportedLocalesOf;
        Object.defineProperty(Intl.DateTimeFormat, 'name', {{ value: 'DateTimeFormat' }});
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

    // 16. Window dimensions consistency (headless detection vector)
    (function() {{
        const vw = window.innerWidth || {random.choice([1366, 1440, 1536, 1920])};
        const vh = window.innerHeight || {random.choice([728, 860, 824, 1040])};
        Object.defineProperty(window, 'outerWidth', {{ get: () => vw + {random.choice([0, 0, 14, 16])} }});
        Object.defineProperty(window, 'outerHeight', {{ get: () => vh + {random.choice([74, 79, 85, 111])} }});
        Object.defineProperty(window, 'screenX', {{ get: () => {random.choice([0, 0, 0, 50, 100])} }});
        Object.defineProperty(window, 'screenY', {{ get: () => {random.choice([0, 0, 0, 25, 50])} }});
    }})();

    // 17. Realistic chrome.csi and chrome.loadTimes (Google checks these!)
    if (window.chrome) {{
        window.chrome.csi = function() {{
            return {{
                onloadT: Date.now() - {random.randint(300, 2000)},
                startE: Date.now() - {random.randint(2000, 5000)},
                pageT: {random.randint(200, 1500)},
                tran: 15
            }};
        }};
        window.chrome.loadTimes = function() {{
            return {{
                commitLoadTime: Date.now() / 1000 - {random.uniform(0.5, 2.0):.3f},
                connectionInfo: 'h2',
                finishDocumentLoadTime: Date.now() / 1000 - {random.uniform(0.1, 0.5):.3f},
                finishLoadTime: Date.now() / 1000,
                firstPaintAfterLoadTime: 0,
                firstPaintTime: Date.now() / 1000 - {random.uniform(0.1, 0.3):.3f},
                navigationType: 'Other',
                npnNegotiatedProtocol: 'h2',
                requestTime: Date.now() / 1000 - {random.uniform(1.0, 3.0):.3f},
                startLoadTime: Date.now() / 1000 - {random.uniform(0.5, 2.0):.3f},
                wasAlternateProtocolAvailable: false,
                wasFetchedViaSpdy: true,
                wasNpnNegotiated: true,
            }};
        }};
    }}

    // 18. CDP Runtime leak fix (Playwright/Puppeteer detection via Error.stack)
    (function() {{
        const _origErr = Error;
        const _origStack = Object.getOwnPropertyDescriptor(Error.prototype, 'stack');
        if (_origStack && _origStack.get) {{
            Object.defineProperty(Error.prototype, 'stack', {{
                get: function() {{
                    const stack = _origStack.get.call(this);
                    if (stack && typeof stack === 'string') {{
                        return stack
                            .replace(/pptr:eval/g, '<anonymous>')
                            .replace(/__puppeteer_evaluation_script__/g, '<anonymous>')
                            .replace(/playwright_evaluation_script/g, '<anonymous>');
                    }}
                    return stack;
                }}
            }});
        }}
    }})();

    // 19. History length randomization (bot detection: fresh profiles always have length=1)
    Object.defineProperty(window.history, 'length', {{ get: () => {random.randint(2, 8)} }});

    // 20. PDF viewer consistency
    Object.defineProperty(navigator, 'pdfViewerEnabled', {{ get: () => true }});

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
                {'{{ brand: "' + ('Microsoft Edge' if is_edge else 'Google Chrome') + '", version: "' + ch_ver + '" }}'} ,
                {{ brand: 'Chromium', version: '{ch_ver}' }},
                {{ brand: 'Not_A Brand', version: '24' }},
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
    {'// mobile - skip desktop maxTouchPoints override' if is_mobile else "Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => 0 }});"}

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

    // 26. speechSynthesis.getVoices — return realistic voice list
    (function() {{
        if (window.speechSynthesis) {{
            const fakeVoices = [
                {{ voiceURI: 'Microsoft David - English (United States)', name: 'Microsoft David - English (United States)', lang: 'en-US', localService: true, default: true }},
                {{ voiceURI: 'Microsoft Zira - English (United States)', name: 'Microsoft Zira - English (United States)', lang: 'en-US', localService: true, default: false }},
                {{ voiceURI: 'Microsoft Mark - English (United States)', name: 'Microsoft Mark - English (United States)', lang: 'en-US', localService: true, default: false }},
                {{ voiceURI: 'Google US English', name: 'Google US English', lang: 'en-US', localService: false, default: false }},
                {{ voiceURI: 'Google UK English Female', name: 'Google UK English Female', lang: 'en-GB', localService: false, default: false }},
                {{ voiceURI: 'Google UK English Male', name: 'Google UK English Male', lang: 'en-GB', localService: false, default: false }},
            ];
            // Apply SpeechSynthesisVoice prototype if available
            const origGetVoices = speechSynthesis.getVoices;
            const realVoices = origGetVoices.call(speechSynthesis);
            const proto = (realVoices && realVoices[0]) ? Object.getPrototypeOf(realVoices[0]) : null;
            if (proto) fakeVoices.forEach(v => Object.setPrototypeOf(v, proto));

            speechSynthesis.getVoices = function() {{ return fakeVoices; }};
            // Also fire voiceschanged event on first access
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

    // 28. Date.getTimezoneOffset — MUST match timezone_id
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
            raise RuntimeError("Browser engine not installed. Run: pip install patchright && patchright install chromium")
        self.playwright = await async_playwright().start()
        if _USING_PATCHRIGHT:
            logger.info("Using Patchright engine (CDP leak-free)")
        else:
            logger.warning("Using standard Playwright (CDP leaks possible, install patchright for stealth)")

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
        # Kill any orphaned processes that survived
        try:
            from ..services.browser_leak_guard import kill_orphaned_browsers
            kill_orphaned_browsers(max_age_seconds=60)
        except Exception:
            pass
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

        # Select GPU, hw, memory based on device type
        if device_type.startswith("phone_android"):
            ctx_gpu = random.choice(MOBILE_GPU_ANDROID)
            ctx_hw = random.choice([4, 6, 8])
            ctx_mem = random.choice([2, 4, 6, 8])
        elif device_type.startswith("phone_ios"):
            ctx_gpu = random.choice(MOBILE_GPU_IOS)
            ctx_hw = random.choice([4, 6])
            ctx_mem = random.choice([3, 4, 6])
        else:
            # Desktop — pick GPU pool matching OS in user-agent (D3D11 is Windows-only!)
            if "Macintosh" in ctx_ua or "Mac OS" in ctx_ua:
                ctx_gpu = random.choice(GPU_COMBOS_MAC)
            elif "Linux" in ctx_ua:
                ctx_gpu = random.choice(GPU_COMBOS_LINUX)
            else:
                ctx_gpu = random.choice(GPU_COMBOS)
            ctx_hw = random.choice([4, 8, 12, 16])
            ctx_mem = random.choice([4, 8, 16])

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
        )

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
                        get: () => false,
                        configurable: false,
                    });
                } catch(e) {}
            }
        """
        # ─── Inject stealth scripts ─────────────────────────────────────
        # Patchright's add_init_script is broken (causes navigation timeouts)
        # and CDP Page.addScriptToEvaluateOnNewDocument triggers isAutomatedWithCDP.
        # Solution: monkey-patch page.goto to auto-inject via page.evaluate after navigation.
        # Patchright handles navigator.webdriver natively (no script needed).
        all_stealth_scripts = [_webdriver_evasion_js, stealth_js]

        # Add mobile-specific stealth if emulating phone
        if is_mobile:
            mobile_platform = "ios" if device_type.startswith("phone_ios") else "android"
            mobile_stealth = _build_mobile_stealth_extra(platform=mobile_platform)
            all_stealth_scripts.append(mobile_stealth)
            logger.debug(f"Mobile stealth: GPU={ctx_gpu[1][:40]}..., sensors+touch+battery")
        else:
            logger.debug(f"Stealth: GPU={ctx_gpu[1][:40]}..., platform from UA, hw={ctx_hw}, mem={ctx_mem}")

        combined_stealth = "\n".join(all_stealth_scripts)

        if _USING_PATCHRIGHT:
            # Patchright: inject via page.evaluate after each navigation.
            # Store script on context, monkey-patch new_page to auto-hook page.goto.
            context._leomail_stealth_js = combined_stealth

            _orig_new_page = context.new_page

            async def _patched_new_page(*args, **kwargs):
                page = await _orig_new_page(*args, **kwargs)
                _orig_goto = page.goto

                async def _patched_goto(url, **kw):
                    response = await _orig_goto(url, **kw)
                    try:
                        await page.evaluate(context._leomail_stealth_js)
                    except Exception:
                        pass  # page may have navigated away
                    return response

                page.goto = _patched_goto
                return page

            context.new_page = _patched_new_page

            # ─── Anti-CDP detection via HTML route injection ─────────
            # Bypasses Error.prepareStackTrace-based CDP detection
            # (used by deviceandbrowserinfo.com and similar).
            # Injects a <script> into HTML responses that:
            # 1) Overrides console.log to stringify Error objects
            # 2) Intercepts Blob constructor to fix WebWorker detection
            _anti_cdp_script = '''<script>(function(){
/* === 1. CDP detection bypass (Error.prepareStackTrace trap) === */
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

/* === 2. Webdriver: Proxy trap on Navigator.prototype to hide 'webdriver' completely === */
(function(){
try{delete Navigator.prototype.webdriver}catch(e){}
try{var p=Object.getPrototypeOf(navigator);if(p&&p.hasOwnProperty('webdriver'))delete p.webdriver}catch(e){}
try{delete navigator.webdriver}catch(e){}
/* Proxy trap: 'webdriver' in navigator → false, navigator.webdriver → undefined */
if('webdriver' in navigator){
try{
var origProto=Object.getPrototypeOf(navigator);
var proxyProto=new Proxy(origProto,{
has:function(t,k){if(k==='webdriver')return false;return k in t},
get:function(t,k,r){if(k==='webdriver')return undefined;var v=Reflect.get(t,k,r);return typeof v==='function'?v.bind(navigator):v},
getOwnPropertyDescriptor:function(t,k){if(k==='webdriver')return undefined;return Object.getOwnPropertyDescriptor(t,k)}
});
Object.setPrototypeOf(navigator,proxyProto);
}catch(e){
try{Object.defineProperty(navigator,'webdriver',{get:function(){return undefined},configurable:true})}catch(e2){}
}
}
})();

/* === 3. Notification.permission → 'default' === */
try{Object.defineProperty(Notification,'permission',{
get:function(){return'default'},configurable:true})}catch(e){}

/* === 4. speechSynthesis.getVoices() → return voices (async-safe) === */
try{if(window.speechSynthesis){var _origGV=speechSynthesis.getVoices.bind(speechSynthesis);
var _cachedVoices=null;
speechSynthesis.getVoices=function(){var v=_origGV();if(v&&v.length>0){_cachedVoices=v;return v}
if(_cachedVoices&&_cachedVoices.length>0)return _cachedVoices;
return[{default:true,lang:'en-US',localService:true,name:'Microsoft David - English (United States)',
voiceURI:'Microsoft David - English (United States)'},
{default:false,lang:'en-US',localService:true,name:'Microsoft Zira - English (United States)',
voiceURI:'Microsoft Zira - English (United States)'},
{default:false,lang:'en-GB',localService:true,name:'Microsoft Hazel - English (United Kingdom)',
voiceURI:'Microsoft Hazel - English (United Kingdom)'}];
};
speechSynthesis.getVoices.toString=function(){return'function getVoices() { [native code] }'};
setTimeout(function(){_cachedVoices=_origGV()},200)}}catch(e){}

/* === 5. chrome.runtime basic emulation (runs before page JS) === */
try{if(!window.chrome)window.chrome={};
if(!window.chrome.app)window.chrome.app={isInstalled:false,InstallState:{DISABLED:'disabled',INSTALLED:'installed',NOT_INSTALLED:'not_installed'},RunningState:{CANNOT_RUN:'cannot_run',READY_TO_RUN:'ready_to_run',RUNNING:'running'},getDetails:function(){return null},getIsInstalled:function(){return false}};
if(!window.chrome.csi)window.chrome.csi=function(){return{onloadT:Date.now(),startE:Date.now(),pageT:200,tran:15}};
if(!window.chrome.loadTimes)window.chrome.loadTimes=function(){return{commitLoadTime:Date.now()/1000,connectionInfo:'h2',finishDocumentLoadTime:Date.now()/1000,finishLoadTime:Date.now()/1000,firstPaintAfterLoadTime:0,firstPaintTime:Date.now()/1000,navigationType:'Other',npnNegotiatedProtocol:'h2',requestTime:Date.now()/1000,startLoadTime:Date.now()/1000,wasAlternateProtocolAvailable:false,wasFetchedViaSpdy:true,wasNpnNegotiated:true}};
}catch(e){}
})();</script>'''

            async def _anti_cdp_route(route):
                try:
                    response = await route.fetch()
                    ct = response.headers.get("content-type", "")
                    if "text/html" in ct:
                        body = await response.text()
                        if "<head>" in body:
                            body = body.replace("<head>", "<head>" + _anti_cdp_script, 1)
                        elif "<HEAD>" in body:
                            body = body.replace("<HEAD>", "<HEAD>" + _anti_cdp_script, 1)
                        await route.fulfill(response=response, body=body)
                    else:
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

        logger.info(f"Session saved: account {account_id} -> {session_path}")
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
