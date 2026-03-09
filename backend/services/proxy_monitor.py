"""
Leomail v3 - Proxy Health Monitor
Correct checking for all 3 proxy types: SOCKS5, HTTP, Mobile.
Uses aiohttp-socks for SOCKS5, standard aiohttp for HTTP/Mobile.
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from loguru import logger
from ..database import SessionLocal
from ..models import Proxy, ProxyStatus

# Multiple check endpoints - if one is down, try next
CHECK_ENDPOINTS = [
    ("http://ip-api.com/json", "query"),       # Returns {"query": "1.2.3.4", ...}
    ("http://httpbin.org/ip", "origin"),        # Returns {"origin": "1.2.3.4"}
    ("http://api.ipify.org/?format=json", "ip"),# Returns {"ip": "1.2.3.4"}
]

TIMEOUT_SEC = 25
CONCURRENT_CHECKS = 10


async def check_single_proxy(proxy: Proxy) -> dict:
    """Check one proxy. Works for SOCKS5, HTTP, and Mobile types.
    Tests HTTP connectivity via ip-api.com to get external IP and GEO.
    """
    proxy_type = (proxy.proxy_type or "http").lower()

    # Derive protocol for connection
    if proxy_type == "socks5":
        proto = "socks5"
    else:
        proto = "http"  # both 'http' and 'mobile' use HTTP

    # Build proxy URL
    proxy_url = f"{proto}://"
    if proxy.username and proxy.password:
        proxy_url += f"{proxy.username}:{proxy.password}@"
    proxy_url += f"{proxy.host}:{proxy.port}"

    is_socks = proto == "socks5"
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEC)

    for url, ip_key in CHECK_ENDPOINTS:
        try:
            if is_socks:
                try:
                    from aiohttp_socks import ProxyConnector
                    connector = ProxyConnector.from_url(proxy_url)
                    async with aiohttp.ClientSession(
                        connector=connector, timeout=timeout
                    ) as session:
                        start = datetime.utcnow()
                        async with session.get(url, ssl=False) as resp:
                            elapsed_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                ext_ip = data.get(ip_key, "unknown") if isinstance(data, dict) else "unknown"
                                return {
                                    "alive": True,
                                    "response_time_ms": elapsed_ms,
                                    "external_ip": str(ext_ip),
                                    "geo": data.get("countryCode", "").upper() if isinstance(data, dict) else "",
                                }
                except ImportError:
                    logger.warning("aiohttp-socks not installed - cannot check SOCKS5 proxies")
                    return {"alive": False, "response_time_ms": None, "external_ip": None}
            else:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    start = datetime.utcnow()
                    async with session.get(url, proxy=proxy_url, ssl=False) as resp:
                        elapsed_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            ext_ip = data.get(ip_key, "unknown") if isinstance(data, dict) else "unknown"
                            return {
                                "alive": True,
                                "response_time_ms": elapsed_ms,
                                "external_ip": str(ext_ip),
                                "geo": data.get("countryCode", "").upper() if isinstance(data, dict) else "",
                            }
        except Exception as e:
            logger.debug(f"Proxy check {proxy.host}:{proxy.port} ({proxy_type}) via {url} failed: {type(e).__name__}: {e}")
            continue  # Try next endpoint

    return {"alive": False, "response_time_ms": None, "external_ip": None, "geo": ""}


async def resolve_geo(ip: str) -> str:
    """Resolve GEO country code from IP using direct (non-proxy) lookup."""
    if not ip or ip in ("unknown", "tcp-only"):
        return ""
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"http://ip-api.com/json/{ip}?fields=countryCode", ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return (data.get("countryCode", "") or "").upper()
    except Exception:
        pass
    return ""


async def monitor_all_proxies(max_fails: int = 3):
    """
    Check all non-dead proxies concurrently.
    Proxy that fails max_fails times total -> marked DEAD.
    Logs provider-specific availability after check.
    """
    db = SessionLocal()
    try:
        # Check ALL non-dead proxies (active, free, etc.)
        proxies = db.query(Proxy).filter(
            ~Proxy.status.in_([ProxyStatus.DEAD, "dead"])
        ).all()

        if not proxies:
            return {"checked": 0, "alive": 0, "dead": 0}

        alive_count = 0
        dead_count = 0

        # Grace period: skip proxies added less than 5 minutes ago
        grace_cutoff = datetime.utcnow() - timedelta(minutes=5)

        to_check = []
        for proxy in proxies:
            if proxy.created_at and proxy.created_at > grace_cutoff:
                alive_count += 1  # Assume alive during grace period
            else:
                to_check.append(proxy)

        if not to_check:
            logger.info(f"Proxy monitor: {len(proxies)} total, all in grace period")
            return {"checked": 0, "alive": alive_count, "dead": 0}

        # Check concurrently in batches
        semaphore = asyncio.Semaphore(CONCURRENT_CHECKS)

        async def check_one(proxy):
            async with semaphore:
                return proxy, await check_single_proxy(proxy)

        tasks = [check_one(p) for p in to_check]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for item in results:
            if isinstance(item, Exception):
                logger.error(f"Proxy check exception: {item}")
                continue

            proxy, result = item
            proxy.last_check = datetime.utcnow()

            if result["alive"]:
                proxy.response_time_ms = result["response_time_ms"]
                proxy.fail_count = 0
                # Respect BOUND status — don't overwrite if proxy is bound to account
                proxy.status = ProxyStatus.BOUND if proxy.bound_account_id else ProxyStatus.ACTIVE
                if result.get("external_ip") and result["external_ip"] not in ("unknown", "tcp-only"):
                    proxy.external_ip = result["external_ip"]
                if result.get("geo"):
                    proxy.geo = result["geo"]
                elif proxy.external_ip and not proxy.geo:
                    # Fallback: direct GEO lookup by external IP
                    geo = await resolve_geo(proxy.external_ip)
                    if geo:
                        proxy.geo = geo
                alive_count += 1
                logger.debug(f"Proxy OK: {proxy.host}:{proxy.port} ({proxy.proxy_type}) {result['response_time_ms']}ms IP={result.get('external_ip','?')} GEO={proxy.geo or '?'}")
            else:
                proxy.fail_count = (proxy.fail_count or 0) + 1
                proxy.response_time_ms = None
                if proxy.fail_count >= max_fails:
                    proxy.status = ProxyStatus.DEAD
                    dead_count += 1
                    logger.warning(f"Proxy DEAD: {proxy.host}:{proxy.port} ({proxy.proxy_type}) failed {proxy.fail_count}x")
                else:
                    logger.info(f"Proxy FAIL #{proxy.fail_count}/{max_fails}: {proxy.host}:{proxy.port} ({proxy.proxy_type})")

        db.commit()

        # ── Auto-revive DEAD proxies ──
        # Check if any DEAD proxies have come back to life
        # (prevents permanently killing proxies that had momentary hiccups)
        dead_proxies = db.query(Proxy).filter(
            Proxy.status.in_([ProxyStatus.DEAD, "dead"])
        ).all()
        revived_count = 0

        if dead_proxies:
            dead_tasks = [check_one(p) for p in dead_proxies]
            dead_results = await asyncio.gather(*dead_tasks, return_exceptions=True)

            for item in dead_results:
                if isinstance(item, Exception):
                    continue
                proxy, result = item
                proxy.last_check = datetime.utcnow()
                if result["alive"]:
                    # Respect BOUND status on revive
                    proxy.status = ProxyStatus.BOUND if proxy.bound_account_id else ProxyStatus.ACTIVE
                    proxy.fail_count = 0
                    proxy.response_time_ms = result["response_time_ms"]
                    if result.get("external_ip") and result["external_ip"] not in ("unknown", "tcp-only"):
                        proxy.external_ip = result["external_ip"]
                    if result.get("geo"):
                        proxy.geo = result["geo"]
                    revived_count += 1
                    new_status = "BOUND" if proxy.bound_account_id else "ACTIVE"
                    logger.info(
                        f"[RETRY] Proxy REVIVED: {proxy.host}:{proxy.port} ({proxy.proxy_type}) "
                        f"{result['response_time_ms']}ms - back to {new_status}"
                    )

            if revived_count > 0:
                db.commit()

        # Auto-reassign accounts bound to dead proxies
        if dead_count > 0:
            try:
                from .proxy_manager import ProxyManager
                pm = ProxyManager(db)
                reassign_result = pm.auto_reassign_dead_proxies()
                logger.info(f"Auto-reassign: {reassign_result}")
            except Exception as e:
                logger.error(f"Auto-reassign error: {e}")

        # ── Provider-aware availability summary ──
        from .proxy_manager import ProxyManager as PM
        alive_proxies = db.query(Proxy).filter(
            Proxy.status.in_([ProxyStatus.ACTIVE, "active"])
        ).all()
        ya_avail = sum(1 for p in alive_proxies if (p.use_yahoo or 0) + (p.use_aol or 0) < PM.YA_LIMIT)
        gm_avail = sum(1 for p in alive_proxies if (p.use_gmail or 0) < PM.GMAIL_LIMIT
                       and (p.proxy_type or "").lower() == "mobile")
        oh_avail = sum(1 for p in alive_proxies if (p.use_outlook or 0) + (p.use_hotmail or 0) < PM.OH_LIMIT)
        pt_avail = sum(1 for p in alive_proxies if (p.use_protonmail or 0) < PM.PT_LIMIT)
        wd_avail = sum(1 for p in alive_proxies if (getattr(p, 'use_webde', 0) or 0) < PM.WD_LIMIT)

        logger.info(
            f"Proxy monitor: {len(to_check)} checked ({alive_count} alive, {dead_count} dead)"
            + (f", {revived_count} revived" if revived_count > 0 else "")
        )
        logger.info(
            f"Available for autoreg: yahoo={ya_avail}, gmail={gm_avail}(mobile), "
            f"outlook={oh_avail}, proton={pt_avail}, webde={wd_avail}"
        )
        return {
            "checked": len(to_check), "alive": alive_count, "dead": dead_count,
            "revived": revived_count,
            "available": {"yahoo": ya_avail, "gmail": gm_avail, "outlook": oh_avail, "proton": pt_avail, "webde": wd_avail},
        }

    except Exception as e:
        logger.error(f"Proxy monitor error: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


async def check_proxy_once(proxy_id: int) -> dict:
    """
    Check a single proxy by ID - for manual check from UI.
    If fails -> increment fail_count but don't immediately kill.
    """
    db = SessionLocal()
    try:
        proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
        if not proxy:
            return {"error": "Proxy not found"}
        result = await check_single_proxy(proxy)
        proxy.last_check = datetime.utcnow()
        if result["alive"]:
            proxy.response_time_ms = result["response_time_ms"]
            proxy.fail_count = 0
            # Respect BOUND status
            proxy.status = ProxyStatus.BOUND if proxy.bound_account_id else ProxyStatus.ACTIVE
            if result.get("external_ip") and result["external_ip"] not in ("unknown", "tcp-only"):
                proxy.external_ip = result["external_ip"]
            if result.get("geo"):
                proxy.geo = result["geo"]
            elif proxy.external_ip and not proxy.geo:
                geo = await resolve_geo(proxy.external_ip)
                if geo:
                    proxy.geo = geo
        else:
            proxy.fail_count = (proxy.fail_count or 0) + 1
            if proxy.fail_count >= 3:
                proxy.status = ProxyStatus.DEAD
            proxy.response_time_ms = None
            logger.warning(f"Proxy manually checked: {proxy.host}:{proxy.port} ({proxy.proxy_type}) - {'DEAD' if proxy.fail_count >= 3 else f'FAIL #{proxy.fail_count}'}")
        db.commit()
        return {
            "proxy_id": proxy_id,
            "alive": result["alive"],
            "response_time_ms": result.get("response_time_ms"),
            "external_ip": result.get("external_ip"),
            "fail_count": proxy.fail_count,
            "status": proxy.status,
        }
    finally:
        db.close()


async def proxy_monitor_loop(interval_sec: int = 120, max_fails: int = 3):
    """Background loop that continuously monitors proxies."""
    logger.info(f"Proxy monitor started (interval: {interval_sec}s, max_fails: {max_fails})")
    await asyncio.sleep(30)  # Wait 30s after startup before first check
    while True:
        try:
            await monitor_all_proxies(max_fails=max_fails)
        except Exception as e:
            logger.error(f"Proxy monitor loop error: {e}")
        await asyncio.sleep(interval_sec)
