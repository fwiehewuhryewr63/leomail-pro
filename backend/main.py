import sys
import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from .database import engine as db_engine, Base
from .config import init_directories, load_config

# Import routers
from .routers import dashboard, birth, settings, proxies, farms, templates, databases, links, geo, resources
from .routers import sms, human_engine, errors, names, work, logs, stats, campaigns, export
from .routers import engine as engine_router
from .routers import warmup, update


@asynccontextmanager
async def lifespan(app):
    """Single lifespan handler - avoids merged_lifespan recursion in PyInstaller."""
    await _startup()
    yield
    # Shutdown logic (if needed)
    logger.info("Leomail shutting down...")


app = FastAPI(title="Leomail", version="4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers - using direct route addition to avoid
# FastAPI's merged_lifespan recursion (crashes PyInstaller frozen EXE)
_all_routers = [
    dashboard.router, birth.router, settings.router, proxies.router,
    farms.router, templates.router, databases.router, links.router,
    geo.router, resources.router, sms.router, human_engine.router,
    errors.router, names.router, work.router, logs.router,
    stats.router, campaigns.router, export.router, engine_router.router,
    warmup.router, update.router,
]
for _r in _all_routers:
    app.router.routes.extend(_r.routes)


async def _startup():
    # Setup log file (next to EXE, not inside _internal/)
    from .database import PROJECT_ROOT as _PR
    log_path = _PR / "user_data" / "logs" / "leomail.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(str(log_path), rotation="5 MB", retention="7 days", level="INFO",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}")

    # Create all tables
    Base.metadata.create_all(bind=db_engine)
    logger.info("Database tables created/verified")

    # Auto-migrate: add missing columns to existing tables
    from sqlalchemy import text, inspect
    with db_engine.connect() as conn:
        inspector = inspect(db_engine)

        # proxies - missing columns
        proxy_cols = [c["name"] for c in inspector.get_columns("proxies")]
        proxy_migrations = {
            "external_ip": "VARCHAR",
            "use_count": "INTEGER DEFAULT 0",
        }
        for col, col_type in proxy_migrations.items():
            if col not in proxy_cols:
                conn.execute(text(f"ALTER TABLE proxies ADD COLUMN {col} {col_type}"))
                conn.commit()
                logger.info(f"Migrated: added {col} column to proxies")

        # templates - all potentially missing columns
        try:
            tmpl_cols = [c["name"] for c in inspector.get_columns("templates")]
            migrations = {
                "pack_name": "VARCHAR",
                "variables": "JSON",
                "content_type": "VARCHAR DEFAULT 'html'",
                "language": "VARCHAR DEFAULT 'en'",
                "updated_at": "DATETIME",
                "niche": "VARCHAR",
            }
            for col, col_type in migrations.items():
                if col not in tmpl_cols:
                    conn.execute(text(f"ALTER TABLE templates ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    logger.info(f"Migrated: added {col} column to templates")
        except Exception:
            pass  # table may not exist yet

        # tasks - stop_reason (graceful termination)
        try:
            task_cols = [c["name"] for c in inspector.get_columns("tasks")]
            task_migrations = {
                "stop_reason": "VARCHAR",
            }
            for col, col_type in task_migrations.items():
                if col not in task_cols:
                    conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    logger.info(f"Migrated: added {col} column to tasks")
        except Exception:
            pass

        # proxies - per-provider usage counters
        try:
            proxy_cols2 = [c["name"] for c in inspector.get_columns("proxies")]
            proxy_extra = {
                "use_gmail": "INTEGER DEFAULT 0",
                "use_yahoo": "INTEGER DEFAULT 0",
                "use_aol": "INTEGER DEFAULT 0",
                "use_outlook": "INTEGER DEFAULT 0",
                "use_hotmail": "INTEGER DEFAULT 0",
                "use_protonmail": "INTEGER DEFAULT 0",
                "use_tuta": "INTEGER DEFAULT 0",
                "total_births": "INTEGER DEFAULT 0",
                "total_fails": "INTEGER DEFAULT 0",
                "last_used_at": "DATETIME",
                "source": "VARCHAR DEFAULT 'manual'",
                "external_id": "VARCHAR",
            }
            for col, col_type in proxy_extra.items():
                if col not in proxy_cols2:
                    conn.execute(text(f"ALTER TABLE proxies ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    logger.info(f"Migrated: added {col} column to proxies")
        except Exception:
            pass

        # campaigns - send settings + account source columns
        try:
            camp_cols = [c["name"] for c in inspector.get_columns("campaigns")]
            camp_migrations = {
                "emails_per_day_min": "INTEGER DEFAULT 25",
                "emails_per_day_max": "INTEGER DEFAULT 75",
                "delay_min": "INTEGER DEFAULT 30",
                "delay_max": "INTEGER DEFAULT 180",
                "same_provider": "BOOLEAN DEFAULT 0",
                "max_link_uses": "INTEGER DEFAULT 0",
                "max_link_cycles": "INTEGER DEFAULT 0",
                "use_existing": "BOOLEAN DEFAULT 0",
                "farm_ids": "JSON",
                "stop_reason": "VARCHAR",
                "accounts_born": "INTEGER DEFAULT 0",
                "accounts_dead": "INTEGER DEFAULT 0",
                "total_sent": "INTEGER DEFAULT 0",
                "total_errors": "INTEGER DEFAULT 0",
            }
            for col, col_type in camp_migrations.items():
                if col not in camp_cols:
                    conn.execute(text(f"ALTER TABLE campaigns ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    logger.info(f"Migrated: added {col} column to campaigns")
        except Exception:
            pass

        # campaign_recipients - first_name for VIP
        try:
            cr_cols = [c["name"] for c in inspector.get_columns("campaign_recipients")]
            if "first_name" not in cr_cols:
                conn.execute(text("ALTER TABLE campaign_recipients ADD COLUMN first_name VARCHAR"))
                conn.commit()
                logger.info("Migrated: added first_name column to campaign_recipients")
        except Exception:
            pass

        # link_databases - niche column
        try:
            lp_cols = [c["name"] for c in inspector.get_columns("link_databases")]
            if "niche" not in lp_cols:
                conn.execute(text("ALTER TABLE link_databases ADD COLUMN niche VARCHAR"))
                conn.commit()
                logger.info("Migrated: added niche column to link_databases")
        except Exception:
            pass

        # recipient_databases - with_name column
        try:
            rd_cols = [c["name"] for c in inspector.get_columns("recipient_databases")]
            if "with_name" not in rd_cols:
                conn.execute(text("ALTER TABLE recipient_databases ADD COLUMN with_name BOOLEAN DEFAULT 0"))
                conn.commit()
                logger.info("Migrated: added with_name column to recipient_databases")
        except Exception:
            pass

        # accounts - IMAP verification columns
        try:
            acc_cols = [c["name"] for c in inspector.get_columns("accounts")]
            acc_migrations = {
                "imap_verified": "BOOLEAN DEFAULT 0",
                "imap_checked_at": "DATETIME",
            }
            for col, col_type in acc_migrations.items():
                if col not in acc_cols:
                    conn.execute(text(f"ALTER TABLE accounts ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    logger.info(f"Migrated: added {col} column to accounts")
        except Exception:
            pass

    # Initialize user_data directories
    init_directories()

    # Clean up stuck ThreadLog AND Task entries from previous sessions
    from .models import ThreadLog, Task
    from .database import SessionLocal
    db = SessionLocal()

    # Stuck threads
    stuck = db.query(ThreadLog).filter(ThreadLog.status == "running").all()
    for t in stuck:
        t.status = "error"
        t.error_message = "Server was restarted"
    if stuck:
        db.commit()
        logger.info(f"Cleaned up {len(stuck)} stuck thread(s) from previous session")

    # Stuck tasks (shows as "active tasks" on dashboard)
    stuck_tasks = db.query(Task).filter(Task.status.in_(["running", "pending"])).all()
    for t in stuck_tasks:
        t.status = "failed"
        t.details = "Server was restarted"
    if stuck_tasks:
        db.commit()
        logger.info(f"Cleaned up {len(stuck_tasks)} stuck task(s) from previous session")
    db.close()

    # Seed built-in GEO name packs (auto-imports on first run only)
    from .routers.names import seed_builtin_names
    seed_builtin_names()

    # Start proxy monitor background task
    config = load_config()

    # Apply saved proxy limits to ProxyManager
    from .services.proxy_manager import ProxyManager as _PM
    pl = config.get("proxy_limits", {})
    if "gmail" in pl: _PM.GMAIL_LIMIT = max(1, pl["gmail"])
    if "yahoo_aol" in pl: _PM.YA_LIMIT = max(1, pl["yahoo_aol"])
    if "outlook_hotmail" in pl: _PM.OH_LIMIT = max(1, pl["outlook_hotmail"])
    if "protonmail" in pl: _PM.PT_LIMIT = max(1, pl["protonmail"])
    if "tuta" in pl: _PM.TT_LIMIT = max(1, pl["tuta"])
    logger.info(f"Proxy limits: Gmail={_PM.GMAIL_LIMIT}, YA={_PM.YA_LIMIT}, OH={_PM.OH_LIMIT}, PT={_PM.PT_LIMIT}, TT={_PM.TT_LIMIT}")

    proxy_cfg = config.get("proxy_monitor", {})
    interval = max(60, proxy_cfg.get("check_interval_sec", 120))
    max_fails = max(1, proxy_cfg.get("max_fail_count", 3))

    from .services.proxy_monitor import proxy_monitor_loop
    asyncio.create_task(proxy_monitor_loop(interval_sec=interval, max_fails=max_fails))
    logger.info(f"Proxy monitor started (every {interval}s, max_fails={max_fails})")

    # Browser leak guard - background task kills orphaned chromium processes
    try:
        from .services.browser_leak_guard import periodic_leak_guard
        asyncio.create_task(periodic_leak_guard(interval_seconds=120, max_age_seconds=300))
    except Exception:
        pass

    logger.info("Leomail v4.0 Backend Started - Blitz Pipeline")


# Serve React frontend in production
if getattr(sys, 'frozen', False):
    # PyInstaller frozen EXE
    base_path = Path(sys._MEIPASS)
else:
    base_path = Path(__file__).parent.parent

frontend_path = base_path / "frontend" / "dist"

if frontend_path.exists():
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Not found"}, status_code=404)
        file_path = frontend_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_path / "index.html"))
