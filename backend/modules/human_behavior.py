"""
Leomail v4 - Human Behavior Engine v2
Realistic human-like interactions for browser automation.
Every function is designed to pass modern anti-bot behavioral analysis.

Key techniques:
- Cubic Bezier mouse curves with ease-out (not linear interpolation)
- Typo simulation with QWERTY-adjacent key errors + backspace correction
- Context-aware typing speed (name=fast, password=slow, code=careful)
- Tab/click navigation mix (real humans alternate)
- Hover dwell before clicks (reading button text)
- GEO-aware warmup URL pool (50+ sites)
- Smart scrolling (momentum, variable depth, Page Down mix)
- Idle micro-movements between actions (hand breathing on mouse)
"""
import asyncio
import random
import math
from loguru import logger


# ═══════════════════════════════════════════════════════════════════════════════
# QWERTY Adjacent Key Map - for realistic typo generation
# ═══════════════════════════════════════════════════════════════════════════════
QWERTY_ADJACENT = {
    'q': 'wa', 'w': 'qeas', 'e': 'wrds', 'r': 'etdf', 't': 'ryfg',
    'y': 'tugh', 'u': 'yijh', 'i': 'uojk', 'o': 'iplk', 'p': 'ol',
    'a': 'qwsz', 's': 'awedxz', 'd': 'serfcx', 'f': 'drtgvc',
    'g': 'ftyhbv', 'h': 'gyujnb', 'j': 'huikmn', 'k': 'jiolm',
    'l': 'kop', 'z': 'asx', 'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb',
    'b': 'vghn', 'n': 'bhjm', 'm': 'njk',
    '1': '2q', '2': '13qw', '3': '24we', '4': '35er', '5': '46rt',
    '6': '57ty', '7': '68yu', '8': '79ui', '9': '80io', '0': '9p',
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. BEZIER MOUSE CURVES
# ═══════════════════════════════════════════════════════════════════════════════

def _bezier_point(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """Cubic bezier interpolation: P0->P1->P2->P3 at parameter t ∈ [0,1]."""
    u = 1 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3


def _ease_out_quad(t: float) -> float:
    """Ease-out: fast start, slow finish (human deceleration near target)."""
    return 1 - (1 - t) ** 2


def _ease_out_cubic(t: float) -> float:
    """Even more pronounced ease-out."""
    return 1 - (1 - t) ** 3


def _generate_bezier_path(start_x, start_y, end_x, end_y, steps=None):
    """
    Generate a natural mouse path from start to end using cubic Bezier curve.
    Returns list of (x, y) points with ease-out timing.
    """
    if steps is None:
        # More steps for longer distances
        dist = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        steps = max(12, min(35, int(dist / 15)))

    # Control points: create a natural arc (not straight line)
    # P1: 25-40% of the way, offset perpendicular to the line
    dx = end_x - start_x
    dy = end_y - start_y
    dist = max(1, math.sqrt(dx*dx + dy*dy))

    # Perpendicular offset (creates the arc)
    perp_x = -dy / dist
    perp_y = dx / dist
    arc_strength = dist * random.uniform(0.05, 0.25) * random.choice([-1, 1])

    cp1_x = start_x + dx * random.uniform(0.2, 0.4) + perp_x * arc_strength
    cp1_y = start_y + dy * random.uniform(0.2, 0.4) + perp_y * arc_strength
    cp2_x = start_x + dx * random.uniform(0.6, 0.8) + perp_x * arc_strength * 0.3
    cp2_y = start_y + dy * random.uniform(0.6, 0.8) + perp_y * arc_strength * 0.3

    points = []
    for i in range(steps + 1):
        # Apply ease-out to parameter (slow down near target)
        t_raw = i / steps
        t = _ease_out_quad(t_raw)

        x = _bezier_point(t, start_x, cp1_x, cp2_x, end_x)
        y = _bezier_point(t, start_y, cp1_y, cp2_y, end_y)

        # Micro-jitter (hand tremor: ±1-2px, decreasing near endpoints)
        jitter_scale = min(t_raw, 1 - t_raw) * 4  # Max jitter in middle, zero at edges
        jitter_x = random.gauss(0, 1.2) * jitter_scale
        jitter_y = random.gauss(0, 0.8) * jitter_scale

        points.append((int(x + jitter_x), int(y + jitter_y)))

    return points


async def human_delay(min_s: float = 0.5, max_s: float = 1.5):
    """Random delay with slight human-like variance."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def random_mouse_move(page, steps: int = None):
    """
    Move mouse to random positions using Bezier curves.
    Each movement follows a natural arc with ease-out deceleration.
    """
    if steps is None:
        steps = random.randint(2, 4)

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    w, h = viewport["width"], viewport["height"]

    # Get current mouse position (approximate from center if unknown)
    current_x = random.randint(int(w * 0.3), int(w * 0.7))
    current_y = random.randint(int(h * 0.3), int(h * 0.6))

    for _ in range(steps):
        # Random target (avoid extreme edges)
        target_x = random.randint(int(w * 0.05), int(w * 0.95))
        target_y = random.randint(int(h * 0.1), int(h * 0.85))

        path = _generate_bezier_path(current_x, current_y, target_x, target_y)
        for x, y in path:
            x = max(0, min(w - 1, x))
            y = max(0, min(h - 1, y))
            try:
                await page.mouse.move(x, y)
                # Variable speed: fast in middle, slow at start/end
                await asyncio.sleep(random.uniform(0.008, 0.025))
            except Exception:
                pass

        current_x, current_y = target_x, target_y

        # Small pause after reaching destination (eyes catching up)
        await asyncio.sleep(random.uniform(0.08, 0.25))


async def _move_mouse_to(page, target_x, target_y, from_x=None, from_y=None):
    """Move mouse to a specific point using Bezier curve."""
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    if from_x is None:
        from_x = random.randint(100, viewport["width"] - 100)
    if from_y is None:
        from_y = random.randint(100, viewport["height"] - 100)

    path = _generate_bezier_path(from_x, from_y, target_x, target_y)
    for x, y in path:
        x = max(0, min(viewport["width"] - 1, x))
        y = max(0, min(viewport["height"] - 1, y))
        try:
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.008, 0.022))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SMART SCROLLING
# ═══════════════════════════════════════════════════════════════════════════════

async def random_scroll(page, direction: str = "random"):
    """
    Scroll with variable physics:
    - Small smooth scrolls (reading)
    - Occasional fast momentum scrolls
    - Rare Page Down press
    """
    if direction == "random":
        direction = random.choice(["down", "up", "down", "down"])  # bias down

    # Choose scroll behavior
    behavior = random.choices(
        ["smooth_small", "smooth_medium", "momentum", "page_key"],
        weights=[40, 30, 20, 10],
        k=1
    )[0]

    if behavior == "page_key":
        # Page Down / Page Up (some humans use keyboard)
        key = "PageDown" if direction == "down" else "PageUp"
        try:
            await page.keyboard.press(key)
        except Exception:
            pass
        await asyncio.sleep(random.uniform(0.3, 0.6))
        return

    if behavior == "momentum":
        # Fast momentum scroll (quick flick)
        scroll_amount = random.randint(400, 900)
        if direction == "up":
            scroll_amount = -scroll_amount
        try:
            await page.mouse.wheel(0, scroll_amount)
        except Exception:
            pass
        await asyncio.sleep(random.uniform(0.3, 0.7))
        return

    # Smooth scrolling in chunks
    scroll_total = random.randint(80, 350) if behavior == "smooth_small" else random.randint(200, 500)
    if direction == "up":
        scroll_total = -scroll_total

    chunks = random.randint(3, 7)
    per_chunk = scroll_total / chunks

    for i in range(chunks):
        # Variable chunk size (ease-out: fast start, slow finish)
        factor = 1.0 - (i / chunks) * 0.5
        chunk = per_chunk * factor + random.uniform(-10, 10)
        try:
            await page.mouse.wheel(0, chunk)
            await asyncio.sleep(random.uniform(0.03, 0.1))
        except Exception:
            pass

    await asyncio.sleep(random.uniform(0.15, 0.4))


# ═══════════════════════════════════════════════════════════════════════════════
# 3. HOVER + CLICK (reads button text before clicking)
# ═══════════════════════════════════════════════════════════════════════════════

async def hover_then_click(page, selector: str, timeout: int = 5000):
    """
    Human-like click: move to element, hover (read text), then click.
    More realistic than instant click - humans read before acting.
    """
    try:
        el = page.locator(selector).first
        box = await el.bounding_box()
        if not box:
            await el.click(timeout=timeout)
            return

        center_x = box["x"] + box["width"] / 2
        center_y = box["y"] + box["height"] / 2

        # Slight offset from center (humans don't hit dead center)
        offset_x = random.gauss(0, box["width"] * 0.12)
        offset_y = random.gauss(0, box["height"] * 0.12)
        target_x = center_x + offset_x
        target_y = center_y + offset_y

        # Clamp within element bounds
        target_x = max(box["x"] + 3, min(box["x"] + box["width"] - 3, target_x))
        target_y = max(box["y"] + 2, min(box["y"] + box["height"] - 2, target_y))

        # Move to element with Bezier curve
        await _move_mouse_to(page, target_x, target_y)

        # HOVER DWELL (200-600ms) - reading button text
        await asyncio.sleep(random.uniform(0.2, 0.6))

        # Click
        await page.mouse.click(target_x, target_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))

    except Exception:
        try:
            await page.locator(selector).first.click(timeout=timeout)
        except Exception:
            pass


async def human_click(page, selector: str, timeout: int = 5000):
    """
    Click with human-like approach:
    1. Move mouse to element via Bezier curve
    2. Hover dwell (100-400ms)
    3. Click with offset from center
    """
    try:
        el = page.locator(selector).first
        box = await el.bounding_box()
        if not box:
            await el.click(timeout=timeout)
            return

        center_x = box["x"] + box["width"] / 2
        center_y = box["y"] + box["height"] / 2

        # Human offset - Gaussian distribution (most clicks near center)
        offset_x = random.gauss(0, box["width"] * 0.15)
        offset_y = random.gauss(0, box["height"] * 0.15)
        target_x = center_x + offset_x
        target_y = center_y + offset_y

        # Clamp
        target_x = max(box["x"] + 2, min(box["x"] + box["width"] - 2, target_x))
        target_y = max(box["y"] + 2, min(box["y"] + box["height"] - 2, target_y))

        # Bezier approach
        await _move_mouse_to(page, target_x, target_y)

        # Pre-click pause (shorter than hover_then_click)
        await asyncio.sleep(random.uniform(0.05, 0.2))

        # Click
        await page.mouse.click(target_x, target_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))

    except Exception:
        try:
            await page.locator(selector).first.click(timeout=timeout)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TYPING WITH TYPOS + CONTEXT-AWARE SPEED
# ═══════════════════════════════════════════════════════════════════════════════

# Typing speed profiles (ms per keystroke)
TYPING_PROFILES = {
    "name":     {"base_min": 65, "base_max": 130, "think_chance": 0.05},
    "email":    {"base_min": 75, "base_max": 150, "think_chance": 0.09},
    "username": {"base_min": 80, "base_max": 160, "think_chance": 0.12},
    "password": {"base_min": 85, "base_max": 170, "think_chance": 0.08},
    "phone":    {"base_min": 60, "base_max": 115, "think_chance": 0.06},
    "code":     {"base_min": 95, "base_max": 185, "think_chance": 0.14},
    "search":   {"base_min": 65, "base_max": 130, "think_chance": 0.10},
    "default":  {"base_min": 70, "base_max": 140, "think_chance": 0.09},
}


def _get_adjacent_key(char: str) -> str:
    """Get a random adjacent key on QWERTY layout for typo simulation."""
    lower = char.lower()
    if lower in QWERTY_ADJACENT:
        adj = random.choice(QWERTY_ADJACENT[lower])
        return adj.upper() if char.isupper() else adj
    return char


async def human_type(page, selector: str, text: str, clear: bool = True,
                     field_type: str = "default"):
    """
    Type text with human-like behavior:
    - Context-aware speed (name=fast, password=slow)
    - Occasional typos + backspace correction (5-8% error rate)
    - Thinking pauses before special characters (@, digits)
    - Variable rhythm (not metronomic)
    """
    el = page.locator(selector).first

    # Click the field first (with Bezier approach)
    try:
        box = await el.bounding_box()
        if box:
            cx = box["x"] + box["width"] / 2 + random.uniform(-10, 10)
            cy = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
            await _move_mouse_to(page, cx, cy)
            await asyncio.sleep(random.uniform(0.05, 0.15))
            await page.mouse.click(cx, cy)
            await asyncio.sleep(random.uniform(0.1, 0.3))
    except Exception:
        await el.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))

    if clear:
        await el.fill("")
        await asyncio.sleep(random.uniform(0.08, 0.2))

    # Get typing profile
    profile = TYPING_PROFILES.get(field_type, TYPING_PROFILES["default"])
    base_min = profile["base_min"]
    base_max = profile["base_max"]
    think_chance = profile["think_chance"]

    # Typos DISABLED — risk of real errors outweighs anti-bot benefit
    # (fingerprint/timing/behavior are much more effective)
    typo_rate = 0.0

    i = 0
    while i < len(text):
        char = text[i]

        # Thinking pause before special characters
        if char in "@._-!#$%&" and random.random() < 0.4:
            await asyncio.sleep(random.uniform(0.3, 0.8))
        elif char.isdigit() and i > 0 and text[i-1].isalpha() and random.random() < 0.3:
            # Pause at alpha->digit transition (switching mental mode)
            await asyncio.sleep(random.uniform(0.2, 0.5))

        # Random thinking pause
        if random.random() < think_chance:
            await asyncio.sleep(random.uniform(0.3, 0.8))

        # TYPO SIMULATION
        if random.random() < typo_rate and len(text) > 3:
            typo_type = random.choices(
                ["adjacent", "double", "transpose", "skip"],
                weights=[40, 25, 20, 15],
                k=1
            )[0]

            if typo_type == "adjacent":
                # Type wrong adjacent key, notice, backspace, retype correct
                wrong_char = _get_adjacent_key(char)
                await el.type(wrong_char, delay=random.randint(base_min, base_max))
                await asyncio.sleep(random.uniform(0.15, 0.5))  # Notice mistake
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.08, 0.2))
                await el.type(char, delay=random.randint(base_min, base_max))

            elif typo_type == "double":
                # Double press: 'passsword' -> backspace -> continue
                await el.type(char, delay=random.randint(base_min, base_max))
                await el.type(char, delay=random.randint(20, 50))  # Fast double
                await asyncio.sleep(random.uniform(0.15, 0.4))
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.15))

            elif typo_type == "transpose" and i + 1 < len(text):
                # Type next char first, then backspace both and retype correctly
                next_char = text[i + 1]
                await el.type(next_char, delay=random.randint(base_min, base_max))
                await el.type(char, delay=random.randint(base_min, base_max))
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await page.keyboard.press("Backspace")
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.1, 0.25))
                await el.type(char, delay=random.randint(base_min, base_max))
                await el.type(next_char, delay=random.randint(base_min, base_max))
                i += 2  # Skip next char (already typed)
                continue

            elif typo_type == "skip":
                # Skip this char, type next, notice, go back
                if i + 1 < len(text):
                    await el.type(text[i + 1], delay=random.randint(base_min, base_max))
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(random.uniform(0.08, 0.15))
                    await el.type(char, delay=random.randint(base_min, base_max))
                    await el.type(text[i + 1], delay=random.randint(base_min, base_max))
                    i += 2
                    continue
                else:
                    await el.type(char, delay=random.randint(base_min, base_max))
        else:
            # Normal typing with variable speed
            delay = random.randint(base_min, base_max)
            # Burst typing: sometimes 2-3 chars come fast (muscle memory)
            if random.random() < 0.15 and i + 2 < len(text):
                # Fast burst for 2-3 chars
                for j in range(random.randint(2, 3)):
                    if i + j < len(text):
                        await el.type(text[i + j], delay=random.randint(25, 50))
                i += j + 1
                continue
            else:
                await el.type(char, delay=delay)

        i += 1

    await asyncio.sleep(random.uniform(0.15, 0.4))


# ═══════════════════════════════════════════════════════════════════════════════
# 5. BETWEEN-STEPS (TAB/CLICK MIX)
# ═══════════════════════════════════════════════════════════════════════════════

async def between_steps(page):
    """
    Natural behavior between form fields.
    Mix of: mouse move, Tab key, scroll, micro-pause.
    """
    action = random.choices(
        ["mouse_move", "tab", "mouse_and_scroll", "just_pause", "idle"],
        weights=[35, 25, 15, 15, 10],
        k=1
    )[0]

    if action == "tab":
        # Tab to next field (common for keyboard users)
        await page.keyboard.press("Tab")
        await asyncio.sleep(random.uniform(0.2, 0.6))

    elif action == "mouse_move":
        # Short mouse movement (looking around)
        await random_mouse_move(page, steps=random.randint(1, 2))
        await asyncio.sleep(random.uniform(0.2, 0.8))

    elif action == "mouse_and_scroll":
        # Mouse move + small scroll
        await random_mouse_move(page, steps=1)
        await random_scroll(page, "down")
        await asyncio.sleep(random.uniform(0.3, 0.8))

    elif action == "idle":
        # Micro idle behavior
        await idle_behavior(page, duration_seconds=random.uniform(0.5, 1.5))

    else:
        # Just pause (thinking)
        await asyncio.sleep(random.uniform(0.3, 1.2))


# ═══════════════════════════════════════════════════════════════════════════════
# 6. IDLE BEHAVIOR (micro-movements)
# ═══════════════════════════════════════════════════════════════════════════════

async def idle_behavior(page, duration_seconds: float = None):
    """
    Simulate human 'idle' - subtle mouse jitters, occasional micro-scroll.
    Real humans don't freeze between actions; their hand drifts on the mouse.
    """
    if duration_seconds is None:
        duration_seconds = random.uniform(0.5, 2.0)

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    w, h = viewport["width"], viewport["height"]
    elapsed = 0

    while elapsed < duration_seconds:
        # Tiny mouse drift (±5-15px "hand breathing")
        drift_x = random.gauss(0, 6)
        drift_y = random.gauss(0, 4)
        cx = max(5, min(w - 5, int(w / 2 + drift_x)))
        cy = max(5, min(h - 5, int(h / 2 + drift_y)))

        try:
            await page.mouse.move(cx, cy)
        except Exception:
            pass

        pause = random.uniform(0.15, 0.4)
        await asyncio.sleep(pause)
        elapsed += pause

        # Rare micro-scroll (3% chance per cycle)
        if random.random() < 0.03:
            try:
                await page.mouse.wheel(0, random.randint(-30, 30))
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# 7. WARMUP BROWSING (GEO-aware, 50+ URLs)
# ═══════════════════════════════════════════════════════════════════════════════

# URL pool organized by category (ensures variety)
WARMUP_SITES_GLOBAL = [
    # === News ===
    ("https://www.bbc.com", "BBC"), ("https://www.cnn.com", "CNN"),
    ("https://www.reuters.com", "Reuters"), ("https://www.nytimes.com", "NYTimes"),
    ("https://news.ycombinator.com", "HackerNews"), ("https://www.theguardian.com", "Guardian"),
    ("https://www.aljazeera.com", "AlJazeera"), ("https://apnews.com", "APNews"),
    # === Shopping ===
    ("https://www.amazon.com", "Amazon"), ("https://www.ebay.com", "eBay"),
    ("https://www.etsy.com", "Etsy"), ("https://www.walmart.com", "Walmart"),
    ("https://www.target.com", "Target"),
    # === Entertainment ===
    ("https://www.youtube.com", "YouTube"), ("https://www.imdb.com", "IMDb"),
    ("https://www.rottentomatoes.com", "RottenTomatoes"), ("https://www.spotify.com", "Spotify"),
    # === Social / Forums ===
    ("https://www.reddit.com", "Reddit"), ("https://www.quora.com", "Quora"),
    ("https://medium.com", "Medium"),
    # === Tech ===
    ("https://stackoverflow.com", "StackOverflow"), ("https://github.com", "GitHub"),
    ("https://www.producthunt.com", "ProductHunt"), ("https://techcrunch.com", "TechCrunch"),
    ("https://arstechnica.com", "ArsTechnica"),
    # === Reference ===
    ("https://www.wikipedia.org", "Wikipedia"), ("https://www.britannica.com", "Britannica"),
    # === Utility ===
    ("https://www.weather.com", "Weather"), ("https://www.timeanddate.com", "TimeAndDate"),
    ("https://www.speedtest.net", "Speedtest"),
    # === Lifestyle ===
    ("https://www.allrecipes.com", "AllRecipes"), ("https://www.webmd.com", "WebMD"),
    ("https://www.healthline.com", "Healthline"),
]

# GEO-specific sites (visited when proxy matches region)
WARMUP_SITES_GEO = {
    "US": [("https://www.usatoday.com", "USAToday"), ("https://www.espn.com", "ESPN"), ("https://www.craigslist.org", "Craigslist")],
    "GB": [("https://www.bbc.co.uk", "BBCuk"), ("https://www.dailymail.co.uk", "DailyMail"), ("https://www.sky.com", "Sky")],
    "DE": [("https://www.spiegel.de", "Spiegel"), ("https://www.zeit.de", "Zeit"), ("https://www.heise.de", "Heise")],
    "FR": [("https://www.lemonde.fr", "LeMonde"), ("https://www.lefigaro.fr", "LeFigaro")],
    "BR": [("https://www.globo.com", "Globo"), ("https://www.uol.com.br", "UOL")],
    "RU": [("https://www.rbc.ru", "RBC"), ("https://yandex.ru", "Yandex")],
    "IN": [("https://www.ndtv.com", "NDTV"), ("https://timesofindia.indiatimes.com", "TOI")],
    "JP": [("https://www.yahoo.co.jp", "YahooJP"), ("https://www.nikkei.com", "Nikkei")],
    "CA": [("https://www.cbc.ca", "CBC"), ("https://www.theglobeandmail.com", "GlobeMail")],
    "AU": [("https://www.abc.net.au", "ABC_AU"), ("https://www.smh.com.au", "SMH")],
    "ES": [("https://www.elpais.com", "ElPais"), ("https://www.marca.com", "Marca")],
    "IT": [("https://www.corriere.it", "Corriere"), ("https://www.repubblica.it", "Repubblica")],
    "NL": [("https://www.nu.nl", "NuNL"), ("https://www.telegraaf.nl", "Telegraaf")],
    "PL": [("https://www.wp.pl", "WP"), ("https://www.onet.pl", "Onet")],
    "TR": [("https://www.hurriyet.com.tr", "Hurriyet"), ("https://www.sabah.com.tr", "Sabah")],
}

# Search queries (diverse, natural)
SEARCH_QUERIES = [
    "best restaurants near me", "weather today", "latest news",
    "how to cook pasta", "movie recommendations 2026",
    "travel deals europe", "python tutorial", "healthy recipes",
    "best laptops 2026", "football scores today",
    "new music releases", "diy home projects",
    "book recommendations", "coffee shops nearby",
    "workout routines at home", "best hiking trails",
    "how to invest in stocks", "remote jobs 2026",
    "best streaming services", "online courses free",
    "quick breakfast ideas", "budget travel tips",
    "photography tips beginners", "home office setup",
    "electric cars comparison", "best podcasts 2026",
    "learn guitar online", "meditation for beginners",
    "sustainable living tips", "best running shoes",
]

# GEO-specific search queries
SEARCH_QUERIES_GEO = {
    "DE": ["wetter heute", "nachrichten", "rezepte einfach", "beste filme 2026"],
    "FR": ["météo aujourd'hui", "actualités", "recettes faciles", "meilleurs films 2026"],
    "BR": ["clima hoje", "notícias", "receitas fáceis", "melhores filmes 2026"],
    "ES": ["tiempo hoy", "noticias", "recetas fáciles", "mejores películas 2026"],
    "IT": ["meteo oggi", "notizie", "ricette facili", "migliori film 2026"],
    "RU": ["weather today", "news", "recipes", "best movies 2026"],
    "JP": ["天気 今日", "ニュース", "簡単レシピ"],
}


async def warmup_browsing(page, duration_seconds: int = None, geo: str = None):
    """
    Browse popular sites before registration.
    Warms up browser fingerprint with GEO-aware site selection.
    Visits 3-6 sites, performs Google searches, reads content.
    """
    if duration_seconds is None:
        duration_seconds = random.randint(35, 70)

    logger.debug(f"Warmup browsing for ~{duration_seconds}s (geo={geo or 'global'})")

    # Build site pool: global + GEO-specific
    sites = list(WARMUP_SITES_GLOBAL)
    if geo and geo.upper() in WARMUP_SITES_GEO:
        sites.extend(WARMUP_SITES_GEO[geo.upper()])

    # Build query pool: global + GEO-specific
    queries = list(SEARCH_QUERIES)
    if geo and geo.upper() in SEARCH_QUERIES_GEO:
        queries.extend(SEARCH_QUERIES_GEO[geo.upper()])

    start = asyncio.get_event_loop().time()
    visited = 0
    max_visits = random.randint(3, 6)

    # Always start with Google (most natural entry point)
    try:
        await page.goto("https://www.google.com", wait_until="load", timeout=25000)
        await human_delay(2, 5)
        await random_mouse_move(page, steps=random.randint(2, 3))

        # Google search — handle autocomplete dropdown interception
        query = random.choice(queries)
        search_input = page.locator('textarea[name="q"], input[name="q"]')
        if await search_input.count() > 0:
            # Dismiss any consent/autocomplete overlays first
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(random.uniform(0.2, 0.5))
            except Exception:
                pass
            # Click search input with force to bypass overlay
            try:
                await search_input.first.click(force=True)
            except Exception:
                try:
                    await search_input.first.focus()
                except Exception:
                    pass
            await human_delay(0.5, 1.5)
            # Type search query with realistic speed
            for char in query:
                await page.keyboard.type(char, delay=random.randint(40, 100))
            await human_delay(1.0, 2.5)
            # Dismiss autocomplete suggestions before hitting Enter
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(random.uniform(0.1, 0.3))
            except Exception:
                pass
            await page.keyboard.press("Enter")
            await human_delay(3, 7)

            # Read search results
            await random_scroll(page, "down")
            await human_delay(2, 4)
            await random_mouse_move(page, steps=random.randint(2, 4))
            await random_scroll(page, "down")
            await human_delay(1.5, 3.5)

            # Maybe click a result (30%)
            if random.random() < 0.3:
                try:
                    links = page.locator('h3')
                    count = await links.count()
                    if count > 0:
                        idx = random.randint(0, min(4, count - 1))
                        await links.nth(idx).click()
                        await human_delay(3, 6)
                        await random_scroll(page, "down")
                        await human_delay(2, 4)
                except Exception:
                    pass

        visited += 1
        google_ok = True
    except Exception as e:
        logger.debug(f"Warmup Google error: {e}")
        google_ok = False

    # If Google didn't load, proxy is dead — skip all other sites
    if not google_ok:
        logger.info("[WARN] Proxy not working, warmup failed")
        elapsed = asyncio.get_event_loop().time() - start
        logger.debug(f"Warmup complete: {elapsed:.1f}s, 0 sites visited")
        return

    # Visit random sites from the pool
    random.shuffle(sites)
    consecutive_errors = 0  # Track failures for dead proxy detection
    for url, name in sites:
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed > duration_seconds or visited >= max_visits:
            break

        # Dead proxy detection: 2 consecutive fails = stop warmup
        if consecutive_errors >= 2:
            logger.debug(f"Warmup: {consecutive_errors} consecutive errors — proxy likely dead, stopping")
            break

        try:
            await page.goto(url, wait_until="load", timeout=15000)
            consecutive_errors = 0  # Reset on success
            await human_delay(3, 6)

            # Read the page (bezier mouse + scrolling)
            await random_mouse_move(page, steps=random.randint(2, 5))
            await random_scroll(page, "down")
            await human_delay(2, 5)

            # More scrolling
            for _ in range(random.randint(1, 3)):
                await random_scroll(page, "down")
                await human_delay(1, 4)

            # Maybe scroll back up (40%)
            if random.random() < 0.4:
                await random_scroll(page, "up")
                await human_delay(1, 2.5)

            # Idle browsing behavior
            if random.random() < 0.3:
                await idle_behavior(page, random.uniform(1, 3))

            # Mouse reading movements
            await random_mouse_move(page, steps=random.randint(1, 4))
            await human_delay(1.5, 3.5)

            # Maybe click a link (20%)
            if random.random() < 0.2:
                try:
                    links = page.locator('a')
                    count = await links.count()
                    if count > 5:
                        idx = random.randint(0, min(10, count - 1))
                        await links.nth(idx).click()
                        await human_delay(3, 6)
                        await random_scroll(page, "down")
                        await human_delay(1.5, 3.5)
                except Exception:
                    pass

            visited += 1

        except Exception as e:
            consecutive_errors += 1
            logger.debug(f"Warmup site {name} error ({consecutive_errors}/2): {e}")
            # Don't hammer the proxy — wait before trying next site
            await asyncio.sleep(random.uniform(2, 4))

    elapsed = asyncio.get_event_loop().time() - start
    logger.debug(f"Warmup complete: {elapsed:.1f}s, {visited} sites visited")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. PRE/POST REGISTRATION WARMUP
# ═══════════════════════════════════════════════════════════════════════════════

async def pre_registration_warmup(page, geo: str = None):
    """
    Full pre-registration warmup sequence with GEO awareness.
    Makes the session look like a real user before hitting signup page.
    """
    await warmup_browsing(page, duration_seconds=random.randint(45, 90), geo=geo)


async def post_registration_warmup(page, provider: str = "yahoo", duration_seconds: int = None):
    """
    Post-registration session aging: visit inbox, settings, compose.
    Makes the freshly created account look like a real first-time user.
    Runs 15-30s - enough to establish session cookies without being slow.
    """
    if duration_seconds is None:
        duration_seconds = random.randint(45, 90)

    logger.debug(f"Post-reg warmup ({provider}) for ~{duration_seconds}s")

    PROVIDER_PAGES = {
        "yahoo": [
            ("https://mail.yahoo.com", "Yahoo Mail Inbox"),
            ("https://mail.yahoo.com/d/settings/1", "Yahoo Settings"),
            ("https://mail.yahoo.com/d/compose/", "Yahoo Compose"),
        ],
        "aol": [
            ("https://mail.aol.com", "AOL Mail Inbox"),
            ("https://mail.aol.com/d/settings/1", "AOL Settings"),
            ("https://mail.aol.com/d/compose/", "AOL Compose"),
        ],
        "outlook": [
            ("https://outlook.live.com/mail/0/inbox", "Outlook Inbox"),
            ("https://outlook.live.com/mail/0/options/general", "Outlook Settings"),
            ("https://outlook.live.com/people/", "Outlook People"),
        ],
        "hotmail": [
            ("https://outlook.live.com/mail/0/inbox", "Hotmail Inbox"),
            ("https://outlook.live.com/mail/0/options/general", "Hotmail Settings"),
            ("https://outlook.live.com/people/", "Hotmail People"),
        ],
        "gmail": [
            ("https://mail.google.com/mail/u/0/#inbox", "Gmail Inbox"),
            ("https://mail.google.com/mail/u/0/#settings/general", "Gmail Settings"),
        ],
    }

    pages_to_visit = PROVIDER_PAGES.get(provider.lower(), PROVIDER_PAGES["yahoo"])
    start = asyncio.get_event_loop().time()

    for url, name in pages_to_visit:
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed > duration_seconds:
            break

        try:
            logger.debug(f"Post-reg warmup: visiting {name}")
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await human_delay(2, 5)

            # Human-like: scroll and move mouse with Bezier
            await random_mouse_move(page, steps=random.randint(2, 5))
            await random_scroll(page, "down")
            await human_delay(1, 3)

            # Read more
            if random.random() < 0.6:
                await random_scroll(page, "down")
                await human_delay(1, 2)

            if random.random() < 0.3:
                await random_scroll(page, "up")
                await human_delay(0.5, 1)

            # Idle (human reading inbox)
            if random.random() < 0.4:
                await idle_behavior(page, random.uniform(1, 3))

            await random_mouse_move(page, steps=random.randint(1, 3))
            await human_delay(1, 2)

        except Exception as e:
            logger.debug(f"Post-reg warmup {name} error: {e}")
            continue

    elapsed = asyncio.get_event_loop().time() - start
    logger.debug(f"Post-reg warmup done: {elapsed:.1f}s ({provider})")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. FORM REVIEW SCAN (eyes scanning form before submit)
# ═══════════════════════════════════════════════════════════════════════════════

async def form_review_scan(page, field_selectors: list[str] = None):
    """
    Simulate a human reviewing a filled form before clicking Submit.
    Mouse traces from field to field (top→bottom), pausing at each
    as if re-reading entered values. Anti-bot systems track this.
    """
    if not field_selectors:
        # Auto-detect visible input fields
        field_selectors = ['input[type="text"]', 'input[type="email"]',
                          'input[type="password"]', 'input[type="tel"]',
                          'select', 'textarea']

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    visited = 0

    for sel in field_selectors:
        try:
            els = page.locator(sel)
            count = await els.count()
            for i in range(count):
                el = els.nth(i)
                if not await el.is_visible():
                    continue
                box = await el.bounding_box()
                if not box:
                    continue

                # Move mouse to field with Bezier
                cx = box["x"] + box["width"] * random.uniform(0.2, 0.8)
                cy = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                await _move_mouse_to(page, cx, cy)

                # Reading dwell (200-800ms per field)
                await asyncio.sleep(random.uniform(0.2, 0.8))
                visited += 1

                if visited >= 6:  # Don't scan too many
                    break
        except Exception:
            continue

    # Final pause — "everything looks good" moment
    if visited > 0:
        await asyncio.sleep(random.uniform(0.4, 1.0))


# ═══════════════════════════════════════════════════════════════════════════════
# 10. FOCUS / BLUR EVENT SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

async def focus_blur_field(page, selector: str):
    """
    Dispatch focus, input, change, blur events on a field.
    Modern anti-bot (Arkose, PerimeterX) tracks these DOM events.
    A bot that fills via JS but never triggers focus/blur is suspicious.
    """
    try:
        el = page.locator(selector).first
        if await el.count() == 0:
            return

        await el.evaluate("""el => {
            el.dispatchEvent(new Event('focus', {bubbles: true}));
            el.dispatchEvent(new Event('focusin', {bubbles: true}));
        }""")
        await asyncio.sleep(random.uniform(0.05, 0.15))

        await el.evaluate("""el => {
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        await asyncio.sleep(random.uniform(0.05, 0.1))

        await el.evaluate("""el => {
            el.dispatchEvent(new Event('blur', {bubbles: true}));
            el.dispatchEvent(new Event('focusout', {bubbles: true}));
        }""")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# 11. READING-SPEED AWARE DWELL
# ═══════════════════════════════════════════════════════════════════════════════

async def reading_dwell(page, min_seconds: float = 1.0, max_seconds: float = 5.0):
    """
    Pause proportional to visible text content length.
    More text on page → longer reading dwell. Plus some mouse drift.
    """
    try:
        text_length = await page.evaluate("document.body.innerText.length")
        # ~250 WPM average reading speed, ~5 chars/word
        estimated_read_time = (text_length / 5 / 250) * 60  # seconds
        dwell = max(min_seconds, min(max_seconds, estimated_read_time * random.uniform(0.1, 0.3)))
    except Exception:
        dwell = random.uniform(min_seconds, max_seconds)

    # Drift mouse while "reading"
    elapsed = 0
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    while elapsed < dwell:
        dx = random.gauss(0, 8)
        dy = random.gauss(0, 5)
        cx = max(10, min(viewport["width"] - 10, int(viewport["width"] * 0.5 + dx)))
        cy = max(10, min(viewport["height"] - 10, int(viewport["height"] * 0.4 + dy)))
        try:
            await page.mouse.move(cx, cy)
        except Exception:
            pass
        pause = random.uniform(0.2, 0.5)
        await asyncio.sleep(pause)
        elapsed += pause


# ═══════════════════════════════════════════════════════════════════════════════
# 12. CLIPBOARD PASTE SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

async def clipboard_paste(page, selector: str, text: str):
    """
    Simulate Ctrl+V paste (some humans copy-paste passwords from managers).
    Uses clipboard API to set content, then keyboard shortcut.
    ~20% of real users paste passwords instead of typing.
    """
    try:
        el = page.locator(selector).first
        box = await el.bounding_box()
        if box:
            cx = box["x"] + box["width"] * 0.5 + random.gauss(0, 5)
            cy = box["y"] + box["height"] * 0.5 + random.gauss(0, 3)
            await _move_mouse_to(page, cx, cy)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.mouse.click(cx, cy)
        else:
            await el.click()
        await asyncio.sleep(random.uniform(0.2, 0.5))

        # Set clipboard and paste
        await page.evaluate(f"navigator.clipboard.writeText('{text}')")
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.keyboard.press("Control+a")  # Select all first
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.keyboard.press("Control+v")
        await asyncio.sleep(random.uniform(0.2, 0.5))
    except Exception:
        # Fallback: fill directly
        try:
            await page.locator(selector).first.fill(text)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# 13. NATURAL TAB/CLICK FIELD NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════════

async def natural_tab_navigate(page, from_selector: str = None, to_selector: str = None):
    """
    Navigate between fields using Tab or mouse click (mixed).
    Real humans alternate between keyboard and mouse navigation.
    ~40% Tab, ~60% mouse click for form fields.
    """
    use_tab = random.random() < 0.4

    if use_tab:
        await page.keyboard.press("Tab")
        await asyncio.sleep(random.uniform(0.2, 0.5))
    elif to_selector:
        await human_click(page, to_selector)
    else:
        # Just Tab if no target selector
        await page.keyboard.press("Tab")
        await asyncio.sleep(random.uniform(0.2, 0.5))


# ═══════════════════════════════════════════════════════════════════════════════
# 14. MICRO-HESITATION (before important actions)
# ═══════════════════════════════════════════════════════════════════════════════

async def micro_hesitation(page, action_name: str = "submit"):
    """
    Brief freeze before important actions (Submit, Confirm, Continue).
    Real humans hesitate 0.5-2s before clicking Submit — re-reading the button,
    mentally confirming. Bots click instantly. This is detected.
    """
    # Brief mouse freeze (stop moving)
    await asyncio.sleep(random.uniform(0.3, 0.8))

    # Tiny mouse jitter (hand tension before pressing)
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    for _ in range(random.randint(1, 3)):
        dx = random.gauss(0, 3)
        dy = random.gauss(0, 2)
        try:
            await page.mouse.move(
                viewport["width"] // 2 + int(dx),
                viewport["height"] // 2 + int(dy)
            )
        except Exception:
            pass
        await asyncio.sleep(random.uniform(0.1, 0.2))

    # Final pause — "ok, I'll click now"
    await asyncio.sleep(random.uniform(0.2, 0.5))


# ═══════════════════════════════════════════════════════════════════════════════
# 15. SCROLL TO ELEMENT (natural scrolling to bring element into view)
# ═══════════════════════════════════════════════════════════════════════════════

async def scroll_to_element(page, selector: str):
    """
    Smoothly scroll to bring an element into viewport.
    Uses incremental scrolling instead of instant scrollIntoView().
    Anti-bot systems flag instant viewport jumps.
    """
    try:
        el = page.locator(selector).first
        if await el.count() == 0:
            return

        box = await el.bounding_box()
        if not box:
            # Element exists but not in layout — use JS scroll
            await el.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return

        viewport = page.viewport_size or {"width": 1280, "height": 720}
        vh = viewport["height"]

        # Check if element is visible in viewport
        if box["y"] >= 0 and box["y"] + box["height"] <= vh:
            return  # Already visible

        # Calculate scroll needed
        scroll_needed = box["y"] - vh * 0.4  # target 40% from top

        # Smooth scroll in chunks
        direction = 1 if scroll_needed > 0 else -1
        remaining = abs(scroll_needed)
        chunks = random.randint(3, 6)

        for i in range(chunks):
            chunk = (remaining / (chunks - i)) * random.uniform(0.8, 1.2)
            chunk = min(chunk, remaining) * direction
            try:
                await page.mouse.wheel(0, chunk)
                await asyncio.sleep(random.uniform(0.04, 0.12))
            except Exception:
                break
            remaining -= abs(chunk)
            if remaining <= 5:
                break

        await asyncio.sleep(random.uniform(0.2, 0.5))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# 16. WINDOW / VIEWPORT EVENTS
# ═══════════════════════════════════════════════════════════════════════════════

async def simulate_window_focus(page):
    """
    Dispatch window focus/visibilitychange events.
    Tab-switching is normal human behavior. Anti-bot systems track if
    a window NEVER loses/regains focus (bots don't switch tabs).
    """
    try:
        # Simulate brief tab switch (user checking something else)
        if random.random() < 0.15:
            await page.evaluate("""
                document.dispatchEvent(new Event('visibilitychange'));
                window.dispatchEvent(new Event('blur'));
            """)
            await asyncio.sleep(random.uniform(1, 4))  # "looked at another tab"
            await page.evaluate("""
                document.dispatchEvent(new Event('visibilitychange'));
                window.dispatchEvent(new Event('focus'));
            """)
            await asyncio.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass
