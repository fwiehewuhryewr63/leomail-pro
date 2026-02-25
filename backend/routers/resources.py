"""
Leomail v2.1 — Resource Calculator API
Serves server health + thread recommendations + active thread listing + batch resource loading
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import ThreadLog, Farm, Proxy, Template, RecipientDatabase, LinkDatabase, NamePack, Task, Account
from ..services.resource_calculator import ResourceCalculator
from sqlalchemy import func

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("/health")
async def server_health():
    """Overall server health for dashboard."""
    return ResourceCalculator.get_health_status()


@router.get("/threads/{task_type}")
async def recommend_threads(task_type: str, proxies: int = 999, active: int = 0):
    """
    Get recommended thread count for a task.
    task_type: birth | warmup | work
    proxies: how many free proxies are available
    active: how many threads are already running
    """
    if task_type not in ("birth", "warmup", "work"):
        return {"error": "task_type must be: birth, warmup, work"}
    return ResourceCalculator.get_max_threads(task_type, proxies, active)


@router.get("/system")
async def system_resources():
    """Raw system resource snapshot."""
    return ResourceCalculator.get_system_resources()


@router.get("/active-threads")
async def active_threads(db: Session = Depends(get_db)):
    """List recent thread logs: running + last 50 completed."""
    running = db.query(ThreadLog).filter(ThreadLog.status == "running").all()
    recent = db.query(ThreadLog).filter(
        ThreadLog.status.in_(["done", "error"])
    ).order_by(ThreadLog.updated_at.desc()).limit(50).all()
    
    threads = running + recent
    return [
        {
            "id": t.id,
            "task_id": t.task_id,
            "index": t.thread_index,
            "type": t.thread_type,
            "status": t.status,
            "action": t.current_action,
            "email": t.account_email,
            "proxy": t.proxy_info,
            "error": t.error_message,
            "started": t.started_at.isoformat() if t.started_at else None,
            "updated": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in threads
    ]


@router.get("/batch")
async def batch_resources(db: Session = Depends(get_db)):
    """
    Single endpoint returning ALL resources needed by Birth/Warmup/Work pages.
    Uses raw SQL to avoid ORM schema mismatch issues with older databases.
    """
    from sqlalchemy import text

    # Farms with account counts
    farms = []
    try:
        rows = db.execute(text(
            "SELECT f.id, f.name, COUNT(fa.account_id) as acc_count "
            "FROM farms f LEFT JOIN farm_accounts fa ON f.id = fa.farm_id "
            "GROUP BY f.id, f.name"
        )).fetchall()
        farms = [{"id": r[0], "name": r[1], "account_count": r[2]} for r in rows]
    except Exception:
        pass

    # Proxies (summary + per-type counts)
    proxies = {"total": 0, "alive": 0, "socks5": 0, "http": 0, "mobile": 0}
    try:
        row = db.execute(text(
            "SELECT COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) FROM proxies"
        )).fetchone()
        if row:
            proxies["total"] = row[0] or 0
            proxies["alive"] = row[1] or 0
        # Per-type active counts
        type_rows = db.execute(text(
            "SELECT proxy_type, COUNT(*) FROM proxies WHERE status='active' GROUP BY proxy_type"
        )).fetchall()
        for tr in type_rows:
            ptype = (tr[0] or 'http').lower()
            if ptype in ('socks5', 'http', 'mobile'):
                proxies[ptype] = tr[1] or 0
    except Exception:
        pass

    # Templates (with niche + variables for campaign matching)
    templates = []
    try:
        tpl_cols = [r[1] for r in db.execute(text("PRAGMA table_info(templates)")).fetchall()]
        select_parts = ["id", "name"]
        if "pack_name" in tpl_cols:
            select_parts.append("pack_name")
        if "niche" in tpl_cols:
            select_parts.append("niche")
        if "variables" in tpl_cols:
            select_parts.append("variables")
        rows = db.execute(text(f"SELECT {', '.join(select_parts)} FROM templates")).fetchall()
        for r in rows:
            t = {"id": r[0], "name": r[1]}
            idx = 2
            if "pack_name" in select_parts:
                t["pack_name"] = r[idx]; idx += 1
            else:
                t["pack_name"] = None
            if "niche" in select_parts:
                t["niche"] = r[idx] or ""; idx += 1
            else:
                t["niche"] = ""
            if "variables" in select_parts:
                import json as _json
                try:
                    t["variables"] = _json.loads(r[idx]) if r[idx] else []
                except Exception:
                    t["variables"] = []
                idx += 1
            else:
                t["variables"] = []
            t["needs_names"] = any(v in ["FIRSTNAME", "LASTNAME"] for v in t["variables"])
            templates.append(t)
    except Exception:
        pass

    # Recipient databases (with_name flag)
    databases = []
    try:
        db_cols = [r[1] for r in db.execute(text("PRAGMA table_info(recipient_databases)")).fetchall()]
        if "with_name" in db_cols:
            rows = db.execute(text(
                "SELECT id, name, total_count, used_count, with_name FROM recipient_databases"
            )).fetchall()
            databases = [{"id": r[0], "name": r[1], "total_count": r[2], "used_count": r[3], "with_name": bool(r[4])} for r in rows]
        else:
            rows = db.execute(text(
                "SELECT id, name, total_count, used_count FROM recipient_databases"
            )).fetchall()
            databases = [{"id": r[0], "name": r[1], "total_count": r[2], "used_count": r[3], "with_name": False} for r in rows]
    except Exception:
        pass

    # Link packs (with niche)
    links = []
    try:
        lnk_cols = [r[1] for r in db.execute(text("PRAGMA table_info(link_databases)")).fetchall()]
        if "niche" in lnk_cols:
            rows = db.execute(text("SELECT id, name, total_count, niche FROM link_databases")).fetchall()
            links = [{"id": r[0], "name": r[1], "total_count": r[2], "niche": r[3] or ""} for r in rows]
        else:
            rows = db.execute(text("SELECT id, name, total_count FROM link_databases")).fetchall()
            links = [{"id": r[0], "name": r[1], "total_count": r[2], "niche": ""} for r in rows]
    except Exception:
        pass

    # Name packs
    name_packs = []
    try:
        rows = db.execute(text("SELECT id, name, total_count FROM name_packs")).fetchall()
        name_packs = [{"id": r[0], "name": r[1], "total_count": r[2]} for r in rows]
    except Exception:
        pass

    # Task statuses
    task_status = {"birth": False, "warmup": False, "work": False}
    try:
        rows = db.execute(text("SELECT type FROM tasks WHERE status='running'")).fetchall()
        for r in rows:
            if r[0] in task_status:
                task_status[r[0]] = True
    except Exception:
        pass

    return {
        "farms": farms,
        "proxies": proxies,
        "templates": templates,
        "databases": databases,
        "links": links,
        "name_packs": name_packs,
        "task_status": task_status,
    }
