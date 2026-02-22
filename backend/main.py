import sys
import os
import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from .database import engine, Base
from .config import init_directories, load_config

# Import routers
from .routers import dashboard, birth, settings, proxies, farms, templates, databases, links, geo, resources
from .routers import sms, human_engine, errors, names, warmup, work, logs, stats

app = FastAPI(title="Leomail", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(dashboard.router)
app.include_router(birth.router)
app.include_router(settings.router)
app.include_router(proxies.router)
app.include_router(farms.router)
app.include_router(templates.router)
app.include_router(databases.router)
app.include_router(links.router)
app.include_router(geo.router)
app.include_router(resources.router)
app.include_router(sms.router)
app.include_router(human_engine.router)
app.include_router(errors.router)
app.include_router(names.router)
app.include_router(warmup.router)
app.include_router(work.router)
app.include_router(logs.router)
app.include_router(stats.router)


@app.on_event("startup")
async def startup_event():
    # Setup log file
    from pathlib import Path as P
    log_path = P("user_data/logs/leomail.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(str(log_path), rotation="5 MB", retention="7 days", level="INFO",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}")

    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Auto-migrate: add missing columns to existing tables
    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        inspector = inspect(engine)

        # proxies — missing columns
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

        # templates — all potentially missing columns
        try:
            tmpl_cols = [c["name"] for c in inspector.get_columns("templates")]
            migrations = {
                "pack_name": "VARCHAR",
                "variables": "JSON",
                "content_type": "VARCHAR DEFAULT 'html'",
                "language": "VARCHAR DEFAULT 'en'",
                "updated_at": "DATETIME",
            }
            for col, col_type in migrations.items():
                if col not in tmpl_cols:
                    conn.execute(text(f"ALTER TABLE templates ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    logger.info(f"Migrated: added {col} column to templates")
        except Exception:
            pass  # table may not exist yet

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
        t.error_message = "Сервер был перезапущен"
    if stuck:
        db.commit()
        logger.info(f"Cleaned up {len(stuck)} stuck thread(s) from previous session")

    # Stuck tasks (shows as "active tasks" on dashboard)
    stuck_tasks = db.query(Task).filter(Task.status.in_(["running", "pending"])).all()
    for t in stuck_tasks:
        t.status = "failed"
        t.details = "Сервер был перезапущен"
    if stuck_tasks:
        db.commit()
        logger.info(f"Cleaned up {len(stuck_tasks)} stuck task(s) from previous session")
    db.close()

    # Seed built-in GEO name packs (auto-imports on first run only)
    from .routers.names import seed_builtin_names
    seed_builtin_names()

    # Start proxy monitor background task
    config = load_config()
    proxy_cfg = config.get("proxy_monitor", {})
    interval = max(60, proxy_cfg.get("check_interval_sec", 120))
    max_fails = max(1, proxy_cfg.get("max_fail_count", 3))

    from .services.proxy_monitor import proxy_monitor_loop
    asyncio.create_task(proxy_monitor_loop(interval_sec=interval, max_fails=max_fails))
    logger.info(f"Proxy monitor started (every {interval}s, max_fails={max_fails})")

    logger.info("Leomail v3.0 Backend Started")


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
