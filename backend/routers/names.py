"""
Leomail v3 — Names Router
Upload, list, delete name packs. Get random name from selected packs.
Format: firstname,lastname or firstname lastname per line.
"""
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from ..database import get_db, SessionLocal
from ..models import NamePack
from ..config import load_config
from loguru import logger
import os, random, shutil

router = APIRouter(prefix="/api/names", tags=["names"])

# Relative path — portable across VPS moves
NAMES_DIR = os.path.join("user_data", "names")
os.makedirs(NAMES_DIR, exist_ok=True)

# Built-in GEO name packs directory
BUILTIN_NAMES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "names")

# GEO pack labels
GEO_LABELS = {
    "us_uk": "🇺🇸 US / UK — English",
    "latam_es": "🇲🇽 LATAM — Español",
    "brazil_pt": "🇧🇷 Brazil — Português",
    "ru_cis": "🇷🇺 Россия / СНГ",
    "arab": "🇪🇬 Arab / Middle East",
    "europe_de_fr_it": "🇪🇺 Europe — DE / FR / IT",
    "africa": "🇳🇬 Africa — NG / ZA / ZM",
}


def seed_builtin_names():
    """Auto-import built-in GEO name packs on first startup."""
    if not os.path.isdir(BUILTIN_NAMES_DIR):
        return

    db = SessionLocal()
    try:
        existing = {p.name for p in db.query(NamePack).all()}
        seeded = 0

        for filename in sorted(os.listdir(BUILTIN_NAMES_DIR)):
            if not filename.endswith(".txt"):
                continue

            geo_key = os.path.splitext(filename)[0]
            pack_label = GEO_LABELS.get(geo_key, f"🌍 {geo_key}")

            if pack_label in existing:
                continue  # Already seeded

            src = os.path.join(BUILTIN_NAMES_DIR, filename)
            dst = os.path.join(NAMES_DIR, filename)

            # Copy file to user_data/names/
            shutil.copy2(src, dst)

            # Count names
            count = 0
            with open(dst, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        count += 1

            pack = NamePack(
                name=pack_label,
                file_path=os.path.join("user_data", "names", filename),  # relative path!
                total_count=count,
            )
            db.add(pack)
            seeded += 1
            logger.info(f"[Names] Seeded: {pack_label} ({count} names)")

        if seeded:
            db.commit()
            logger.info(f"[Names] ✅ Seeded {seeded} built-in GEO name packs")

        # Fix any absolute paths from previous versions (VPS portability)
        fixed = 0
        for pack in db.query(NamePack).all():
            fp = pack.file_path
            if fp and os.path.isabs(fp):
                # Convert absolute to relative: extract user_data/names/filename
                basename = os.path.basename(fp)
                new_path = os.path.join("user_data", "names", basename)
                if os.path.exists(new_path) or os.path.exists(fp):
                    pack.file_path = new_path
                    fixed += 1
        if fixed:
            db.commit()
            logger.info(f"[Names] Fixed {fixed} absolute paths → relative")

    except Exception as e:
        logger.error(f"[Names] Seed error: {e}")
    finally:
        db.close()


@router.get("/")
async def list_name_packs(db: Session = Depends(get_db)):
    packs = db.query(NamePack).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "total_count": p.total_count,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in packs
    ]


@router.get("/{pack_id}/preview")
async def preview_name_pack(pack_id: int, db: Session = Depends(get_db)):
    """Return all names from a pack."""
    pack = db.query(NamePack).filter(NamePack.id == pack_id).first()
    if not pack:
        return {"error": "Pack not found", "names": []}
    import os
    if not os.path.exists(pack.file_path):
        return {"error": "File not found", "names": [], "name": pack.name}
    lines = []
    try:
        with open(pack.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    lines.append(line)
    except Exception:
        pass
    return {"name": pack.name, "total": pack.total_count, "names": lines}


def _parse_name_line(line: str) -> tuple[str, str] | None:
    """Parse a name line: 'First,Last' or 'First Last' or just 'First'."""
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    if ',' in line:
        parts = [p.strip() for p in line.split(',', 1)]
    elif '\t' in line:
        parts = [p.strip() for p in line.split('\t', 1)]
    else:
        parts = line.split(None, 1)

    first = parts[0] if len(parts) > 0 else None
    last = parts[1] if len(parts) > 1 else ""

    if not first:
        return None
    return (first, last)


@router.post("/upload")
async def upload_name_pack(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = (await file.read()).decode("utf-8", errors="ignore")
    lines = content.strip().split("\n")

    names = []
    for line in lines:
        parsed = _parse_name_line(line)
        if parsed:
            names.append(parsed)

    if not names:
        return {"error": "Не найдено имён в файле"}

    # Save file
    pack_name = os.path.splitext(file.filename)[0]
    file_path = os.path.join(NAMES_DIR, f"{pack_name}.txt")
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(NAMES_DIR, f"{pack_name}_{counter}.txt")
        counter += 1

    with open(file_path, "w", encoding="utf-8") as f:
        for first, last in names:
            f.write(f"{first},{last}\n")

    pack = NamePack(
        name=pack_name,
        file_path=file_path,
        total_count=len(names),
    )
    db.add(pack)
    db.commit()

    logger.info(f"Name pack '{pack_name}' uploaded: {len(names)} names")
    return {"id": pack.id, "name": pack_name, "count": len(names)}


from pydantic import BaseModel


class NameTextUpload(BaseModel):
    name: str = ""
    text: str


@router.post("/upload-text")
async def upload_names_text(req: NameTextUpload, db: Session = Depends(get_db)):
    """Upload names from pasted text (first,last per line)."""
    lines = req.text.strip().split("\n")
    names = []
    for line in lines:
        parsed = _parse_name_line(line)
        if parsed:
            names.append(parsed)

    if not names:
        return {"error": "Не найдено имён. Формат: first,last (по одному на строку)"}

    import time
    pack_name = req.name.strip() or f"paste_{len(names)}_names"
    file_path = os.path.join(NAMES_DIR, f"{int(time.time())}_{pack_name}.txt")

    with open(file_path, "w", encoding="utf-8") as f:
        for first, last in names:
            f.write(f"{first},{last}\n")

    pack = NamePack(
        name=pack_name,
        file_path=file_path,
        total_count=len(names),
    )
    db.add(pack)
    db.commit()

    logger.info(f"Name pack '{pack_name}' from text: {len(names)} names")
    return {"id": pack.id, "name": pack_name, "count": len(names)}

@router.post("/batch-delete")
async def batch_delete_names(req: dict, db: Session = Depends(get_db)):
    """Delete multiple name packs by IDs."""
    ids = req.get("ids", [])
    if not ids:
        return {"deleted": 0}
    packs = db.query(NamePack).filter(NamePack.id.in_(ids)).all()
    for p in packs:
        try:
            if os.path.exists(p.file_path):
                os.remove(p.file_path)
        except Exception:
            pass
        db.delete(p)
    db.commit()
    return {"deleted": len(packs)}

@router.delete("/{pack_id}")
async def delete_name_pack(pack_id: int, db: Session = Depends(get_db)):
    pack = db.query(NamePack).filter(NamePack.id == pack_id).first()
    if not pack:
        return {"error": "Pack not found"}

    if os.path.exists(pack.file_path):
        os.remove(pack.file_path)

    db.delete(pack)
    db.commit()
    return {"status": "deleted"}


@router.get("/random")
async def get_random_name(pack_ids: str = "", db: Session = Depends(get_db)):
    """Get a random name from selected packs. pack_ids = comma-separated IDs."""
    ids = [int(x) for x in pack_ids.split(",") if x.strip().isdigit()] if pack_ids else []

    if ids:
        packs = db.query(NamePack).filter(NamePack.id.in_(ids)).all()
    else:
        packs = db.query(NamePack).all()

    if not packs:
        return {"first_name": "Alex", "last_name": "Johnson"}

    # Collect all names from all selected packs
    all_names = []
    for pack in packs:
        if os.path.exists(pack.file_path):
            with open(pack.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    parsed = _parse_name_line(line)
                    if parsed:
                        all_names.append(parsed)

    if not all_names:
        return {"first_name": "Alex", "last_name": "Johnson"}

    first, last = random.choice(all_names)
    return {"first_name": first, "last_name": last}
