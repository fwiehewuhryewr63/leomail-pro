"""
Leomail v3 — Human Behavior Engine
Realistic human-like interactions for browser automation.
Makes every browser session look like a real person.
"""
import asyncio
import random
import math
from loguru import logger


async def human_delay(min_s: float = 0.5, max_s: float = 1.5):
    """Random delay with slight human-like variance."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def random_mouse_move(page, steps: int = None):
    """
    Move mouse to random positions on the page with natural curves.
    Simulates real hand movements with bezier-like curves.
    """
    if steps is None:
        steps = random.randint(2, 5)

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    w, h = viewport["width"], viewport["height"]

    for _ in range(steps):
        # Random target position (avoid extreme edges)
        target_x = random.randint(int(w * 0.05), int(w * 0.95))
        target_y = random.randint(int(h * 0.1), int(h * 0.85))

        # Move in small increments (bezier-like)
        move_steps = random.randint(3, 8)
        for i in range(move_steps):
            t = (i + 1) / move_steps
            # Add slight curve wobble
            wobble_x = random.randint(-15, 15) * (1 - t)
            wobble_y = random.randint(-10, 10) * (1 - t)
            x = int(target_x * t + wobble_x)
            y = int(target_y * t + wobble_y)
            x = max(0, min(w, x))
            y = max(0, min(h, y))
            try:
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.01, 0.04))
            except Exception:
                pass

        # Small pause after movement
        await asyncio.sleep(random.uniform(0.05, 0.2))


async def random_scroll(page, direction: str = "random"):
    """
    Scroll the page naturally.
    direction: "down", "up", or "random"
    """
    viewport = page.viewport_size or {"width": 1280, "height": 720}

    if direction == "random":
        direction = random.choice(["down", "up", "down", "down"])  # bias towards down

    scroll_amount = random.randint(100, 400)
    if direction == "up":
        scroll_amount = -scroll_amount

    # Scroll in small chunks for realism
    chunks = random.randint(2, 5)
    per_chunk = scroll_amount / chunks

    for _ in range(chunks):
        try:
            await page.mouse.wheel(0, per_chunk)
            await asyncio.sleep(random.uniform(0.05, 0.15))
        except Exception:
            pass

    await asyncio.sleep(random.uniform(0.2, 0.5))


async def human_click(page, selector: str, timeout: int = 5000):
    """
    Click an element with human-like approach:
    1. Move mouse towards element gradually
    2. Small pause before click
    3. Click with slight offset from center
    """
    try:
        el = page.locator(selector).first
        box = await el.bounding_box()
        if not box:
            await el.click(timeout=timeout)
            return

        # Move to element with some wobble
        center_x = box["x"] + box["width"] / 2
        center_y = box["y"] + box["height"] / 2

        # Add slight offset (humans don't click dead center)
        offset_x = random.uniform(-box["width"] * 0.2, box["width"] * 0.2)
        offset_y = random.uniform(-box["height"] * 0.2, box["height"] * 0.2)

        target_x = center_x + offset_x
        target_y = center_y + offset_y

        # Approach in steps
        steps = random.randint(3, 6)
        for i in range(steps):
            t = (i + 1) / steps
            x = int(target_x * t)
            y = int(target_y * t)
            try:
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.01, 0.03))
            except Exception:
                pass

        # Small pre-click pause
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # Click at position
        await page.mouse.click(target_x, target_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))

    except Exception:
        # Fallback to regular click
        try:
            await page.locator(selector).first.click(timeout=timeout)
        except Exception:
            pass


async def human_type(page, selector: str, text: str, clear: bool = True):
    """
    Type text into a field like a real human:
    - Variable typing speed
    - Occasional pauses (thinking)
    - Move mouse to field first
    """
    el = page.locator(selector).first

    # Click the field first
    try:
        box = await el.bounding_box()
        if box:
            cx = box["x"] + box["width"] / 2 + random.uniform(-10, 10)
            cy = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
            await page.mouse.click(cx, cy)
            await asyncio.sleep(random.uniform(0.1, 0.3))
    except Exception:
        await el.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))

    if clear:
        await el.fill("")
        await asyncio.sleep(random.uniform(0.1, 0.2))

    # Type character by character with human-like delays
    for i, char in enumerate(text):
        delay = random.randint(40, 120)  # ms between keystrokes

        # Occasional longer pause (thinking)
        if random.random() < 0.08:
            await asyncio.sleep(random.uniform(0.3, 0.7))

        await el.type(char, delay=delay)

    await asyncio.sleep(random.uniform(0.2, 0.5))


async def warmup_browsing(page, duration_seconds: int = None):
    """
    Browse Google/YouTube for a bit before registration.
    Warms up the browser fingerprint and makes it look like a real session.
    """
    if duration_seconds is None:
        duration_seconds = random.randint(15, 40)

    logger.debug(f"Warmup browsing for ~{duration_seconds}s")

    sites = [
        ("https://www.google.com", "Google"),
        ("https://www.wikipedia.org", "Wikipedia"),
    ]

    start = asyncio.get_event_loop().time()

    for url, name in random.sample(sites, min(2, len(sites))):
        if asyncio.get_event_loop().time() - start > duration_seconds:
            break

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await human_delay(1, 3)

            # Random mouse movements on the page
            await random_mouse_move(page, steps=random.randint(3, 7))

            # Scroll around
            await random_scroll(page, "down")
            await human_delay(1, 2)
            await random_scroll(page, "down")
            await human_delay(0.5, 1.5)

            # Maybe scroll back up
            if random.random() < 0.4:
                await random_scroll(page, "up")
                await human_delay(0.5, 1)

            # Random mouse movements
            await random_mouse_move(page, steps=random.randint(2, 4))

            await human_delay(1, 3)

        except Exception as e:
            logger.debug(f"Warmup site {name} error: {e}")
            continue

    elapsed = asyncio.get_event_loop().time() - start
    logger.debug(f"Warmup complete: {elapsed:.1f}s")


async def between_steps(page):
    """
    Natural behavior between form steps.
    Random mouse move + optional scroll + micro-pause.
    Call this between each form field interaction.
    """
    # Random mouse move (short)
    if random.random() < 0.7:
        await random_mouse_move(page, steps=random.randint(1, 3))

    # Occasional scroll
    if random.random() < 0.2:
        await random_scroll(page, "down")

    # Micro-pause (thinking)
    await asyncio.sleep(random.uniform(0.3, 1.2))


async def pre_registration_warmup(page):
    """
    Full pre-registration warmup sequence:
    1. Visit Google, scroll around
    2. Random mouse movements
    3. Natural pauses
    Makes the session look like a real user before hitting signup page.
    """
    await warmup_browsing(page, duration_seconds=random.randint(15, 30))
