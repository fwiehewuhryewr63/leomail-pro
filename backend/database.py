from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import sys

# Resolve paths:  in EXE → next to Leomail.exe,  in dev → project root
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

