from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import shutil
import sys
from datetime import datetime
from loguru import logger

# Resolve paths:  in EXE -> next to Leomail.exe,  in dev -> project root
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).parent  # e.g. Desktop/Leomail/
else:
    PROJECT_ROOT = Path(__file__).parent.parent

USER_DATA_DIR = PROJECT_ROOT / "user_data"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = USER_DATA_DIR / "leomail.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ── SQLite WAL mode + busy_timeout ──────────────────────────────────────────
@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Enable WAL journal mode and busy timeout on every connection.
    WAL = better concurrent reads during multi-threaded autoreg/warmup/campaign.
    busy_timeout = wait 5s instead of instant 'database is locked' error.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, faster writes
    cursor.close()


# ── Auto-backup on startup ──────────────────────────────────────────────────
BACKUP_DIR = USER_DATA_DIR / "backups"


def backup_database(reason: str = "auto") -> Path | None:
    """Copy leomail.db to backups/ with timestamp. Returns backup path or None."""
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"leomail_{ts}_{reason}.db"
    try:
        shutil.copy2(DB_PATH, dst)
        # Keep only last 5 backups
        backups = sorted(BACKUP_DIR.glob("leomail_*.db"), key=lambda p: p.stat().st_mtime)
        for old in backups[:-5]:
            old.unlink(missing_ok=True)
        logger.info(f"[DB] Backup created: {dst.name}")
        return dst
    except Exception as e:
        logger.warning(f"[DB] Backup failed: {e}")
        return None


# Run auto-backup on import (= app startup)
if DB_PATH.exists():
    backup_database("startup")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

