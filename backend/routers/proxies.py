from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Proxy, ProxyStatus, Account
from ..schemas import ProxyImportRequest
from ..services.proxy_monitor import monitor_all_proxies
from ..services.proxy_manager import ProxyManager
from loguru import logger

router = APIRouter(prefix="/api/proxies", tags=["proxies"])


class ProxyRefreshRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


@router.get("/")
async def list_proxies(status: str = None, db: Session = Depends(get_db)):
    query = db.query(Proxy)
    if status:
        query = query.filter(Proxy.status == status)
    proxies = query.all()
    result = []
    for p in proxies:
        bound_to = None
        if p.bound_account_id:
            acc = db.query(Account).filter(Account.id == p.bound_account_id).first()
            bound_to = acc.email if acc else None

        result.append({
            "id": p.id,
            "host": p.host,
            "port": p.port,
            "username": p.username or "",
            "protocol": p.protocol,
            "proxy_type": p.proxy_type,
            "status": p.status,
            "geo": p.geo,
            "response_time_ms": p.response_time_ms,
            "fail_count": p.fail_count,
            "use_count": p.use_count or 0,
            "use_G": p.use_gmail or 0,
            "use_YA": (p.use_yahoo or 0) + (p.use_aol or 0),
            "use_OH": (p.use_outlook or 0) + (p.use_hotmail or 0),
            "use_PT": p.use_protonmail or 0,
            "bound_to": bound_to,
            "source": getattr(p, 'source', 'manual') or 'manual',
            "last_check": p.last_check.isoformat() if p.last_check else None,
            "expires_at": p.expires_at.isoformat() if p.expires_at else None,
        })
    return result


@router.get("/stats")
async def proxy_stats(db: Session = Depends(get_db)):
    pm = ProxyManager(db)
    return pm.get_stats()


@router.post("/{proxy_id}/move-to-active")
async def move_to_active(proxy_id: int, db: Session = Depends(get_db)):
    """Move a dead/exhausted/expired proxy back to active pool."""
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        return {"error": "Proxy not found"}
    if proxy.status == "active":
        return {"error": "Proxy is already active"}
    proxy.status = "active"
    proxy.fail_count = 0
    db.commit()
    return {"ok": True, "id": proxy_id, "status": "active"}


import re


class ProxyImportSimple(BaseModel):
    proxies: list[str]
    expires_at: Optional[str] = None


def parse_proxy_line(line: str) -> dict | None:
    """Auto-parse proxy in ANY format. Returns {host, port, username, password, protocol, proxy_type}.
    
    Supported formats:
        protocol://user:pass@host:port
        protocol://host:port
        user:pass@host:port
        host:port:user:pass
        user:pass:host:port  (if host looks like IP or hostname)
        host:port
    
    Protocol: http, https, socks4, socks5
    Host: IP (1.2.3.4) or hostname (proxy.example.com)
    """
    line = line.strip().rstrip('/')
    if not line or line.startswith('#'):
        return None

    host = port = username = password = None
    detected_protocol = None

    # ─── 1. Protocol prefix: protocol://... ───
    proto_match = re.match(r'^(https?|socks[45]?)://', line, re.IGNORECASE)
    if proto_match:
        detected_protocol = proto_match.group(1).lower()
        line = line[proto_match.end():]  # strip protocol://

    # ─── 2. Auth separator: user:pass@host:port ───
    if '@' in line:
        auth_part, server_part = line.rsplit('@', 1)
        # Parse auth (user:pass)
        if ':' in auth_part:
            username, password = auth_part.split(':', 1)
        else:
            username = auth_part
            password = ''
        # Parse server (host:port)
        # Handle IPv6 [::1]:port or host:port
        if server_part.startswith('['):
            # IPv6: [::1]:port
            m6 = re.match(r'^\[([^\]]+)\]:(\d+)$', server_part)
            if m6:
                host, port = m6.group(1), int(m6.group(2))
        else:
            parts = server_part.rsplit(':', 1)
            if len(parts) == 2:
                host = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    return None
            else:
                host = parts[0]
                port = 1080 if detected_protocol and 'socks' in detected_protocol else 80

    # ─── 3. No @: could be host:port, host:port:user:pass, or user:pass:host:port ───
    else:
        parts = line.split(':')
        
        if len(parts) == 2:
            # host:port
            host = parts[0]
            try:
                port = int(parts[1])
            except ValueError:
                return None

        elif len(parts) == 4:
            # Could be host:port:user:pass OR user:pass:host:port
            # Strategy: check for IP FIRST (strongest signal), then hostname
            p0_is_ip = bool(re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', parts[0]))
            p2_is_ip = bool(re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', parts[2]))
            
            if p0_is_ip and not p2_is_ip:
                # IP:port:user:pass
                host = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    return None
                username, password = parts[2], parts[3]
            elif p2_is_ip and not p0_is_ip:
                # user:pass:IP:port
                username, password = parts[0], parts[1]
                host = parts[2]
                try:
                    port = int(parts[3])
                except ValueError:
                    return None
            elif p0_is_ip and p2_is_ip:
                # Both IPs - default to host:port:user:pass
                host = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    return None
                username, password = parts[2], parts[3]
            else:
                # Neither is IP - check hostnames (with dots like proxy.com)
                p0_is_host = _looks_like_host(parts[0])
                p2_is_host = _looks_like_host(parts[2])
                if p0_is_host:
                    host = parts[0]
                    try:
                        port = int(parts[1])
                    except ValueError:
                        return None
                    username, password = parts[2], parts[3]
                elif p2_is_host:
                    username, password = parts[0], parts[1]
                    host = parts[2]
                    try:
                        port = int(parts[3])
                    except ValueError:
                        return None
                else:
                    return None

        elif len(parts) == 3:
            # host:port:user (no password) - rare but handle it
            if _looks_like_host(parts[0]):
                host = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    return None
                username = parts[2]
            else:
                return None
        else:
            return None

    if not host or not port:
        return None
    
    # Validate port range
    if port < 1 or port > 65535:
        return None
    
    # Strip whitespace from all fields
    host = host.strip()
    if username:
        username = username.strip()
    if password:
        password = password.strip()

    # ─── Auto-detect proxy type ───
    proxy_type = "http"
    user_lower = (username or "").lower()

    if detected_protocol and 'socks' in detected_protocol:
        proxy_type = "socks5"
    elif 'mobile' in user_lower:
        proxy_type = "mobile"
    elif detected_protocol == 'https':
        proxy_type = "https"
    elif port in (1080, 1081, 1082):
        proxy_type = "socks5"

    # Protocol derived from type
    if proxy_type == "socks5":
        protocol = "socks5"
    elif proxy_type == "https":
        protocol = "https"
    else:
        protocol = "http"

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "protocol": protocol,
        "proxy_type": proxy_type,
    }


def _looks_like_host(s: str) -> bool:
    """Check if string looks like an IP address or hostname."""
    s = s.strip()
    # IPv4: 1.2.3.4
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', s):
        return True
    # Hostname: contains dot and letters (proxy.example.com)
    if '.' in s and re.search(r'[a-zA-Z]', s):
        return True
    # Single word hostname (rare but valid: localhost, proxy-server)
    if re.match(r'^[a-zA-Z][a-zA-Z0-9\-]+$', s):
        return True
    return False


@router.post("/import")
async def import_proxies(req: ProxyImportSimple, db: Session = Depends(get_db)):
    """Import proxies with auto-detection of format and type."""
    added = 0
    types = {"socks5": 0, "http": 0, "mobile": 0}

    # Parse expires_at string to datetime object
    parsed_expires = None
    if req.expires_at:
        from datetime import datetime as dt
        for fmt in ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                parsed_expires = dt.strptime(req.expires_at, fmt)
                break
            except ValueError:
                continue
        if not parsed_expires:
            try:
                from dateutil.parser import parse as dateparse
                parsed_expires = dateparse(req.expires_at)
            except Exception:
                logger.warning(f"Could not parse expires_at: {req.expires_at}")

    for proxy_str in req.proxies:
        parsed = parse_proxy_line(proxy_str)
        if not parsed:
            continue

        # Check duplicate
        exists = db.query(Proxy).filter(
            Proxy.host == parsed["host"], Proxy.port == parsed["port"]
        ).first()
        if exists:
            continue

        proxy = Proxy(
            host=parsed["host"],
            port=parsed["port"],
            username=parsed["username"],
            password=parsed["password"],
            protocol=parsed["protocol"],
            proxy_type=parsed["proxy_type"],
            expires_at=parsed_expires,
        )
        db.add(proxy)
        added += 1
        types[parsed["proxy_type"]] = types.get(parsed["proxy_type"], 0) + 1

    db.commit()
    logger.info(f"Imported {added} proxies (socks5={types.get('socks5',0)}, http={types.get('http',0)}, mobile={types.get('mobile',0)})")
    return {
        "imported": added,
        "types": types,
        "total": db.query(Proxy).count(),
    }


@router.delete("/dead")
async def delete_dead_proxies(db: Session = Depends(get_db)):
    """Delete all dead/expired/banned proxies. Unbind accounts first."""
    dead_proxies = db.query(Proxy).filter(
        Proxy.status.in_(["dead", "expired", "banned"])
    ).all()

    dead_ids = [p.id for p in dead_proxies]
    if not dead_ids:
        return {"deleted": 0}

    accounts = db.query(Account).filter(Account.proxy_id.in_(dead_ids)).all()
    for acc in accounts:
        acc.proxy_id = None

    db.query(Proxy).filter(Proxy.id.in_(dead_ids)).delete(synchronize_session=False)
    db.commit()
    logger.info(f"Deleted {len(dead_ids)} dead proxies, unbound {len(accounts)} accounts")
    return {"deleted": len(dead_ids), "unbound_accounts": len(accounts)}


@router.delete("/exhausted")
async def delete_exhausted_proxies(db: Session = Depends(get_db)):
    """Delete all exhausted proxies (all provider limits hit). Unbind accounts first."""
    exhausted = db.query(Proxy).filter(Proxy.status == "exhausted").all()
    ids = [p.id for p in exhausted]
    if not ids:
        return {"deleted": 0}

    accounts = db.query(Account).filter(Account.proxy_id.in_(ids)).all()
    for acc in accounts:
        acc.proxy_id = None

    db.query(Proxy).filter(Proxy.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    logger.info(f"Deleted {len(ids)} exhausted proxies")
    return {"deleted": len(ids), "unbound_accounts": len(accounts)}


@router.delete("/all")
async def delete_all_proxies(db: Session = Depends(get_db)):
    """Delete all proxies."""
    # Clear proxy bindings from accounts first
    accounts_with_proxy = db.query(Account).filter(Account.proxy_id.isnot(None)).all()
    for acc in accounts_with_proxy:
        acc.proxy_id = None
    
    total = db.query(Proxy).count()
    db.query(Proxy).delete(synchronize_session=False)
    db.commit()
    logger.info(f"Deleted all {total} proxies")
    return {"deleted": total}


@router.post("/batch-delete")
async def batch_delete_proxies(req: dict, db: Session = Depends(get_db)):
    """Delete multiple proxies by IDs."""
    ids = req.get("ids", [])
    if not ids:
        return {"deleted": 0}
    # Unbind accounts
    accounts = db.query(Account).filter(Account.proxy_id.in_(ids)).all()
    for acc in accounts:
        acc.proxy_id = None
    count = db.query(Proxy).filter(Proxy.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}


@router.delete("/{proxy_id}")
async def delete_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        return {"error": "Proxy not found"}
    if proxy.bound_account_id:
        return {"error": "Proxy is bound to an account. Unbind first."}
    db.delete(proxy)
    db.commit()
    return {"status": "deleted"}


@router.post("/check")
async def check_all_proxies():
    """Manual trigger for proxy health check."""
    result = await monitor_all_proxies()
    return result


@router.post("/{proxy_id}/unbind")
async def unbind_proxy(proxy_id: int, db: Session = Depends(get_db)):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        return {"error": "Proxy not found"}
    # Clear binding from account too
    if proxy.bound_account_id:
        acc = db.query(Account).filter(Account.id == proxy.bound_account_id).first()
        if acc:
            acc.proxy_id = None
    proxy.bound_account_id = None
    proxy.status = ProxyStatus.ACTIVE  # BOUND -> ACTIVE when unbound
    db.commit()
    return {"status": "unbound"}


@router.post("/{proxy_id}/refresh")
async def refresh_proxy(proxy_id: int, req: ProxyRefreshRequest, db: Session = Depends(get_db)):
    """
    Refresh proxy connection data (when provider changes credentials but IP stays same).
    The proxy stays bound to its account.
    """
    pm = ProxyManager(db)
    return pm.refresh_proxy(
        proxy_id,
        new_host=req.host,
        new_port=req.port,
        new_username=req.username,
        new_password=req.password,
    )


@router.post("/auto-reassign")
async def auto_reassign(db: Session = Depends(get_db)):
    """
    Auto-reassign accounts from dead/expired proxies to available active ones.
    Called manually or by proxy monitor when a proxy dies.
    """
    pm = ProxyManager(db)
    return pm.auto_reassign_dead_proxies()


@router.post("/reset-all")
async def reset_all_proxies(db: Session = Depends(get_db)):
    """Reset ALL non-bound proxies back to active status AND clear counters.
    BOUND proxies are skipped (still in use by accounts)."""
    count = db.query(Proxy).filter(
        Proxy.status.in_([ProxyStatus.DEAD, "dead", ProxyStatus.EXPIRED, "expired",
                          ProxyStatus.BANNED, "banned", ProxyStatus.EXHAUSTED, "exhausted"])
    ).count()

    # Only reset non-bound proxies
    db.query(Proxy).filter(
        Proxy.status != ProxyStatus.BOUND
    ).update({
        Proxy.status: ProxyStatus.ACTIVE,
        Proxy.fail_count: 0,
        Proxy.use_gmail: 0,
        Proxy.use_yahoo: 0,
        Proxy.use_aol: 0,
        Proxy.use_outlook: 0,
        Proxy.use_hotmail: 0,
        Proxy.use_protonmail: 0,
        Proxy.use_count: 0,
    }, synchronize_session=False)
    db.commit()

    logger.info(f"Reset {count} proxies to ACTIVE + cleared all counters (BOUND proxies skipped)")
    return {"reset": count, "total": db.query(Proxy).count()}


@router.post("/reset-counters")
async def reset_counters(db: Session = Depends(get_db)):
    """Reset per-provider usage counters on all proxies. Re-activates exhausted -> active."""
    pm = ProxyManager(db)
    result = pm.reset_all_counters()
    return result


@router.post("/release-free")
async def release_free_proxies(db: Session = Depends(get_db)):
    """Release all dead/expired UNBOUND proxies back to ACTIVE for reuse."""
    pm = ProxyManager(db)
    result = pm.release_all_free_proxies()
    return result


@router.post("/check/{proxy_id}")
async def check_single_proxy(proxy_id: int):
    """Manually check a single proxy right now."""
    from ..services.proxy_monitor import check_proxy_once
    result = await check_proxy_once(proxy_id)
    return result


@router.post("/check-all")
async def check_all_proxies():
    """Run a full proxy check on all active proxies right now."""
    from ..services.proxy_monitor import monitor_all_proxies
    result = await monitor_all_proxies()
    return result


@router.post("/health-check")
async def proxy_health_check(db: Session = Depends(get_db)):
    """Deep health check: TCP test all active proxies + auto-deactivate slow ones (>10s)."""
    pm = ProxyManager(db)
    health = await pm.check_all_proxies_health()
    slow = await pm.auto_deactivate_slow_proxies()
    return {
        **health,
        "slow_deactivated": slow["deactivated"],
        "threshold_ms": slow["threshold_ms"],
    }

